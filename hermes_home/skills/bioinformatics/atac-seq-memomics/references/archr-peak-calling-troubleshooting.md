# ArchR Peak Calling & 跨物种 ATAC 排错（人/猴海马衰老专利项目实战沉淀）

实战来源：2026-08-29 人（Zemke GSE278576 / hg38）+ 猴（张潇 NHPABC / T2T-MFA8v1.1，RefSeq `NC_088375.1` 命名）snATAC 跨物种 peak calling。

## 1. getMatrixFromProject(useMatrix="PeakMatrix") 报 "useMatrix is not in Available Matrices"
- 根因：只跑了 `addReproduciblePeakSet`（出 peak 坐标），**没跑 `addPeakMatrix`**（细胞×peak 计数矩阵）。
- 修复：`getAvailableMatrices(proj)` 确认 → `proj <- addPeakMatrix(proj, force = TRUE)` → 再取。
- 人脑"跑完 peak"后同样要确认 addPeakMatrix 已执行，否则同错。

## 2. addGroupCoverages / H5Fcreate 报 "HDF5. File accessibility. Unable to open file"
- 根因链：**load 了别人的 ArchRProject → outputDirectory 指向对方目录 → 你无写权限 → 创建 coverage .h5 失败**（最常见）。也见过上次中断残留损坏 .h5、共享盘写锁（高线程并行时）。
- 验证顺序：
  1. `getOutputDirectory(proj)` 看实际写路径；`touch 该目录/test.tmp` 测试写权限（不行=权限问题）
  2. `df -h` 看磁盘/配额；`lfs quota` 查 per-user 配额
  3. `find 输出目录/GroupCoverages -name "*.h5"` 看残留
- 修复（首选）：`copyArchRProject(projToCopy = proj, outputDirectory = 自己有权限的目录, force = TRUE)` → 从自己目录 `loadArchRProject` 再跑。备选：改 `proj@projectMetadata$outputDirectory` 到自己的路径。
- 重跑前必做：`unlink(file.path(out, "GroupCoverages"), recursive = TRUE)` + 传 `force = TRUE`；线程保守 `addArchRThreads(threads = 8)`，50 线程在 NFS/GlusterFS 上易写锁。

## 3. 猴脑（T2T-MFA8v1.1，NC_088375.1 命名）需要 BSgenome 吗？
- `addGroupCoverages` / `addReproduciblePeakSet` **不需要** `library(BSgenome...)`——基因组注释在 Arrow 文件里（createArrowFiles 时写入）。
- **禁止为猴数据加载 hg38 BSgenome**（坐标体系全错）。只有 motif 分析（addMotifAnnotations）才需要对应物种的 BSgenome。
- 验证用对基因组：`head(proj@genomeAnnotation$chromSizes)` 应显示 21 条 NC_088375.1 命名；若见 chr1-22+X+Y = 用了人基因组，项目建错了。

## 4. peak calling 参数（张潇 NHPABC cCRE 论文流程，可复现）
```r
proj <- addGroupCoverages(proj, groupBy = "celltype",
    minCells = 40, maxCells = 5000, minReplicates = 2, maxReplicates = 10, force = TRUE)
proj <- addReproduciblePeakSet(proj, groupBy = "celltype",
    pathToMacs2 = "绝对路径/macs2", maxPeaks = 500000, cutOff = 0.01)
```
- 输出 501-bp fixed-width peaks（人脑实测 525,137 个全部 501bp = 正常）。
- `findMacs2()` 找不到 → 手动绝对路径（conda env，如 `/hwfssz3/.../envs/MACS2/bin/macs2`），先 `macs2 --version` 验证。
- 50 CPU 上限：addGroupCoverages 是 I/O + 逐步并行，CPU 静默 **正常**；addPeakMatrix 吃全量细胞，峰值内存 20-40GB，先 `free -g`。

## 5. 保存 ArchR Project
- 必须用 `saveArchRProject(proj, outputDirectory=..., load=TRUE)`，**不是 saveRDS**——saveRDS 只存指针，不管理 Arrow/PeakSet 引用，下次 load 不到数据。
- 载回用 `loadArchRProject(目录)`，不要 readRDS。

## 6. Sample → individual 提取（跨物种 meta 统一）
- 猴：`"M1_Hip_1"` → `sub("_[0-9]+$", "", x)` → `M1`（同个体多文库去重）。
- 人：`"GSM8549615_hc77"` → `sub("^GSM[0-9]+_", "", x)` → `hc77`。
- **年龄映射必须代码匹配权威表**（Zemke Table_S1 donor ID），禁止手写 age_map 占位符——用户当场抓出过 hc78=25 应为 20。

## 7. 跨物种年龄组对齐（生命阶段，非绝对年龄）
- 猴 Young(5-6)/Middle(10-12)/Old(22-23)/EO(28-31) ↔ 人 20-40/40-60/60-80/80-100（Zemke Table_S1，40 donors 4×10 平衡）。
- 统计单位 = **个体**（人 40 / 猴 21），非细胞数（防伪重复）；猴 M4 仅 61 细胞被剔除 → 统计 n=20，文档必须写明口径。

## 8. L1 序列保守性资源与路径
- UCSC **无 T2T-MFA8 chain**（只有旧组装 MacFas5）→ **不走 liftOver**，用基因 ortholog 映射（DA tile → 最近基因 → NCBI ortholog → hg38 基因座 → phyloP 评分）。
- 已下载：`hg38.phyloP100way.bw`(9.87GB)、`hg38.phastCons100way.bw`(5.5GB)、`hg38.phyloP30way.bw`(7.9GB) → `E:/专利/L1_resources/`。
- 下载坑：Windows 上 curl 对 UCSC 域名 DNS 超时/SSL 失败，但 **Python urllib 可用**（走系统代理）；大文件用后台进程 + 进度日志（每 64MB 记录）模式，不要前台阻塞。