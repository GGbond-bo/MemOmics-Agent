# ArchR Peak Calling on Shared HPC Cluster — Pitfalls & Facts

会话来源：memomics-cd677556（2026-08-29，猴脑/人脑海马 ATAC peak calling，张潇 NHPABC 流程复现）

## 1. HDF5 `File accessibility. Unable to open file` 根因（最高频）

`addGroupCoverages` 报 `Error in H5Fcreate(file): HDF5. File accessibility. Unable to open file.`

**第一个要查的不是参数，是写权限**：

- 如果你 `loadArchRProject` 的是**别人的 Project**（如张潇的 `/hwfssz3/.../saveProj20250710`），它的 `outputDirectory` 指向对方目录；
- `addGroupCoverages` 要在 `outputDirectory/GroupCoverages/` 下创建 `.h5`，你没有那个目录写权限 → H5Fcreate 失败。
- 日志特征：`Group Astro._.O2_Hip_3 (1 of 40)` 出现在错误前——正在遍历 sample×group 写覆盖文件。

**判断**：
```r
getOutputDirectory(proj)   # 看指向哪；若是他人目录 → 权限问题
```
```bash
touch <outputDirectory>/__test.tmp && echo WRITABLE || echo NOT_WRITABLE
```

**修复（二选一）**：
```r
# A. 复制 Project 到自己的可写目录（推荐，长期使用一劳永逸）
proj <- copyArchRProject(projToCopy = proj, outputDirectory = "/自己/可写/路径", force = TRUE)

# B. 只改内存中的 outputDirectory，不碰原 Project
proj@projectMetadata$outputDirectory <- "/自己/可写/路径"
dir.create(proj@projectMetadata$outputDirectory, recursive = TRUE)
unlink(file.path(proj@projectMetadata$outputDirectory, "GroupCoverages"), recursive = TRUE)
```

**次要原因**：上次中断残留损坏/空 .h5、磁盘满（`df -h`）、共享文件系统锁（NFS/GlusterFS 上多线程写 H5 有已知问题 → 降 `addArchRThreads(1-8)` 稳）。

## 2. Peak Calling 官方顺序（官网 12.2 逐行）

```r
pathToMacs2 <- findMacs2()        # ⭐ 先（12.2 第一件事）——不在后面！
proj <- addGroupCoverages(proj, groupBy = "celltype")          # 峰值前必须跑（官网强调）
proj <- addReproduciblePeakSet(proj, groupBy = "celltype",
                               pathToMacs2 = pathToMacs2)      # 12.2 官方示例同款
```
`findMacs2()` 找不到时手动指定：`pathToMacs2 <- "/path/to/macs2"`（官网明确支持；conda env 里装好 MACS2 后直接给 envs/.../bin/macs2 绝对路径）。

## 3. 官方默认参数（formals() 实测，非凭空）

**addGroupCoverages 默认**：`minCells=40, maxCells=500, maxFragments=25e6`（⚠️ 不是 8e7，曾记错过）、`minReplicates=2, maxReplicates=5, sampleRatio=0.8`

**addReproduciblePeakSet 默认**：`peakMethod="Macs2"`（推荐）/`reproducibility="2"`（至少 2 个 pseudo-bulk 有 peak）/`peaksPerCell=500`/`minCells=25`/`pathToMacs2=findMacs2()`/`shift=-75, extsize=150`（ATAC 经典 MACS2 参数）/`excludeChr=c("chrM","chrY")`

官网示例只写 3 个参数是因为其余走默认，**不是"官方没有"**。

## 4. BSgenome 澄清（重要）

- `addGroupCoverages` / `addReproduciblePeakSet` **不需要** `library(BSgenome.XXX)`——基因组注释在 `createArrowFiles` 时已写入 Arrow（`proj@genomeAnnotation`），loadArchRProject 自动读取。
- 猴脑（Macaca fascicularis T2T-MFA8v1.1）**绝不能用 hg38 的 BSgenome**——染色体会不匹配（猴是 NC_088375.1 系列 21 条染色体）。
- 什么时候才需要 BSgenome：`addMotifAnnotations()`（motif 富集，算背景用的）。

## 5. CPU 观察（正常现象，不是卡死）

| 阶段 | 瓶颈 | 现象 |
|------|------|------|
| addGroupCoverages | 磁盘 I/O（读 Arrow + 写覆盖文件） | CPU 低是正常的，在等 IO |
| addReproduciblePeakSet 的 MACS2 | 单核计算 | 50 核节点只见 1 核忙，正常 |

**时间估算（~20 万细胞 / 8 个大群）**：addGroupCoverages 15-40 min（IO 瓶颈），MACS2 callpeak 10-20 min（单核逐个跑，ArchR 并行），addPeakMatrix 15-30 min（全量细胞，IO 瓶颈，与线程无关）→ 合计约 1-2.5 h。别用 50 线程硬怼（共享 FS 写锁 + 内存翻倍），`addArchRThreads(8)` 稳妥。

## 6. 张潇 NHPABC cCRE 官方参数（复现目标）

- **QC 线**：每个体 >10 nuclei、每 age group >100 nuclei 的细胞类型才做 cCRE
- **addGroupCoverages**：`minCells=40, maxCells=5000, minReplicates=2, maxReplicates=10`
- **addReproduciblePeakSet**：`maxPeaks=500000, cutOff=0.01` → **501-bp 固定宽度 peak**
- **cCRE 过滤**：PeakMatrix → Seurat RC 归一化（scale.factor=1e6 = CPM）→ Peak × Individual 均值 → `Mean CPM > 4 在 ≥4 猴样本` 且 `Mean CPM > 0 在 ≥12 猴样本`
- **peak-to-gene**：`addCoAccessibility`，aggregation k=10, window=500kb, distance=250kb

## 7. Peak 保存 / 导出

```r
saveArchRProject(proj)                                   # 含 PeakSet + PeakMatrix
peaks <- getPeakSet(proj)                                 # GRanges
rtracklayer::export.bed(peaks, "xxx_Hf_peaks.bed")        # L1 序列保守分析输入
```

## 8. 样本命名 → individual 提取（人猴通用）

- 人脑：`GSM8549615_hc77` → individual = `hc77`：`sub(".*_(hc[0-9]+).*", "\\1", sample)`
- 猴脑：`M1_Hip_1` / `O2_Hip_3` → individual = `M1`（去掉 `_Hip_N`）：`sub("_.*", "", sample)` 或 `sub("(.*)_Hip_.*", "\\1", sample)`
- 统计单位 = individual（人 40 / 猴 21），**不能拿 sample/library 当个体**（同一个体多个文库是伪重复）。