# ArchR Peak Calling 生产流程坑（2026-08-30 GSE278576 40 人 + NHPABC 63 文库实测）

## 1. HDF5 "Unable to open file" / H5Fcreate 失败 —— 写权限根因（最常见）

**症状**：
```
Group Astro._.O2_Hip_3 (1 of 40): Creating Group Coverage File ...
Number of Cells = 500
Error in H5Fcreate(file): HDF5. File accessibility. Unable to open file.
```

**根因（逐层排查，按频率排序）**：
1. **outputDirectory 无写权限**（本会话最终根因）：从别人共享的 ArchR Project 加载（如 `/hwfssz3/PS_JLU/zhangxiao6/.../saveProj20250710`），Project 的 `outputDirectory` 写死指向主人目录，`addGroupCoverages` 往那里写 `GroupCoverages/*.h5`。看似有读权限能 load，但写被拒 → H5Fcreate 失败。
   - 诊断：`proj@projectMetadata$outputDirectory` 看指向；`touch <dir>/__test.tmp` 验证可写。
   - 修复：`copyArchRProject(projToCopy=proj, outputDirectory="自己的目录")` 或直接改 `proj@projectMetadata$outputDirectory` 后 `saveArchRProject` 到自己目录。**不要想着去改源头目录权限**。
2. 上次中断残留损坏 .h5 → `unlink("GroupCoverages", recursive=TRUE)` + `force=TRUE` 重跑。
3. 磁盘满（`df -h` 达 100%）→ 清空间。
4. 并发写同一 Project（ArchR 多实例共享 tmp 的已知坑）→ 串行。

**注意**：`H5Fcreate`（创建失败）通常是权限/磁盘；`H5Fopen`（打开失败）通常是残留损坏文件。日志 `CellGroups N =5` 说明 addGroupCoverages 分组逻辑已跑通，纯卡在写文件。

## 2. call peak 后必须 addPeakMatrix（否则 getMatrixFromProject 报错）

**症状**：
```
Error in getMatrixFromProject(proj, useMatrix = "PeakMatrix"): useMatrix is not in Available Matrices
```

**根因**：`addReproduciblePeakSet()` 只生成 **peak 坐标集（PeakSet）**，不生成 **细胞×peak 计数矩阵**。矩阵要单独 `addPeakMatrix()`。

**正确顺序**：
```r
proj <- addGroupCoverages(proj, groupBy="celltype", minCells=40, maxCells=5000, minReplicates=2, maxReplicates=10, force=TRUE)
proj <- addReproduciblePeakSet(proj, groupBy="celltype", pathToMacs2=pathToMacs2, maxPeaks=500000, cutOff=0.01)
proj <- addPeakMatrix(proj, force=TRUE)          # ← 常被漏掉！之后才 getMatrixFromProject 可用
saveArchRProject(proj)                            # 保存整个 Project
```

## 3. 保存必须 saveArchRProject，不是 saveRDS

- `saveRDS(proj)` 只序列化轻量 R 对象（元数据 + cellColData + Arrow 路径引用），**PeakSet/PeakMatrix 等大矩阵不会完整涵盖**，下次 load 可能丢失。
- ArchR 官方保存 = `saveArchRProject(ArchRProj=proj, outputDirectory=..., overwrite=TRUE, load=TRUE)`；加载 = `loadArchRProject("目录")`（不是 readRDS）。
- 用户问"不是 saveRDS 吗" → 明确解释二者区别，ArchR 项目用 saveArchRProject。

## 4. 猴脑 peak calling 不需要 BSgenome.Hsapiens.UCSC.hg38

- `addGroupCoverages` / `addReproduciblePeakSet` 用到的基因组信息（chrom sizes / blacklist）已随 Arrow 生成时写入 `proj@genomeAnnotation`，**不需要**当前 session `library(BSgenome.*)`。
- **绝不能用 hg38 跑猴脑**：猴脑是食蟹猴 T2T-MFA8v1.1（21 条 chr：NC_088375.1–NC_088395.1），用人类 BSgenome 会导致染色体名不匹配、peak calling 全错。
- 校验：`proj@genomeAnnotation$chromSizes` 应显示 `NC_088375.1` 等 RefSeq accession（猴）或 `chr1-22+X`（人）。
- 只有 motif/footprint 相关（addMotifAnnotations）才需要 BSgenome；猴脑需自建 T2T-MFA8 对应 BSgenome，不是 hg38。

## 5. MACS2 找不到时的路径提供（官网 12.2 原文支持）

`findMacs2()` 只查 PATH/pip/conda。手动装好的 conda env 里 macs2 不在 PATH 时：
```r
pathToMacs2 <- "/hwfssz3/.../miniconda3/envs/MACS2/bin/macs2"
system(paste(pathToMacs2, "--version"))     # 先验证可执行
proj <- addReproduciblePeakSet(proj, groupBy="celltype", pathToMacs2=pathToMacs2)
```
官网原话：装好了但 ArchR 找不到 → 通过 `pathToMacs2` 参数提供函数路径。

## 6. 张潇 NHPABC cCRE 官方参数（复现峰值）

```r
proj <- addGroupCoverages(proj, groupBy="celltype",
    minCells=40, maxCells=5000, minReplicates=2, maxReplicates=10)
proj <- addReproduciblePeakSet(proj, groupBy="celltype",
    pathToMacs2=pathToMacs2, maxPeaks=500000, cutOff=0.01)
# 输出：501-bp fixed-width peaks
```
- 官方 README（github NHPABC cCRE）：cell types 每个体 >10 nuclei、每 age group >100 nuclei 才进分析。
- 之后 cCRE 筛选：PeakMatrix → Seurat RC 归一化 (scale.factor=1e6) → Peak×Individual mean-CPM → 过滤 Mean CPM>4 in ≥4 monkey samples、>0 in ≥12 samples。
- 101 万 peak（人 52.5万 + 猴 53.8万）为 normal：ArchR union peak set 常见 15-50 万；宽度全 501bp（`summary(width(getPeakSet(proj)))` min=median=max=501）是 addReproduciblePeakSet 默认 resize 的**正常标志**，不是 bug。

## 7. Windows 本地读 bigWig 工具链：全灭 → L1 phyloP 必须上 Linux 集群

目标是本地对已下载的 `*phyloP*.bw` 批量打分（如 L1 序列保守性），Windows 上所有现成工具都不可用（2026-08-30 实测）：

| 方案 | 结果 |
|------|------|
| `pip install pyBigWig` | ❌ 无 Windows wheel（PyPI 只有 manylinux），源码编译缺 MSVC 失败 |
| `conda install -c conda-forge pybigwig` | ❌ PackagesNotFoundInChannelsError（无 win-64 包） |
| R `rtracklayer::import.bw` / `BigWigFile` | ❌ "UCSC library operation failed"（Windows 下 UCSC C 库调用失败） |
| R CRAN `bigWig` 包 | ❌ 不存在 |
| UCSC 官方 `bigWigAverageOverBed.exe` | ❌ mingw.x86_64 路径 404 |
| 纯 Python 手写 bigWig 解析 | 可行但费时（B+ tree/cirTree 解析约 200+ 行），只作为最后手段 |

**结论/正确路线**：
1. **平时下载 UCSC 大数据用 Python urllib 而非 curl**（本机 curl 超时、Python 走代理成功——bigWig 23GB 就是 urllib 下的）。
2. **phyloP 批量打分的正路 = Linux 集群**：`pip install pyBigWig` 一条命令即可，脚本在集群跑；Windows 本机只做小样本 UCSC API 抽查（`https://api.genome.ucsc.edu/getData/track?genome=hg38&track=phyloP100way&chrom=chr1&start=&end=`，每查询约 0.9-1.7s，适合验证不适合全量）。
3. 全量 100 万 peak 逐点 API ≈ 300+ 小时，**不可行**；本地下 bigWig 又无工具 → 唯一现实路径是集群 pyBigWig 批量。
4. API 排查套路：curl 404/超时不代表工具不能用，先看响应原文（曾因查询代码里 chrom 拼接成 `chrchr1` 而返回空）；UCSC 下载/API 用 `User-Agent: Mozilla/5.0` + `urllib.request`。

## 8. 人猴跨物种比较：UCSC chain 版本陷阱

- UCSC 只有 `hg38ToMacFas5.over.chain.gz`（旧组装 MacFas5），**没有 T2T-MFA8v1.1（GCF_037993035.2, RefSeq NC_088375.1 命名）的 chain**。
- 直接用 MacFas5 chain 映射 T2T 坐标 = 坐标错位 → 结果不可信。**不要下载旧组装 chain 冒充**。
- 可行替代：基因 ortholog 锚定（DA tile → 最近基因 TSS±2kb → NCBI ortholog → hg38 基因座 → phyloP 打分），本会话 P3 已验证跑通（`gene_anchor_ortholog.py` + `fetch_hg38_coords_v3.py` + `l1_phylop_fill_v3.py`）；文献支持：Mich 2021 Cell Rep (PMID:33789096)、Barr & Gilad 2026 Genome Biol (PMID:42026616, alignment bias)。
- L1 窗口铁律：评估窗口用 TSS±2kb，不能整个基因全长（长内含子会稀释 phyloP 均值，BNIP3 全长 -0.126 vs TSS±1kb +0.185）。