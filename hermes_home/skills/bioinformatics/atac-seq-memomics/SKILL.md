---
name: atac-seq-memomics
description: "ArchR scATAC-seq 全流程: 环境搭建→Arrow文件→QC→降维→聚类→Peak calling→Motif→Footprinting→差异可及性→共可及性→导出"
version: 3.0.0
prerequisites:
  r_packages: ["ArchR", "Signac", "Seurat", "chromVAR", "motifmatchr", "ChIPseeker", "BSgenome.Hsapiens.UCSC.hg38"]
  python_packages: ["MACS2 (optional — TileMatrix fallback if unavailable, see references/macs2-windows-fallback.md)"]
  system_requirements: "ArchR needs R >=4.5.0 (TFMPvalue dep). R 4.5.3 is the goldilocks version — R 4.4.2 is too old (no TFMPvalue), R 4.6.1 is too new (no Rtools46). See references/windows_archr_setup.md for proven dual-R setup. Java >=8, >=16GB RAM for >50K cells"
---

# ATAC-seq 分析 (ArchR)

## Windows 双 R 环境 (ArchR + Seurat/Signac 共存)

ArchR 依赖 TFMPvalue → 需要 R ≥ 4.5.0。但版本选择有讲究：

| R 版本 | Rtools | TFMPvalue | ArchR 能装？ | 原因 |
|--------|:---:|:---:|:---:|------|
| 4.4.2 | Rtools44 ✅ | ❌ Bioc 3.20 没这个包 | ❌ | TFMPvalue 最早出现在 Bioc 3.21 |
| **4.5.3** | **Rtools44 可用** ✅ | ✅ Bioc 3.22 | ✅ **首选** | Rtools45 安装器有 bug，Rtools44+符号链接更可靠 |
| 4.6.1 | Rtools46 未发布 ❌ | ✅ | ❌ | 没有编译工具，GitHub 包源码编译失败 |

> 🏆 **R 4.5.3 是黄金版本。** 安装到 `C:\Program Files\R\R-4.5.3`（本体小），R 包库放 `E:\R-libs\R-4.5.3`（包很大，放 E 盘）。

调用：普通脚本用 `Rscript`，ArchR 脚本用 `"C:/Program Files/R/R-4.5.3/bin/Rscript.exe"`。

完整安装指南见 `references/windows_archr_setup.md`。

## Signac vs ArchR 选择

| 功能 | Signac | ArchR |
|------|:---:|:---:|
| peak calling | ✅ (需 MACS2) | ✅ (MACS2 或 TileMatrix 无 MACS2) |
| 差异可及性 | ✅ FindMarkers | ✅ (PeakMatrix 或 TileMatrix) |
| TF footprinting | ✅ | ✅ |
| **共可及性 (co-accessibility)** | ❌ | ✅ **ArchR 独占** |
| peak-to-gene linkage | ✅ LinkPeaks | ✅ 更成熟 |

> 跨物种 CRE 保守性评估需要共可及性 → 必须用 ArchR。

## 已知问题

> 📑 本会话（2026-08-08 P0/P1/P3）踩坑速查 → `references/archr-windows-pitfalls-2026-08.md`（addClusters input= / addGeneScoreMatrix 崩溃 / TileMatrix CSC 直读 / cellNames 前缀 / filtered Arrow 未剔除 doublet 的 8 条快查）

### 🔴 安装相关
- **Rtools45 安装器有 bug** — exit code 2/5，无法静默安装。**解决方案**：复用 Rtools44，在 ucrt64 目录创建 gcc/g++/gfortran 符号链接指向 x86_64-w64-mingw32.static.posix/bin/
- **`.Rprofile` 劫持库路径** — 如果 `~/.Rprofile` 硬编码了 `R-4.4.2-library`，所有 R 版本都会被劫持到错误路径。**解决方案**：改为 `R_version <- paste(R.version$major, R.version$minor, sep='.'); .libPaths(c(paste0('E:/R-libs/R-', R_version), .libPaths()))`
- **Bioconductor 镜像选择** — 清华镜像没有 Bioc 包，西湖大学 (`mirrors.westlake.edu.cn`) 可用。CRAN 用清华，Bioc 用西湖
- **R 包库分离** — R 本体放 C 盘（~100MB），包库放 E 盘（几 GB）。通过 `.libPaths()` 控制

### 🔴 DLL 连锁损坏（taskkill 杀 R 进程后）— 2026-07-29 已验证

**现象**：`taskkill` 杀 Rscript 后，`library(ArchR)` 报一连串 `LoadLibrary failure: 找不到指定的程序`：
```
rlang.dll → data.table.dll → Rcpp.dll → magrittr.dll → Biobase.dll → ...
```

**根因**：R 进程被杀时正在使用 `E:/R-libs/R-4.5.3/` 下的 DLL 文件 → Windows 文件锁未释放 → DLL 损坏。损坏是连锁的——ArchR 加载链上任何一环断了就全崩。

**⚠️ 先确认 R 版本**：`Rscript --version` 可能显示 **R 4.4.2**（PATH 默认），但 `E:/R-libs/R-4.5.3/` 的包是为 R 4.5.3 编译的。4.4.2 加载 4.5.3 DLL 也会报同样的错。**先用 `"C:/Program Files/R/R-4.5.3/bin/Rscript.exe" --version` 确认。**

**修复（批量重装受损包，必须 `type="win.binary"`）**：
```r
"C:/Program Files/R/R-4.5.3/bin/Rscript.exe" -e '
.libPaths(c("E:/R-libs/R-4.5.3", .libPaths()))
# 先修核心依赖，顺序重要：Rcpp → rlang → data.table
install.packages(c("Rcpp", "rlang", "data.table"), 
  repos="https://cloud.r-project.org", type="win.binary", lib="E:/R-libs/R-4.5.3")
# Bioconductor 包（Biobase, S4Vectors, etc.）用 BiocManager
BiocManager::install(c("Biobase", "S4Vectors", "GenomicRanges", "SummarizedExperiment"),
  lib="E:/R-libs/R-4.5.3", ask=FALSE)
'
```

**预防**：杀 R 进程前先确认没有 R 脚本正在跑（`tasklist | grep Rscript`），优先等脚本自然结束。

### 🔴 MACS2 在 Windows 上不可安装 → TileMatrix 替代方案
- **MACS2 pip install 失败** — Cython 3+ 不兼容 MACS2 的 `cimport numpy` 旧语法（`'numpy/uint32_t.pxd' not found`）
- **MACS3 也失败** — 需要 VC++ 14.0 构建工具
- **conda install 不可靠** — conda 环境损坏时会静默失败
- **解决方案**：用 ArchR 的 `addTileMatrix(tileSize=500)` 替代 `addReproduciblePeakSet()`，无需 MACS2。差异分析用 `useMatrix = "TileMatrix"`。详见 `references/macs2-windows-fallback.md`

### 🟡 运行相关
- **ArchR Arrow 文件是自定义格式** — 不是 Apache Arrow IPC 也不是 Parquet。只能用 ArchR 包读取，pyarrow 读不了
- **Windows 必须 threads=1** — ArchR 并行依赖 `mclapply`（Unix fork），Windows 无 fork → `addArchRThreads(threads=1)` 是强制要求。多线程会随机崩溃，日志无明确错误，极易误诊为内存问题。所有脚本开头必须显式设置
- **BiocManager::install 输出缓冲** — 大包下载时 R 缓冲所有输出，看起来像卡住了但实际在下载。通过检查库目录的包数量判断进度

### 🔴 Bash+R segfault (exit 139) — 策略矩阵（cmd.exe /c vs bash 直接）

**现象**：在 MSYS2/git-bash 下跑 `Rscript` 偶发 segfault (exit code 139)，readRDS 大文件时概率最高。`terminal(background=True)` **不能** 解决此问题（已验证无效）。

**根因**：bash 与 R 的动态库加载器冲突，ArchR 加载 rhdf5/Matrix 等包时触发。

**策略矩阵（路径含中文时 cmd.exe /c 不可靠，必须在两害间选择）**：

| 场景 | 方案 | 可靠性 |
|------|------|:---:|
| 路径纯 ASCII，单样本/少量样本 | cmd.exe /c + .bat（纯 ASCII）| ✅ 最高（绕过 bash segfault） |
| 路径含中文（`E:\专利\...`），批量 40 样本需幂等重试 | bash 直接调 Rscript.exe | ✅ 可行（偶发 segfault 可幂等重试，优于 cmd GBK 确定性失败） |
| 完全不用 shell | `execute_r()` 工具 | ✅ 最安全（Hermes 内部直接调 R，不走终端 shell） |

> ⚠️ **cmd.exe /c 的铁律（2026-08-07 40 样本批量实测）**：.bat 文件内容**必须纯 ASCII**。中文路径放 R 脚本内部处理（R UTF-8 无碍），bat 只传 ASCII sample_id 参数。违反此条 → `'tarted:' 不是内部或外部命令` / EXIT_CODE=9009。详见下方 `.bat 文件含中文路径` 条目。

**方案 A：cmd.exe /c + 纯 ASCII .bat（首选，路径无中文时）**：

```bash
# ❌ 不行 — bash 中直接跑 R，高概率 segfault
Rscript script.R

# ✅ 可行 — cmd.exe 包装
cmd.exe /c "E:\path\to\run.bat"
```

`.bat` 包装模板：
```bat
@echo off
echo Started: %DATE% %TIME%
"C:\Program Files\R\R-4.5.3\bin\Rscript.exe" "E:\path\to\script.R" > "E:\path\to\output.log" 2>&1
echo EXIT_CODE=%ERRORLEVEL%
echo Finished: %DATE% %TIME%
```

Terminal 调用方式（Hermes）：
```
terminal(command='cmd.exe /c "E:\\path\\to\\run.bat"', background=True, notify_on_complete=True, timeout=3600)
```

> ⚠️ `terminal(background=True)` 仍走 bash → Rscript，segfault 照旧。**必须** cmd.exe 包装。

### 🔴 非人类基因组 / NCBI 染色体命名 — 2026-07-29 已验证

**现象**：
- `addTileMatrix()` → 明确报错 `Chromosome chr1 not in ArrowFile! Available: NC_088375.1, NC_088376.1, ...`
- `addGroupCoverages()` → **静默崩溃** exit_code=1，无报错信息，只完成了部分组（如 21/57）
- `addArchRGenome("hg38")` 调用时不报错，但所有下游函数失败

**根因**：Arrow 文件使用 NCBI RefSeq 染色体命名（如食蟹猴 T2T 组装的 `NC_088375.1`），而 `addArchRGenome("hg38")` 构建 UCSC 命名（`chr1`）。染色体名不匹配 → ArchR 找不到数据。

### 🔴 物种身份验证（染色体 accession → NCBI 查证）— 2026-08-02 已验证

**现象**：分析全程假设猴数据是 *Macaca mulatta*（猕猴），但 `query_ncbi(db="nuccore", query="NC_088375.1[Accession]")` 返回 **Macaca fascicularis**（食蟹猴）isolate 582-1 chromosome 1, **T2T-MFA8v1.1**，length 234,122,563。文件名/目录名/旧记忆都可能误导物种假设。

**影响**（跨物种专利/分析致命）：
- **LiftOver chain 选择错误** — rheMac10/rheMac8 是 *mulatta* 的 chain；*fascicularis* 需要 T2T-MFA8v1.1 → hg38 的 chain（UCSC 需按 MFA8 组装找）。用错 chain = 坐标映射全错。
- **直系同源映射错误** — ortholog 配对表按物种选择（human↔mulatta vs human↔fascicularis），用错物种丢失/错配直系同源 CRE。
  - **ortholog 映射唯一可靠通道（2026-08-08 实测）**：NCBI **eutils efetch XML API**（`eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=gene&id={GeneID}&retmode=xml`）的 `Orthologs from Annotation Pipeline` 段（直接给 human GeneID+symbol）。⚠️ 网页端 `/gene/{id}/?report=xml` **曾可用但 2026-08-08 实测 500 被限流，勿再依赖**。❌ Ensembl Compara 不可用（Ensembl 食蟹猴注释是 Macaca_fascicularis_6.0 组装，与 T2T-MFA8v1.1 坐标不兼容）；❌ mygene homologene 无食蟹猴 9541（只有恒河猴 9544）；❌ NCBI datasets ortholog API 404；❌ 网页爬虫 403。human GeneID → hg38 坐标走 esummary（注意其 genomicinfo 是 **GRCh37**，chraccver .14/.12 后缀）→ `pyliftover.LiftOver('hg19','hg38')` 转 hg38。完整通道表 + 批量脚本 → cross-species-atac-conservation `references/ortholog-mapping-2026-08.md`
- **专利权利要求物种错误** — 交底书/权利要求写"猕猴"而数据是"食蟹猴"→ 实施例与权要不一致，审查员可质疑。

**验证方法（每批新数据必须先做，<1 min）**：
```
query_ncbi(db="nuccore", query="<任意染色体 accession>[Accession]")
# 例: query="NC_088375.1[Accession]" → 返回 organism + assembly 名 + length
# 与 macaque_chrom_sizes.json / Arrow TileMatrix params 中的 length 对比确认同一组装
```

> ⚠️ **铁律**：**任何跨物种分析的物种身份，必须用染色体 accession 查 NCBI nuccore 确认**，不能靠文件夹名、GEO 摘要、旧记忆假设。物种错了，下游 chain/ortholog/权利要求全错。

**修复（最小侵入式 — 2026-07-29 食蟹猴 scATAC 验证）**：

```r
# ❌ 不要用 createGenomeAnnotation — 强制 BSgenome lookup → 报错退出
# ❌ 不要用 SimpleList — ArchR 内部方法不识别自定义 S3 类
# ✅ 直接替换已有 hg38 genome annotation 的 chromSizes（最小侵入）
library(ArchR); addArchRGenome("hg38")     # 初始化环境
proj <- readRDS("project_clustered.rds")

mac_chrom_gr <- GRanges(
  seqnames = c("NC_088375.1", "NC_088376.1", ...),
  ranges = IRanges(start=1, end=c(234122563, ...))
)
proj@genomeAnnotation$genome <- "Macaca_fascicularis"
proj@genomeAnnotation$chromSizes <- mac_chrom_gr
proj@geneAnnotation$genome <- "Macaca_fascicularis"
# ✅ addTileMatrix + getMarkerFeatures 全部正常工作
```

**染色体大小提取**：Python 脚本从 Arrow HDF5 读取 `TileMatrix/Info/Params`：
```python
import h5py, json
with h5py.File("sample.arrow", "r") as f:
    params = json.loads(f["TileMatrix"]["Info"]["Params"][()])
    chrom_sizes = {c: s for c, s in zip(params["chromosomes"], params["chromosomeLengths"])}
```

完整流程见 `references/custom-genome-non-ucsc.md`。

> ⚠️ **调试铁律**：优先测 `addTileMatrix` — 它有明确报错信息（`Chromosome chr1 not in ArrowFile! Available: NC_088...`）。`addGroupCoverages` **也会因为同样原因静默崩溃** — 以前被误诊为内存问题。2026-07-29 验证：修复基因组后 TileMatrix 3 样本×21 chr → 全部通过，getMarkerFeatures 6M tiles → 产出 50 个 DA tiles。

### 🟡 中文路径导致 terminal() workdir 被拦截

**两种崩溃模式**：

| 模式 | 现象 | 根因 |
|------|------|------|
| **Foreground 超时** | 跑到 18-23/57 后静默消失，无 error、无 coredump | `terminal()` foreground 600s 硬限 → 进程被系统 kill。57 组需 ~14 min |
| **Bash segfault** | 随机 exit 139，或"hang"（进程存活但日志停） | MSYS bash 与 R 动态库加载器冲突，多组时概率最高 |

### 🔴 .bat 文件含中文路径 → cmd GBK 解析乱码（EXIT_CODE=9009）— 2026-08-07 已验证

**现象**：write_file 生成的 .bat 内含 `E:\专利\...` 中文路径，用 `cmd.exe /c run.bat` 执行报 `'tarted:' 不是内部或外部命令` / `'ogram' 不是内部或外部命令`，EXIT_CODE=9009（命令找不到）。看似 Rscript 没启动，实际是 bat 本身被解析坏了。

**根因**：write_file 输出 UTF-8 编码 .bat，而 Windows cmd 默认 GBK 代码页解析 bat 内容 → 中文路径乱码 → 引号/命令被拆坏（`Program Files` 变 `'ogram'`，`Started:` 变 `'tarted:'`）。

**修复**：**.bat 保持纯 ASCII** —— bat 里只传 sample_id（ASCII 参数），中文路径（frag_root/out_root/输出目录）全部放 R 脚本内部默认参数处理：
```bat
@echo off
"C:\Program Files\R\R-4.5.3\bin\Rscript.exe" "E:\MemOmics-Agent\results\xxx\create_arrow_qc.R" GSM8549615_hc77 > "E:\MemOmics-Agent\results\xxx\log.txt" 2>&1
echo EXIT_CODE=%ERRORLEVEL%
```
R 脚本内：`out_root <- ifelse(length(args) >= 3, args[3], "E:/专利/.../ArchR_Arrow_QC")` —— 中文路径只存在于 R 代码里（R 4.5.3 UTF-8 内部处理无碍），bat 全 ASCII → 已验证可行。

**批量并发进程监控（2026-08-07 实测）**：每个样本实际 spawn **2 个 Rscript 进程**：
- `bin\Rscript.exe`（launcher，~7.7MB 内存，父进程）
- `bin\x64\Rscript.exe`（实际 worker，1.5-2.4GB，子进程）

所以 N 个样本并发 = **2N 个 Rscript 进程**，这是**正常现象**，不是并发失控。判断真实并发只看：① `ls batch/*.bat | wc -l`（已生成 bat 数）② worker 进程数（内存 >100MB 的 x64 Rscript 数）。bash `jobs -r | wc -l` 在 git-bash 下对 cmd.exe 包装可能计数不可靠 — 不要用它判断并发。

**修复（必须 background + cmd.exe /c 双管齐下）**：

```bash
# ✅ 唯一可靠方式 — background + cmd.exe 绕过 bash + 超长 timeout
terminal(command='cmd.exe /c "\"C:/Program Files/R/R-4.5.3/bin/Rscript.exe\" script.R > log.txt 2>&1"',
         background=True, notify_on_complete=True, timeout=3600)
```

**修复（首选 groupBy="Sample" 减少组数）**：3 组 vs 57 组，~6min，且回避 bash 崩溃窗口
```r
# ✅ groupBy="Sample" 只需 3 组
proj <- addGroupCoverages(proj, groupBy = "Sample", force = TRUE)
saveRDS(proj, "project_cov.rds")
# TileMatrix + getMarkerFeatures(useMatrix="TileMatrix", groupBy="AgeGroup") 正常工作
```

**替代（必须 per-cluster 时）**：手动循环 1 个 cluster 1 次
```r
for(cl in unique(proj$Clusters)) {
  sub <- addGroupCoverages(proj[proj$Clusters==cl,], groupBy="Sample", force=TRUE)
  saveRDS(sub, paste0("cov_C", cl, ".rds"))
}
```

**⚠️ 已生成的 coverage .h5 无法被 `force=FALSE` 复用**：若 `project_clustered.rds` 在 `addGroupCoverages` 之前保存，重载后 ArchRProject 不含 coverage 元数据 → `force=FALSE` 检测不到已有文件 → 重新生成全部。结论：必须 `saveRDS(proj, "project_cov.rds")` 紧跟 `addGroupCoverages`。

**📡 进度监控与卡死检测**：addGroupCoverages 运行时，ArchRLogs 目录（`ArchRLogs/ArchR-addGroupCoverages-*.log`）包含逐染色体的详细进度（`Group X of Y : Processed Fragments Chr (A of 21)`），比 stdout 更精确。心跳脚本应监控 ArchR log 而非脚本 stdout。卡死判定：ArchR log 行数在 >2 个心跳间隔（>4 分钟）无变化。完整监控指南 → `references/coverage-progress-monitoring.md`

### 🟢 getMarkerFeatures 结果验收基准 — 2026-07-29 猕猴海马验证

**正常产出（食蟹猴 3 样本/36K cells/21 clusters，基因组修复后）**：
| 指标 | 值 |
|------|-----|
| TileMatrix tiles | 6,085,841 (500bp × 21 chr × 3 samples) |
| getMarkerFeatures 耗时 | ~3 min (2 pairwise comparisons) |
| DA tiles (strict: FDR<0.05, \|FC\|>0.5) | 50 (Old: 19 Up/31 Down) |
| DA tiles (loose: FDR<0.1, \|FC\|>0.25) | 122 (Old: 55, Young: 67) |
| markers_age_tiles.rds | 183MB |

> 如果 `getMarkerFeatures` 返回全零且你确认基因组正确 → 仍需排查。下面是全零诊断流程：

### 🟡 getMarkers 输出结构（DFrame 而非 GRanges）— BED 导出陷阱 — 2026-08-02 已验证

**现象**：`getMarkers(markers_age, cutOff=...)` 返回 `list(loose, strict)` → 每项是 `SimpleList(Old, Young)` → 元素是 **DFrame**（非 GRanges！），列为 `seqnames, idx, start, Log2FC, FDR, MeanDiff`。`as.data.frame(gr)[, c("seqnames","start","end")]` 会报错 — **没有 `end` 列**。

**正确的 BED 导出（跨物种 LiftOver 输入）**：
```r
da <- readRDS("da_tiles.rds")
loose <- da$loose                    # SimpleList
df <- as.data.frame(loose[["Old"]]) # DFrame → data.frame
# TileMatrix 500bp: end = start + 500 - 1
bed <- data.frame(chr=as.character(df$seqnames),
                  start=df$start - 1,   # BED 是 0-based
                  end=df$start + 500 - 1)
write.table(bed, "da_tiles_Old.bed", sep="\t", row.names=FALSE, col.names=FALSE, quote=FALSE)
```

> ⚠️ `da$loose[[grp]]` 这种链式 `$`+`[[` 在 SimpleList 上会报 "this S4 class is not subsettable" — 必须先 `loose <- da$loose` 再 `loose[[grp]]`。

### 🔴 getMarkerFeatures 全零结果诊断 — 2026-07-29 已验证

**现象**：`getMarkerFeatures(useMatrix="TileMatrix", groupBy="AgeGroup")` 返回**所有 tile log2FC=0, FDR=1, pval=1**，稀疏矩阵 5×5 全为空（`.`）。总 tile 数正常（25 万/染色体），但无任何差异可及性。

**已触发条件**（猴海马 scATAC, 2026-07-29）：
- 3 样本: Old=1 (O1_Hip_1), Young=2 (Y3_Hip_1, Y3_Hip_2)
- 35,879 cells, 21 clusters, nFrags>1000+TSS≥4
- `addTileMatrix(tileSize=500)` → `getMarkerFeatures(groupBy="AgeGroup", testMethod="wilcoxon")`
- 食蟹猴 T2T 基因组 (NCBI NC_088xxx), 非 UCSC 命名

**根因分析（3 种可能，按概率排序）**：

| # | 可能原因 | 概率 | 诊断方法 |
|---|---------|:---:|---------|
| 1 | **样本量不足** — Wilcoxon 对 Old=1 vs Young=2 无统计功效 | ⭐⭐⭐ | `table(proj$AgeGroup)` 看每组样本数 |
| 2 | **TileMatrix 过于稀疏** — 500bp tile 中 ATAC 信号极低（SparseMatrix `NonZeroEntries` 占比 <0.1%） | ⭐⭐ | 检查 `mean1`/`mean2` 列是否全为 0 — 全 0 说明矩阵真的是空 |
| 3 | **基因组命名不匹配** — `addArchRGenome("hg38")` 但 Arrow 是 NCBI 命名 → TileMatrix 建在错误坐标上 | ⭐ | `head(rownames(getMatrixFromProject(proj, "TileMatrix")))` 检查 tile 名 |

**修复流程**：

```r
# Step 1: 确认问题类型
markers_age <- readRDS("markers_age_tiles.rds")
assay(markers_age)[1:10, 1:5]  # 全 0? → 问题 1 或 2
rowData(markers_age)$mean[1:10]  # 全 0? → TileMatrix 真的是空 (问题 2)

# Step 2: 尝试放宽阈值检查是否有微弱信号
da_loose <- getMarkers(markers_age, cutOff = "FDR <= 0.1 & abs(Log2FC) >= 0.1")
# 如果 da_loose 也是空 → 确认是统计功效问题

# Step 3: 替代方案
# A. 改用 groupBy="Sample" (3组) 而非 "AgeGroup" (2组) — 提高 group 数
# B. 降 tileSize 到 100bp → 更密集、更灵敏
# C. 增加样本 (需要更多 Arrow 文件)
# D. 换 pseudobulk DESeq2 按个体聚合 → 每个 cluster×sample 一个 pseudobulk
```

> ⚠️ **不要直接断定"生物学无差异"** — 绝大多数全零结果是统计功效问题而非真阴性。先诊断再下结论。完整诊断决策树见 `references/getmarkerfeatures-all-zero-diagnostic.md`。

### 🔴 markerPlot DA 可视化崩溃 — 2026-07-29 已验证

**现象**：`markerPlot()` 对 TileMatrix SummarizedExperiment 产生 0 字节 PDF / 无输出 / 超时。

**根因**：
1. **markerPlot 已废用** — ArchR 1.0.3 明确警告 `markerPlot不再有用，请用'plotMarkers'`
2. markerPlot 对大 SE（>100 万 tile）不稳定。PDF 矢量格式为每个点生成独立路径 → 6M 点 = 130MB+ 文件 → 600s 超时

**回退方案**：从 `assay(se, "Log2FC"/"FDR")` 直接提取矩阵 → base R `plot()` 生成 PNG/PDF。<10 秒完成，无需 ggplot2。完整模板见 `references/da-plotting-fallback.md`。

```r
# 最小火山图（base R, <5s for 6M points）
markers <- readRDS("markers_age_tiles.rds")
comp_name <- colnames(assay(markers, "Log2FC"))[1]  # e.g. "Old"
log2fc <- assay(markers, "Log2FC")[, comp_name]
fdr <- assay(markers, "FDR")[, comp_name]
negLog10FDR <- -log10(fdr + 1e-300)

png("volcano.png", width=1600, height=1400, res=200)
sig <- rep(rgb(0.7,0.7,0.7,0.4), length(log2fc))
sig[fdr<0.05 & log2fc>0.5] <- rgb(0.9,0.2,0.2,0.6)
sig[fdr<0.05 & log2fc<(-0.5)] <- rgb(0.2,0.3,0.9,0.6)
plot(log2fc, negLog10FDR, col=sig, pch=16, cex=0.4,
     xlab="Log2FC", ylab="-log10(FDR)", main=comp_name)
abline(h=-log10(0.05), lty=2, col="grey40")
abline(v=c(-0.5,0.5), lty=2, col="grey40")
dev.off()
```

### 🔴 filterDoublets 就地过滤 — 没有 DoubletFilter 列 — 2026-08-07 已验证

**现象**：`filterDoublets(proj, filterRatio=2)` 运行后（日志显示 `Filtering 539 cells from ArchRProject!`），紧接着 `proj[proj$DoubletFilter == "Keep", ]` 报错：
```
错误于`[.ArchRProject`(proj, proj$DoubletFilter == "Keep", ):
  Incorrect number of logical values provided to subset cells
```

**根因**：**ArchR 1.0.3 的 `filterDoublets()` 是就地过滤** — 直接删除被判为双联的细胞，**不会**在 cellColData 添加 `DoubletFilter` 列（也没有 "Keep"/"Doublet" 值）。过滤后 project 里已经没有 Doublet 细胞，`proj$DoubletFilter` 返回空 → 子集操作报 "Incorrect number of logical values"。

**正确写法**（filterDoublets 前后各记一次 nrow，差值即双联数；过滤后直接保存，不要再子集）：
```r
n_before <- nrow(getCellColData(proj))        # 过滤前记录
proj <- filterDoublets(proj, filterRatio = 2) # 就地过滤，直接返回已过滤 project
n_after <- nrow(getCellColData(proj))         # 过滤后
n_doublet <- n_before - n_after               # 双联数 = 差值（也可从日志 "Filtering X cells" 读）
# ⛔ 保存走 copy Arrow + CSV（2026-08-07 实测）：saveArchRProject 会递归嵌套目录爆炸（见下方专门条目），完全弃用
dir.create(file.path(out_filtered, sample_id), recursive=TRUE)
file.copy(arrow_file, file.path(out_filtered, sample_id, paste0(sample_id, ".arrow")), overwrite=TRUE)
keep_df <- as.data.frame(getCellColData(proj))
keep_df$DoubletFilter <- "Keep"  # 过滤后剩余细胞全为 Keep（约定列，非 ArchR 元数据）
write.csv(keep_df, file.path(out_filtered, sample_id, paste0(sample_id, "_filtered_cells.csv")), row.names=FALSE)
```

> ⚠️ 对应地：`addDoubletScores()` 添加的是 `DoubletScore` / `DoubletEnrichment` 列，`filterDoublets()` 本身不加任何列。想保留 doublet 标记做后续分析（如对比 Keep vs Doublet 的 QC）时，必须在 `filterDoublets` **之前**从 cellColData 自行提取并另存。

**⚠️ 统计列陷阱（2026-08-07 实测）**：即使按上述正确写法跑，`sum(proj$DoubletFilter == "Doublet", na.rm=TRUE)` 也**恒返回 0** —— filterDoublets 后该列根本不存在，sum(NULL) 返回 0。result.csv 会出现 `n_doublet=0, doublet_rate=0%` 的假象（hc77 实际过滤了 295 cells，7.68%，但报告 0%）。**doublet 数必须用过滤前后细胞数差**：
```r
n_before_doublet <- nrow(getCellColData(proj))
proj <- filterDoublets(proj, filterRatio = 2)
n_cells_after <- nrow(getCellColData(proj))
n_doublet <- n_before_doublet - n_cells_after   # ← 唯一的可靠算法
```
filtered_cells.csv 里手动补 `DoubletFilter="Keep"` 列是给 P4 merge 用的约定，不是 ArchR 元数据。

### 🔴 saveArchRProject 递归嵌套目录爆炸 — 2026-08-07 已验证

**现象**：`saveArchRProject(proj, outputDirectory=FilteredProjects/<sample>)` 后目录无限嵌套：
```
FilteredProjects/<sample>/FilteredProjects/<sample>/FilteredProjects/<sample>/...
```
单样本从 0.86GB 膨胀到 5.7GB（4-5 层嵌套）。日志可见 `Copying Other Files (3 of 10): FilteredProjects`。

**根因**：saveArchRProject 会把 project 的 outputDirectory 下**所有非标准文件**当 "Other Files" 递归复制到新目录。如果：
1. `FilteredProjects/` 位于 project outputDirectory **内部** → 保存时它自己也在"Other Files"列表里 → 复制到自己里面 → 无限递归
2. 即使输出目录移到外部，**源目录**里已有的嵌套 `FilteredProjects/` 也会被当作 Other Files 复制过去 → 嵌套扩散到新目录

**修复（完全弃用 saveArchRProject 保存过滤结果）**：
```r
# ❌ 不要这样（会嵌套）
saveArchRProject(proj, outputDirectory=file.path(out_root, "FilteredProjects", sample_id))

# ✅ 改为: copy Arrow + 导出过滤 cell 名单 CSV
dir.create(file.path(out_filtered, sample_id), recursive=TRUE)
file.copy(arrow_file, file.path(out_filtered, sample_id, paste0(sample_id, ".arrow")), overwrite=TRUE)
avail_cols <- intersect(c("TSSEnrichment","nFrags","DoubletScore","DoubletEnrichment","DoubletFilter"),
                        colnames(getCellColData(proj)))
keep_df <- as.data.frame(getCellColData(proj, select=avail_cols))
keep_df$cellNames <- rownames(keep_df)
keep_df$DoubletFilter <- "Keep"  # filterDoublets 后剩余细胞全为 Keep
write.csv(keep_df, file.path(out_filtered, sample_id, paste0(sample_id, "_filtered_cells.csv")), row.names=FALSE)
```
产物：过滤后 Arrow（可直接 P4 merge）+ 过滤名单 CSV。零嵌套、磁盘省一半（不复制 ArchRLogs/QC pdf/rds）。

**⚠️ 残留嵌套清理**：一旦嵌套已发生，即使修好脚本，源目录里的嵌套 `FilteredProjects/` 仍会被后续 save 复制 → 必须先清理残留嵌套目录（征求用户同意后删除）再跑。

### 🔴 P4 merge 必须按 `_filtered_cells.csv` 子集——filtered Arrow 未剔除 doublet（2026-08-08 实测）

**现象**：QC 完成 40/40 后，merge 4 个 `ArchR_Arrow_QC_Filtered/{s}/{s}.arrow`，nCells = 35,787，但 QC 表 Keep 合计 = 29,357（差 6,430 = 18% doublet）。

**根因（字节级证据）**：`ArchR_Arrow_QC_Filtered/{s}/{s}.arrow` 与 `ArchR_Arrow_QC/{s}.arrow` **大小完全一致**（如 hc78 均 1,699,339,637 字节）——**copy 的是过滤前的 Arrow**，doublet 从未从 Arrow 剔除！过滤结果只记录在 `{s}_filtered_cells.csv`（含 `cellNames` + `DoubletFilter="Keep"` 列，行数 = Keep 数）。

**正确 merge（必须子集）**：
```r
proj <- ArchRProject(ArrowFiles = arrow_files, ...)  # 含全部 QC-pass 细胞（含 doublet）
keep_cells <- c()
for (s in samples) {
  df <- read.csv(file.path(keep_dir, s, paste0(s, "_filtered_cells.csv")))
  keep_cells <- c(keep_cells, df$cellNames[df$DoubletFilter == "Keep"])
}
proj <- proj[keep_cells, ]   # cellNames 格式 sample#barcode，与 ArchR 一致可直接子集
```

> ⚠️ 这是 QC 设计约定（copy Arrow + CSV 记录过滤名单），不是 bug，但 merge 漏子集 = doublet 混入聚类 → 下游 DA/跨物种对比污染。**所有 merge 前必须做此子集。**

### 🟢 addGeneScoreMatrix 耗时 ~10-20min（35K cells）— 必须 background + checkpoint（2026-08-08 实测）

**现象**：注释前加 GeneScoreMatrix，foreground terminal 600s 超时被杀（实际日志显示 7.7min 还在 "Computing Gene Scores"，计算未完成）。

**经验**：
- addGeneScoreMatrix 对 ~35K cells 需 10-20 分钟（逐染色体扫描全基因组）——**必须 `background=True + notify_on_complete=True`，timeout≥3600**，不要 foreground 跑
- 脚本必须带 checkpoint：`if (file.exists(genescore_rds)) { proj <- readRDS(genescore_rds) } else { proj <- addGeneScoreMatrix(...); saveRDS(proj, genescore_rds) }` —— 被杀后可续跑不重算
- 卡死判定：ArchRLogs/ArchR-addGeneScoreMatrix-*.log 的 "Computing Gene Scores using distance relative to GeneBody!" 每 ~4min 重复一条 = 正常计算中，不是卡死

### 🔴 addGeneScoreMatrix Windows 崩溃（连续 2 次）→ TileMatrix marker 注释替代（2026-08-08 实测）

**现象**：P0 人侧注释阶段，`addGeneScoreMatrix` 连续崩溃 2 次（02→02b 迭代，即便 background + checkpoint 也保不住，日志停在 "Computing Gene Scores..."）。**弃用**，改用 TileMatrix（500bp bins，01 阶段 addTileMatrix 已生成，存在于 Arrow，零额外计算）做 8 大类 marker 注释——marker 基因 TSS±2kb 内 tile 的 binarized 平均覆盖度 = 简化版 gene score。

**替代方案**（02e_annotate_human_tile2.R 修复版，已验证可跑，35,787 cells / 17 clusters 秒级出结果）：

> ⚠️ **02c 首版崩溃根因（2026-08-08 21:46 实测）**：`rowRanges(tile)` 返回 **NULL** → `findOverlaps(win, tile_gr)` 报 `错误: 函数'findOverlaps'标签'query = "GRanges", subject = "NULL"'找不到继承方法`。ArchR 1.0.3 `getMatrixFromProject(proj,"TileMatrix",binarize=TRUE)` 返回的 SummarizedExperiment **rowRanges 槽是空的**（TileMatrix 只存 assay），必须用 `getFeatures(proj, useMatrix="TileMatrix")` 获取坐标（直接返回 GRanges，chr1:0-499 格式，606 万条）。

```r
# 1. TileMatrix（已存在，安全）— getMatrixFromProject 约 5 min
tile <- getMatrixFromProject(proj, "TileMatrix", binarize = TRUE)
tile_mat <- assay(tile)
# 2. ⚠️ tile GRanges 必须用 getFeatures()，不能 rowRanges(tile)（返回 NULL！）
tile_gr <- getFeatures(proj, useMatrix = "TileMatrix")   # GRanges 606万 500bp bins
stopifnot(nrow(tile_mat) == length(tile_gr))             # 行序对齐验证
# 3. hg38 基因坐标
geneAnno <- getGeneAnnotation(proj)$genes; gn <- mcols(geneAnno)$symbol
# 4. marker 基因 → TSS±2kb 内 tile 索引
gene_tile_idx <- function(gene_symbols, geneAnno, tile_gr) {
  hits <- which(mcols(geneAnno)$symbol %in% gene_symbols)
  if (length(hits) == 0) return(integer(0))
  tss_gr <- resize(geneAnno[hits], width = 1, fix = "start")
  win <- resize(tss_gr, width = 4001, fix = "center")   # TSS±2kb
  unique(subjectHits(findOverlaps(win, tile_gr)))
}
# 5. 每 cluster × 每类别 = binarized 平均覆盖度
# 6. 注释 = 类别 argmax；写回 proj$CellType → saveRDS + CSV + UMAP
```

**完整脚本** → `templates/annotate_human_tilematrix.R`（8 大类 marker 列表含 Ex/Inh/Astro/Micro/OPC/ODC/VS/ChP，可直接改 marker 复用）。

> ⚠️ 此方案只适合"粗注释"（cluster→8 大类），精度低于 gene score + 标签转移，但 Windows 上稳定性碾压 addGeneScoreMatrix。猴-人跨物种注释对齐时，两侧必须用**同一套 marker 列表**保证可比。

### 🔴 更优替代：Python 直读 Arrow TileMatrix CSC（02d 方案，2026-08-08 实测）— 完全绕开 getMatrixFromProject OOM

**场景**：02e R 方案仍要 `getMatrixFromProject(proj, "TileMatrix", binarize=TRUE)` 加载全量 606 万 tile × 3.5 万 cells 矩阵（~20GB 内存、5+ min、易 OOM/静默期）。02d 改用 **h5py 直读 Arrow 里 TileMatrix 的 CSC 稀疏结构**，只取 marker 基因 TSS±2kb 对应的 ~280 个 tile 行 → 秒级完成、内存 <1GB、无需 R/ArchR 全矩阵加载。

**Arrow TileMatrix 内部结构（h5py 读取要点，02d 实测）**：
- 存储为 CSC（按列压缩）：每组 `TileMatrix/{chr}` 下有 `shape / indptr / indices / data` 四个数据集
- `shape = (n_tiles_chr, n_cells_chr)`；**`indptr` 长度 = n_cells_chr+1**（按列），`indices[indptr[j]:indptr[j+1]]` = cell j 的非零 tile **局部行号**（局部于该 chr）
- tile 全局坐标 = chr + 局部行号 × tileSize（500bp）；tile 名 `chr1:0-499` 格式 = seqnames:start-end
- 细胞名：`Metadata/CellNames` 里的 barcode 需拼前缀 `{sample}#` 才能与 ArchR cellNames 对上

**02d 流程（Python，完整脚本见 GSE278576 项目 02d_tile_annotation.py）**：
```python
# 1. hg38 TSS 表（ArchR getGeneAnnotation 导出一次缓存成 tsv）
# 2. 每 celltype 预计算 marker TSS±2kb → {chr: set(局部行号)}
# 3. 逐 Arrow 逐 chr 读 CSC：遍历每 cell 的非零行，命中 marker 行则累加分数
# 4. 归一化（分数 / 该类总 tile 数）→ argmax → cell-level CellType
# 5. 输出 human_cluster_annotation.csv (cluster级) + human_celltype_scores.csv (cell级) + celltype_map.json
```
- **产出验证**：cell 级 CSV 行数 = nCells+1（header）；`celltype_map.json` 是 **json.dump 单行** → `wc -l` 显示 0 **不代表空文件**（用 `ls -la` 看字节数 / python json.load 验证，别用 wc -l 判空）。
- **适用前提**：只做 marker 区域注释时够用；需要全矩阵（如全基因组 footprinting/DA）仍必须 getMatrixFromProject。
- 2026-08-08 实测产出：35,787 cells → 8 大类（OPC 12032/ODC 7752/Ex 7001/Astro 4557/Micro 1661/Inh 1321/VS 887/ChP 576），与猴侧同一套 marker 列表对齐。

### 🔴 TileMatrix marker 注释验收陷阱 — 全 0 scores / 全同一类别 / 进程死但旧 CSV 在（2026-08-08 实测）

**现象**：02e 注释脚本（getFeatures 修复版）运行后，`human_cluster_annotation.csv` 显示 **17 个 cluster 全部被注释为 "Ex"**（大脑皮层不可能 100% 兴奋性神经元 = 必错），cell-level scores CSV 全部 0.0。02e 日志停在 `VS : marker genes -> 36 tiles`（第 7/8 个类别，无 ChP、无 print(score_df)、无 `P0 DONE` 标记）→ **进程实际已死**（心跳 22:01 后不再写 = 心跳由主脚本 spawn，主进程死心跳也死）。但 22:00 生成的 CSV 文件仍在磁盘 → **"文件存在" ≠ "成功"**。

**根因候选（按概率排序）**：
| # | 原因 | 诊断 |
|---|------|------|
| 1 | **tile_mat 与 tile_gr 行序错位** — 日志显示 `tile_mat rownames head: NULL`：`stopifnot(nrow(tile_mat) == length(tile_gr))` 只验证行数，**验证不了行序**。rownames 为 NULL 时若 ArchR 内部行序 ≠ getFeatures() 返回顺序，findOverlaps 的 subjectHits 索引指向错误 tile → scores 全错 → argmax 全选第一个类别（Ex） | 打印 `head(rownames(tile_mat))`；若 NULL → 必须显式对齐 |
| 2 | **marker symbol 匹配失败** — geneAnno 的 symbol 列为 NULL 时回退 gene_id，与 marker 基因名不匹配 → idx 为空 → score 全 0/NA | 打印 `gene_tile_idx("SLC17A7", ...)` 是否 >0 |
| 3 | **进程中途死亡** — 日志停在 VS 无后续（OOM / taskkill / bash segfault），CSV 是**上一次失败运行**的残留 | 对比 CSV mtime 与日志末尾时间戳 |

**验收红线（每次注释后必须逐项检查，全过才算 P0 完成）**：
1. ✅ 每个 cluster 的 8 类 scores **不是全 0**（`summary(score_mat)` 看分布）
2. ✅ 注释类别数 **≥ 2**（17 个 cluster 全同一类 = 必错，直接判失败）
3. ✅ 日志有完整结束标记（`print(score_df)` + `P0 DONE`），不是停在中间类别
4. ✅ CSV 列名与脚本 `write.csv(score_df)` 输出格式一致（9 列 `cluster,Ex,...,CellType`）；若磁盘 CSV 是 3 列汇总/不同格式 = **不是本次运行的产物**，是残留，不能当结果
5. ✅ 进程已自然退出（tasklist 无 Rscript）且有完成日志

**修复方向**：
- 行序对齐验证（rownames 为 NULL 时）：`stopifnot(nrow(tile_mat) == length(tile_gr))` 之外，加 `if(!is.null(rownames(tile_mat))) stopifnot(all(rownames(tile_mat) == paste0(as.character(seqnames(tile_gr)), ":", start(tile_gr), "-", end(tile_gr))))`
- 先用 1-2 个已知 marker（如 SLC17A7=Ex、MBP=ODC）打印其 tile 索引和覆盖度，验证通路再跑全类别
- 进程死亡后先 `tasklist | grep Rscript` 确认无残留，再决定是否重跑（重跑前不要信任磁盘上任何旧 CSV）

### ✅ 行序错位已排除 — 真因是方法灵敏度（2026-08-08 02h 诊断实测）

**诊断结论**：`getMatrixFromArrow`/`getMatrixFromProject` 返回 SE 的 `rownames` 与 `rowRanges` 均 NULL，但 **`rowData(tile)` 有 `seqnames, idx, start` 三列 = 坐标锚点**。对比 `getFeatures()` 的 idx 与 `rowData()` 的 idx：前 5 行 `match=TRUE`（chr1:0/500/1000... 完全一致）→ **行序天然对齐，不是错位问题**。02e 全 OPC 的根因是 **binarized TSS±2kb 平均覆盖度绝对值极低（0.005-0.094），8 类 marker 分数拉不开 → argmax 被噪声主导**。因此：
- 坐标锚点首选 `rowData()`（与矩阵同源），不要依赖 `rownames()`（NULL）
- 全同一类注释 ≠ 行序 bug，先看分数分布再定

**`getMatrixFromArrow` 没有 `features` 参数（02f 实测）**：`getMatrixFromArrow(proj, useMatrix="TileMatrix", features=win)` 报 `参数没有用(features = win)`。签名只有 `ArrowFile / useMatrix / useSeqnames / excludeChr / cellNames / ArchRProj / binarize / verbose / logFile`。想按窗口提取只能 `useSeqnames` 过滤到染色体级，**不能精确到 TSS 窗口**——marker 注释只能全矩阵提取或走 Python h5py 直读 CSC（见上方 02d 方案）。

**R 陷阱**：`print(round(score_df, 4))` 对含字符列（`cluster`）的 data.frame 报 `数据框中的类似非数值的变量： cluster` → 必须 `round(score_df[, numeric_cols], 4)`，不能整表 round。

**验证门（必做，每次注释后）**：检查 `table(proj$CellType)` 分布是否符合组织预期（海马应 Ex 主导；肌肉应 Myofiber 主导；皮层不会 100% 同一类）。若某非主要类型占压倒性多数 → 红灯，按上述诊断顺序排查，不要直接采用 argmax 结果。02e 首跑 16/17=OPC（仅 C17=Astro）即被此门拦截。

### ⛔ 重跑 ArchR 脚本禁止在 shell 命令里 rm 旧产物（2026-08-08 实测）

重跑管线（修复参数后从头来）时，**不要**在 terminal 命令里写 `rm -f *.rds && rm -rf ArrowFiles IterativeLSI Embeddings` —— 会被删除保护拦截（用户铁律：绝不未经同意删除文件/目录），且命令整体失败、进程根本没启动。
正确做法：
1. 直接重跑 R 脚本——内部 `force=TRUE` 覆盖 + `saveRDS` 同名覆盖，不需要先删
2. 若确需清理旧产物（如嵌套 FilteredProjects 目录），先列出要删的文件/目录向用户确认，不要塞进重跑命令

### 🔴 addClusters 必须用 `input=` 参数（ArchR 1.0.3，2026-08-08 已验证）

**现象**：`addClusters(ArchRProj = proj, ...)` 报错 `错误: 'ArchRProj'的值没有`（object 'ArchRProj' not found），进程退出，但 UMAP 等前置步骤都成功。

**根因**：ArchR 1.0.3 addClusters 签名是 `function(input = NULL, ..., ArchRProj = NULL)`。内部逻辑：
```r
.validInput(input = ArchRProj, name = "ArchRProj", ...)
if (is(ArchRProj, "ArchRProject")) {
    message("When running addClusters 'input' param should be used for 'ArchRProj'...")
    input <- ArchRProj
    rm(ArchRProj)   # ← 删掉变量后，后续代码再引用 ArchRProj → object not found
    gc()
}
```
用 `ArchRProj=` 传入会走这个分支 → `rm(ArchRProj)` → 后续代码再引用 `ArchRProj` 变量 → 崩溃。官方 message 已明确提示用 `input` 参数。

**修复**：`proj <- addClusters(input = proj, reducedDims = "IterativeLSI", method = "Seurat", name = "Clusters", resolution = 0.5, force = TRUE)`

> ⚠️ 顺带注意：`getReducedDims(proj)` 返回 list 结构，不能用 `"IterativeLSI" %in% getReducedDims(proj)` 做存在性检查。UMAP 已生成 = IterativeLSI 必然存在（addUMAP 依赖 reducedDims），无需检查。

### 🔴 addGroupCoverages 命名不匹配陷阱

**现象**：之前成功生成过 coverage .h5 文件，重载 `project_clustered.rds` 后 `addGroupCoverages(force=FALSE)` 全部跳过，尝试重新生成所有文件 → 慢且可能崩溃。

**根因**：`project_clustered.rds` 在 `addGroupCoverages` **之前** 保存的。重载后 ArchRProject 不含 coverage 元数据，ArchR 不认识已有的 `.h5` 文件。即使文件存在磁盘上，`force=FALSE` 也无法跳过。

**修复策略**：
1. **分步保存 RDS**：每步完成后立即 `saveRDS`，不要等到分析结束
   ```r
   proj <- addGroupCoverages(proj, groupBy="Clusters")
   saveRDS(proj, "project_cov.rds")  # ← 立即保存！
   ```
2. 若已丢失 coverage 元数据 → 用 `force=TRUE` 从头重建（~15-20 min for 36K cells, 21 clusters）
3. 先运行诊断脚本检查：对比 `getCellColData(proj, "Sample")` 生成的文件名与磁盘上的 `.h5` 文件

### 🔴 addDoubletScores 日志静默期 — LSI后 doublet 模拟阶段无日志（2026-08-07 hc35 实测）

**现象**：`addDoubletScores` 日志在 LSI 聚类完成后（约 20:28:55，最后一行 `Creating Cluster Matrix`）**停止写入新条目**，文件大小冻结在 ~20KB，持续 3-5 分钟无变化。但 Rscript 进程仍然存活、内存正常（~2GB），磁盘 tmp/ 目录有活跃中间文件增长。

**根因**：ArchR 在 LSI2 完成后的 **doublet 模拟+投影阶段**（`Simulating and Projecting Doublets` + `Computing Doublet Enrichment`）不写详细日志。这是正常行为，不是卡死。

**判定方法**：
1. Rscript 进程存活 + 内存正常（>1GB）= 仍在计算
2. 日志文件冻结 + 磁盘 `ArchR_Arrow_QC/<sample>/` 目录出现 `-Doublet-Summary.pdf` 和 `-Doublet-Summary.rds` = P2 即将完成
3. **PID-change 探针**：Rscript PID 变化 = 已完成 + watchdog 自动续跑新样本（比逐行读日志快得多）

**误判风险**：日志冻结 3-5 分钟时容易被误判为"卡死"→ 错误的 kill+restart 会浪费已完成的 LSI 计算（~5min）。静默期结束后，日志从 20KB 跳到 ~34KB（写入 doublet 结果摘要）。

### 🟡 Windows PowerShell 进程监控 — 执行策略 + bash 转义双重陷阱（2026-08-07 唤醒 #35 发现）

**现象**：
1. `powershell -File "check_procs.ps1"` → `UnauthorizedAccess`（执行策略阻止）
2. `powershell -Command "Get-Process Rscript | Select ... $_.CPU ..."` → bash 将 `$_` 转义为 `/e/MemOmics-Agent.CPU`（路径拼接）

**修复**：
- **方案 A**（一次性）：`powershell -ExecutionPolicy Bypass -File "check_procs.ps1"` — 适合已写好的脚本
- **方案 B**（最可靠）：`write_file` 先写 .ps1 → `powershell -ExecutionPolicy Bypass -File` — 避免 bash 转义 `$_`
- **方案 C**（简单查询）：`tasklist /FI "IMAGENAME eq Rscript.exe"` — 不需要 PowerShell，bash 中直接可用
- **最小内存查询**：`tasklist /FI "IMAGENAME eq Rscript.exe" | grep rscript` 一行搞定，不触发任何转义问题

> ⚠️ 避免在 bash terminal 中内联复杂 PowerShell — `$_`、`$_.CPU`、`@{N=...}` 等语法 100% 被 MSYS bash 转义破坏。要么写 .ps1 文件跑，要么用 tasklist。

### 🔴 监控误报 — 输出目录计数 ≠ 样本完成（2026-08-07 唤醒 #30 发现）

- **症状**: 唤醒检查看到输出目录从 33→34，判定"hc19 ✅ 完成"，但 hc19 输出目录实际不存在。hc19.log 中明确记录 `.tmpToArrow ERROR` + ArrowFiles 列表为空 + 下游 `ArchRProject` 崩溃。目录总数的增加来自其他样本完成，hc19 被误报为完成且从未重试。
- **根因**: 唤醒只统计了输出目录总数（`ls -d GSM* | wc -l`），未逐样本验证日志中的 `=== DONE` 标记或 `ERROR` 关键字。数字增加 ≠ 指定样本成功。
- **修复（每个唤醒/进度检查必须执行）**:
  1. 统计目录数 → `done=N/40`
  2. **必须** `tail` 当前运行样本的 `.log` 文件，检查是否有 `=== DONE` 或 `ERROR`
  3. 交叉验证：`done` 目录列表 vs 预期的完成样本名列表（不是只比数字）
  4. 发现 ERROR → 立即将样本加回 `remaining.txt` 重试列表，不要等所有样本跑完
  5. `run_serial` 脚本的 `done` 判定也必须检查 exit code + 日志 `=== DONE` 行，不能只靠 `ls -d 目录` 存在性
- **教训**: 磁盘目录计数只告诉你"有 N 个目录"，不告诉你"哪些样本成功了"。必须逐样本日志验证。mid-run 唤醒协议中的"磁盘数 done=N/40"必须配套"最新完成的样本日志已确认 === DONE"。

### 🔴 `.tmpToArrow` 静默失败 — Arrow 创建失败但脚本继续执行（hc19 案例）

- **症状**: `createArrowFiles` 日志出现 `ERROR Found in .tmpToArrow for (<sample> : 1 of 1)`，但脚本继续输出 `>>> P1 done in 11.4 min`，ArrowFiles 列表为空。下游 `ArchRProject()` 报 `file.exists(): 'file'参数无效`（次级症状，非真因）。
- **根因**: `.tmpToArrow` 内部错误（fragment 文件损坏/tabix 索引问题/tmp 目录竞争），ArchR 吞掉具体错误只输出通用 ERROR。createArrowFiles 返回空列表 → 脚本继续执行 → 在 ArchRProject 处崩溃。
- **区分此错误与 tmp 竞争错误**: tmp 竞争错误（`.tabixToTmp: Cannot open file tmp-*.arrow`）发生在 P1 早期读 fragment 后写临时 Arrow 时；`.tmpToArrow` 错误发生在 Arrow 构建阶段，可能是 fragment 数据本身问题。
- **修复**:
  1. 检查 fragments 完整性：`tabix <sample>_fragments.tsv.gz chr1:1-1000000 | head`
  2. 检查 `.tbi.gz` 索引存在且非空
  3. 清理 ArchR tmp 目录后重试（`unlink("tmp", recursive=TRUE)`）
  4. 若重试仍失败 → 标记样本跳过，在最终报告中注明

### 🟡 Motif 富集分析 — 非 UCSC 基因组 + 小 DA tile 集

DA tiles 数量少（<100）时，Fisher 检验对 633 个 JASPAR motif 无统计效力 → 改用**得分排序法**（fg/bg mean score fold-change）。详见 `references/motif-analysis-non-ucsc-small-sets.md`：

- **JASPAR2020 而非 JASPAR2024** — 后者 `getMatrixSet` API 已损坏
- **NCBI→UCSC 映射 + BSgenome 边界检查** — T2T 坐标可超出 rheMac10 染色体末端
- **`name(motifs[[id]])` 将 MA 编号转 TF 名**
- 2026-07-29 验证：CEBPB (FC 5.28) Old 富集，HOXB8 (FC 8.38) Young 富集
- **跑完 ≠ 收尾**（2026-08-02 教训）：motif 分析完成后必须出 Top-TF 柱状图（Old 红 #E64B35 / Young 蓝 #4DBBD5）+ 用 anchor 插入法整合进已有 HTML 报告 + 更新 task_plan + record_run。可视化配方/HTML 追加代码/收尾协议见同一 reference 的 "Visualization + HTML Report Integration" 一节
- **跑完 ≠ 下一步可自动启动**（2026-08-02 唤醒验证）：Phase 全 complete 后系统唤醒/用户问进度时，必须走"停止命令检查 + 外部依赖门控 + 三源验证 + 汇报给选项"的唤醒门控协议，不自动启动跨物种对比等新任务。完整协议见 `references/post-completion-wakeup-gate.md`

### 🟢 可视化与 HTML 报告 (Phase 5)

Phase 4 (TileMatrix + getMarkerFeatures) 完成后进入收尾阶段。完整配方 → `references/phase5-visualization-report.md`：

1. **UMAP 3 面板**：Cluster / AgeGroup / Sample，`plotEmbedding` + `ggsave`
2. **细胞组成堆叠柱状图**：按 Old 比例降序排列 Cluster × Age 组成
3. **HTML 总结报告**：Python 手动构建，base64 嵌入所有 PNG，含 summary cards + timeline + 方法参数表 + 文件清单。预期 2-5MB。**禁止用 MemOmics 内建 `generate_report`（仅 ~40KB 空壳）。**

### 🟢 公共 GEO ATAC fragment 文件导入

从 GEO 导入预处理的 ATAC fragment 文件（`.tsv.gz` + `.tbi.gz` Tabix 索引格式）可直接构建 ArchR Arrow — 免除 fastq 比对。已知人类海马 ATAC 数据集（GSE278576 *Science* 2026 为最佳候选：40 ATAC 衰老海马样本）、ENCODE 人类脑 ATAC 缺失说明、GEOparse 元数据提取方法 → `references/public-geo-fragment-import.md`

### 🔴 GSE278576 40 样本全量到齐 + 猴参数复现（2026-08-07 磁盘实测）

- **40/40 fragments + 40/40 .tbi.gz 索引全部下载完成并验证完整**（`E:\专利\Human_Hippocampus_ATAC\fragments\`，0.96–5.97GB/样本）。gse278576 skill 里的"9 样本全 Young / 等 40 样本下齐"已是历史状态。
- **年龄分布 = 官方 4 组 × 10 = 40 donors**（20-40 / 40-60 / 60-80 / 80-100 各 10）。
- **80-100 岁组是必须**：官方分析是连续年龄 Pearson 相关（非 Young vs Old 分组），且专利要 species×age 交互 → 全年龄谱不可缺；该组 Braak 0-II 无 AD 病理 = 健康衰老样本。
- **跨物种专利项目人侧必须走 ArchR + 猴参数**（minTSS=4, minFrags=3000, filterRatio=2, 500bp tile, iterative LSI, Seurat res 0.8）保证两侧管线一致可比 — 不要默认官方 SnapATAC2 流程。
- 环境已验证：R 4.5.3 + ArchR 1.0.3 + BSgenome.hg38 + chromVAR/motifmatchr 全就绪（人侧标准 UCSC hg38，无需自定义基因组）。
- **测速基准（2026-08-07，最小样本 hc69984，918MB/0.96GB）**：P1 createArrowFiles ≈ 10.9 min（5195 cells 通过 QC，TSS=11.9，Frags=9885）→ P2 addDoubletScores ≈ 3 min → filterDoublets 双联率 10.4%（539/5195）。40 样本按平均 2.5GB 估算 P1 单样本 15-30 min → 串行 40 样本预计 10-20h。**中档样本实测（2026-08-07 hc40, 2.48GB）**：P1 Arrow 创建 ≈ 15.25min（19:21:42 START → 19:36:58 Arrow 成功，1.68GB）→ P2 addDoubletScores 启动 +3min（19:43:34）→ P1+P2 合计 ≈ 22min，与\"平均 2.5GB 单样本 15-30min\"估算吻合。
  - 🔴 **P2 阶段日志签名 = 当前样本 stage 探针（2026-08-07 hc40 实测）**：样本 batch 日志出现 `>>> P2 addDoubletScores <timestamp>` 行 = P1 Arrow 已创建成功、进入双联评分阶段（mid-run 唤醒看这一个 marker 就知道当前样本在 P1 还是 P2）；ArchR 内部日志 `Filtering N dims correlated > 0.75 to log10(depth + 1)` 是 addDoubletScores 的确认签名。P3 同理会有 `>>> P3 ...` marker。读当前样本 batch 日志尾部 → 最后一个 `>>> Px` marker 即当前阶段，比猜\"哪个 Rscript 在跑哪个样本\"快得多。**⛔ 并行不可行（2026-08-07 实测推翻）**：并发 3 跑 40 样本批量 → 5/7 失败（`.filterCellsFromArrow` 报 `Cannot open file tmp-*.arrow does not exist`）——ArchR 1.0.3 所有实例共享同一 `outputDirectory/tmp/`，多进程竞争清理临时 Arrow。**60GB RAM 能撑并发 ≠ ArchR 能并发。ArchR Windows 版唯一稳定模式 = 串行（并发 1）**。用 `run_serial.sh`（逐个样本 + 完成检查 `ArchR_Arrow_QC_Filtered/{s}/{s}_filtered_cells.csv` + watchdog 继续下一个）。
  - 🔴 **tmp 竞争第二错误面：`.tabixToTmp` → `h5checktypeOrOpenLoc: Cannot open file ...\\tmp\\tmp-<sample>-arrow-<hash>.arrow does not exist`（2026-08-07 17:35-18:00 级联崩溃实测）**：与 `.filterCellsFromArrow` 同根因（共享 tmp/），但错误出现在 P1 **早期**（读 fragment chunk 后写临时 arrow 时），且**单实例也会触发**——ArchR `createArrowFiles` 默认 `cleanTmp=TRUE`，每次跑完**删除 tmp/ 目录**；并发实例 A 的 cleanTmp 会把实例 B 正在用的 tmp arrow 删掉 → B 的 h5 打开失败。恢复时即使杀到只剩 1 个实例，若 tmp/ 被上次崩溃的 cleanTmp 删掉/残留脏文件，下一实例仍可能在 `.tabixToTmp` 失败。**防御①：R 脚本内每次跑前主动清理 tmp/（`unlink(tmp_dir, recursive=TRUE, force=TRUE)` 放在 `setwd(out_root)` 之后、`createArrowFiles` 之前）——在 R 层面保证"干净启动"，不依赖外部 shell 清理。防御②：单实例串行 + 重启前确认 tmp/ 目录状态（`test -d ArchR_Arrow_QC/tmp`）**。
  - 🔴 **下游误导性错误：`错误于file.exists(object@sampleColData$ArrowFiles): 'file'参数无效`（ArchRProject validity）**：createArrowFiles 失败返回空 → 脚本继续执行到 `ArchRProject(ArrowFiles=...)` → 报校验错（看似 project 构建问题）。**这是 P1 失败的次级症状，不是真因**——追根因必须读 P1 阶段日志（tabixToTmp 的 tmp arrow 打不开），不要在 ArchRProject 处浪费轮次改代码。
  - ⚠️ **batch 日志冻结在 `Attempting to index ... as tabix..` + Rscript 存活 = 可能只是块缓冲**（stdout 重定向不实时落盘，铁规 0 唤醒 #2 已证），不要据此判死；用 ArchRLogs 内部日志 mtime 或 ps -ef 启动时间交叉验证。
  - 🔴 **恢复时先杀 in-flight 孤儿再重启 queue-rebuild 脚本**：v2 类脚本启动时重建 remaining = fragments − done(filtered_cells.csv)；正在跑的样本未落 done → 会被新实例重选 → 与孤儿 worker 并发。恢复顺序 = 杀光 → 清锁 → 修 monitor 钩子 → 重启单实例（详见 windows-bioinformatics-batch-processing `references/auto-restart-hook-stale-script.md`）。
- **逐样本脚本模式已验证**：`create_arrow_qc.R <sample_id> <frag_path> <out_dir>` + `.bat` 包装（cmd.exe /c 铁律）→ stdout 重定向到 `{sample}.log` → P1/P2/P3 分阶段 cat 时间戳。测速阶段 P3 因 filterDoublets 陷阱报错（见上方 filterDoublets 条目），修复后即可全量复用。
- 🔴 **调度器静默死亡事故（2026-08-07 memomics-1135ed52 25/40 停滞 95 分钟）**：hc1265 完成 P3 后 run_serial.sh 调度进程消失，但 monitor_serial.sh 继续活着写 done=25/40——monitor 只报状态不重启，Agent 多轮三源验证都未识别"调度器已死"，用户反复追问才暴露。**判定口诀：done 冻结 + 无 worker + monitor 还在写 = 调度器死了**。**恢复 = 幂等重启**：terminal(background=true, command="bash batch/run_serial.sh", notify_on_complete=true)（SKIP 逻辑自动跳过已完成样本，从断点继续）→ 20s 后确认新样本 log START + 新 .bat mtime。**监控必须加"进度推进检查"**（done 连续 K 轮未增长 && procs==0 && 有剩余 → 自动重启，不是只写 alerts.json）。详见 windows-bioinformatics-batch-processing 铁规 4。
- **🔴 批量 auto-detect create-vs-resume（2026-08-07 memomics-1135ed52 9/40 失败教训）**：批量脚本必须逐样本检查 Arrow 是否存在来选择模式（不存在→create_arrow_qc.R / 存在但无_filtered_cells.csv→resume_p2p3.R / 全齐→skip）。严禁对所有样本统一用 resume。完整决策表 + 验证清单 → `references/batch-create-vs-resume-autodetect.md`\n- **mid-run 唤醒协议（2026-08-07 唤醒 #4 实测，区别于 post-completion 门控）**：P1-P3 串行批量进行中（非全部 complete）被系统唤醒时，正确动作 = ①读 task_plan 核对 session ID ②三源验证（tasklist 看 Rscript 双进程 launcher+worker、磁盘数 *_filtered_cells.csv/.arrow 与 task_plan 快照比对、monitor.log 尾部 done=N/40 procs=2 log=<sample>.log age=Xm + 当前样本 log 尾部看进度百分比）③cron 残留检查（同批并行调用，见记忆铁律）④汇报进度、确认队列推进正常后**不干预、不重启、不启动任何新 Phase**——P4 merge/LSI 必须用户确认后执行。mid-run 唤醒的目的只是确认"还在正常跑"，不是推进任务。
- **task_plan.md 唤醒条目膨胀管理**：长批量任务（40 样本 × 15-20min）会产生 30+ 条唤醒检查，task_plan.md 从 50 行膨胀到 400+ 行。超过 15 条 → 折叠旧条目为摘要行，仅保留最新 3-5 条完整格式。详见 `references/batch-taskplan-hygiene.md`。
- **快速判定样本边界的 PID-change 探针（唤醒 #23 实测）**：Rscript PID 与上次唤醒不同 = 上一个样本已完成、watchdog 自动续跑新样本 —— 比逐个查 log 快得多。`powershell Get-Process Rscript` 拿 PID → 与 task_plan 记录的上一 PID 对比：变了 → 数磁盘确认进度 +1，没变 → 同一样本仍在跑（看其 log 进度百分比）。配合 `ls 输出根目录 | grep '^GSM' | wc -l` 实测计数（⚠️ 输出目录名是 `GSM8549651_hc40` 格式，**必须 grep `^GSM` 而非 `^hc`**，否则恒返回 0）。
- **ArchRLogs 是确定性日志回退源**：task_plan 里记录的 monitor.log / 样本 .log 路径可能不在预期位置（batch 脚本目录变动后失效）。无论心跳文件在哪，`ArchR_Arrow_QC/ArchRLogs/ArchR-createArrows-*.log`（**未过滤 QC 目录**，不是 _Filtered 输出目录）永远有逐样本逐 chunk 进度（`(GSMxxx : 1 of 1) Reading TabixFile N Percent`）。`ls -t ArchRLogs/ArchR-createArrows-*.log | head -1` + tail 30 行 = 当前在跑哪个样本 + 进度百分比，与 PID 探针交叉验证。
- 完整年龄映射表 / 参数映射 / 分阶段计划 → `references/human-hippocampus-40samples-archr.md`
- ✅ **P1-P3 批处理 40/40 全部完成（2026-08-07 22:08 终态，memomics-1135ed52）**：40 个 filtered Arrow + `{s}_filtered_cells.csv` 产出在 `E:\专利\Human_Hippocampus_ATAC\ArchR_Arrow_QC_Filtered\`（40 子目录）。**总 Keep 细胞 265,909**（40 个 CSV 行数求和）。hc73（5.42GB 最大样本，页文件压力后重试成功 7758→6555, 15.51% doublet）；hc19（segfault 后由 bridge+fallback 双兜底补跑 6495→5652, 12.98%）。watchdog_v3 monitor.log 22:30:05 `procs=0 done=40/40` → ALL DONE 退出，无残留进程、无残留 cron。**下一步 P4（merge + tileMatrix + LSI + 聚类）待用户确认后另行执行——红线不自动启动**。40 样本 QC 全流程（进程监控/故障恢复/终态验收）细节 → `windows-bioinformatics-batch-processing` skill（铁规 4/4.5/0）。
- 🔴 **终态 QC 汇总表禁止从 filtered_cells.csv 解析 doublet 率（2026-08-07 终态汇总实测）**：40 样本 `*_filtered_cells.csv` 的 `DoubletFilter` 列**整列都是 `"Keep"`**（filterDoublets 过滤后保存，只含 Keep 细胞）→ Python 解析 40 个 CSV 统计 doublet 得 **0%**（看起来"没去双联"，表格误导）。**doublet 数/比例唯一权威来源 = 过滤前后细胞数差**（hc73 7758→6555=1203/15.51%；hc19 6495→5652=843/12.98%），从 run_serial_auto.out END 行或各样本日志 CellStats 读。CSV 合法用途 = 行数求和得 Keep 总数 + 验证 DONE_MARK 完整性（40/40），**禁止**用来算 doublet 率。
- 🟢 **filtered_cells.csv = "幸存者名单"设计（2026-08-09 用户亲自打开文件质疑"怎么都是 Keep"时的话术）**：这份 CSV 是 **QC+doublet 过滤后保留下来的细胞名单**——被判为 Doublet 的细胞**根本不在文件里**，所以 `DoubletFilter` 列 100% 是 `Keep` **是正常设计，不是 bug**。列只是冗余状态标记（"该细胞在过滤时被保留"）。**filterDoublets 机制澄清**：`filterDoublets(filterRatio=2)` 不是按 DoubletScore 硬阈值切（那样会看到高分标 Doublet、低分标 Keep），而是把全部细胞按 `DoubletEnrichment` 升序排序后**保留前 1/(1+filterRatio)=1/3**（enrichment 越低越像单细胞）→ 所以 `DoubletScore=11` 的细胞只要排名在前 1/3 仍标 Keep。这也解释了为什么同一样本里 doublet 率≈"过滤前后细胞数差/过滤前"而非"高分细胞占比"。**回答用户模板**：①CSV 是幸存者名单，被淘汰的没资格出现 ②DoubletScore 高但排名靠前仍保留 ③此 CSV 正是 merge 前必须用来 subset 的名单（见上方 P4 merge 条目）。

**⚠️ bigwig vs fragments 粒度选择（2026-08-02）**：GSE278576 suppl 同时提供①亚群聚合 bigwig（细胞类型×年龄组，~100-350MB，够做 L2 可及性比较）和②GSM 级单细胞 fragments（~1.3GB/样本，才能做 L3 真 footprinting）。**GSM 级 fragments 单独可下，不需要 89GB 的 GSE278576_RAW.tar。** 下载后用 HTTP HEAD 对比 Content-Length 验证完整性（用户此前下载的 hc77/hc78 只有 2MB/0.7MB，真实是 1.31GB = 0.15% 完成度）。完整决策树（L2→bigwig / L3→fragments / 带宽现实）→ 同上 reference 的 "bigwig vs fragments" 一节。

### 🟢 用户偏好
- **禁止装到 C 盘** — R 包、基因组数据、分析产出全部放 E 盘。R 本体放 C 盘可以（~100MB）
- **安装必须主动监控** — 不能 fire-and-forget。每 30-60 秒轮询进程状态+库目录变化
- **优先使用 `pak::pak()` 装 GitHub 包**（而非 `devtools::install_github()` 或 `remotes::install_github()`）
- **交付集群脚本 = 极简三步式，直接贴对话（2026-08-09 用户原话"我让你写简单一点，脚本就写在交互框上，要什么包，怎么读文件，怎么过滤，干净一点"）** — 用户在自己 Linux 集群跑正式版时，要求：①只给 `library()` 装包行 ②`list.files()` 读文件 ③过滤/统计逻辑，**三段式干净脚本直接贴在回复里**，不要 write_file 保存、不要长篇解释背景、不要完整管线大包。用户逐模块执行、每步把输出贴回来核对，Agent 再给下一步。
- **用户亲自验证数据** — 用户会自己打开 `_filtered_cells.csv` 看内容、数 `length(arrow_files)`、核对样本数。给脚本时必须考虑"用户会在集群上肉眼检查输出"，关键行加 `length()` / `sum()` / 验证注释。

### 🔴 集群正式版：40 样本 Arrow 读取陷阱（2026-08-09 Linux 集群实测）

用户在 Linux 集群（如 `/hwfssz3/PS_JLU/zhangbo/patent/`）跑正式版时踩到的 4 个坑，与 Windows 环境无关、纯 R/ArchR API 层面：

1. **`ArchRProject()` 参数名是大写 `ArrowFiles`，不是 `arrowFiles`** — 用户报 `Error in ArchRProject(arrowFiles = arrow_files): unused argument`。R 大小写敏感，正确写法：`proj <- ArchRProject(ArrowFiles = arrow_files)`（位置参数 `ArchRProject(arrow_files)` 也可，兼容旧版）。
2. **`list.files()` 不支持 shell glob**（`list.files("dir/*/*.arrow")` 返回空/不工作）— 用 `pattern = "\\.arrow$"` + `recursive = TRUE` + `full.names = TRUE`。全目录只要一个根路径。
3. **`recursive=TRUE` 会扫出嵌套副本** — 本地测试版遗留的 `FilteredProjects/` / `ArrowFiles/` 嵌套目录里每层都有同一样本的重复 `.arrow`，40 样本扫出 46 个。**必须先 grep 掉**：
   ```r
   arrow_files <- grep("FilteredProjects",
     list.files(dir, pattern = "\\.arrow$", recursive = TRUE, full.names = TRUE),
     invert = TRUE, value = TRUE)
   # 每样本仍可能有 2 个副本（根目录 + ArrowFiles/）→ 按样本名去重
   samp <- sub(".*/(GSM[0-9]+_hc[0-9]+)/.*", "\\1", arrow_files)
   arrow_files <- arrow_files[match(unique(samp), samp)]
   length(arrow_files)  # 应 = 40
   ```
   集群上清理命令：`find . -depth -type d \( -name "FilteredProjects" -o -name "ArrowFiles" \) -exec rm -rf {} \;`（先 `head` 预览再删；只删精确匹配目录名，不碰根目录 `.arrow` 和 `_filtered_cells.csv`）。
4. **`Save-ArchR-Project.rds` 是项目元数据索引卡（几 MB），不是 bug** — 每次 `subsetArchRProject`/`saveArchRProject` 自动生成，记录样本列表、细胞 metadata、指向哪些 Arrow。几百 MB 的 `.arrow` 才是数据本体。要省磁盘加 `copyArrows = FALSE`（硬链接，不复制 Arrow）。

> ⚠️ 正式版 merge 前**仍必须**按 `_filtered_cells.csv` 的 `cellNames[DoubletFilter=="Keep"]` 子集剔除 doublet（见上方 P4 merge 条目）——用户集群上传的就是 `ArchR_Arrow_QC_Filtered/` 目录，doublet 只在 CSV 名单里，不在 Arrow 里。

### 🟢 过滤前后细胞数统计（用户要的表）

```r
# before = Arrow 内细胞数（含 doublet）；after = CSV Keep 行数；removed = 差值
n_before <- data.frame(sample = as.character(unique(proj$Sample)),
                       before = as.numeric(table(proj$Sample)))
n_after <- do.call(rbind, lapply(csvs, function(c) {
  data.frame(sample = sub(".*/(GSM[0-9]+_hc[0-9]+)_.*", "\\1", c),
             after = sum(read.csv(c)$DoubletFilter == "Keep"))
}))
res <- merge(n_before, n_after, by = "sample", all = TRUE)
res$removed <- res$before - res$after
# sum(res$after) 应 = QC 汇总表 Keep 总数（40 样本 = 265,909）
```
> ⚠️ 提示用户：此段只统计不删除；真正剔除 doublet 要 `subsetArchRProject`（见上）。

### 🟢 分步保存铁律

ArchR 分析**每步操作后必须立即 `saveRDS`**，不能攒到最后。原因：

- addGroupCoverages 生成 coverage 元数据嵌入 ArchRProject — 不保存则重载丢失
- addTileMatrix、addIterativeLSI 等同理
- 单步崩溃时，已有 RDS 可恢复，不用从头重跑

```r
proj <- readRDS("project_clustered.rds")
proj <- addGroupCoverages(proj, groupBy="Clusters")
saveRDS(proj, "project_cov.rds")           # ← 必须

proj <- addTileMatrix(proj, tileSize=500)
saveRDS(proj, "project_tilemat.rds")       # ← 必须

markers <- getMarkerFeatures(proj, ...)
saveRDS(markers, "markers.rds")            # ← 必须
```
---

## ⛔ Post-Completion 唤醒门控（快速版）— 2026-08-08 唤醒 #11 再次验证

**场景**：`⏰ [系统唤醒 #N]` 或用户问进度，且 task_plan Phase 全部 complete / pending 被用户红线阻塞（如本项目的 P4 merge、P7 跨物种）。**唤醒 ≠ 执行入口。默认姿态 = 汇报 + 等指示。**

1. **定位 task_plan**：`ls -lt E:/MemOmics-Agent/results/*/task_plan.md | head` 取 mtime 最新（勿读旧 session 的 plan）
2. **三源验证**：tasklist（Rscript/python 残留）+ search_files 实查产出 + task_plan 的 ⛔ 标记。⚠️ **产出可能跨目录**：task_plan 声明的 Output 路径只覆盖部分产出（实测 P3-P5 写到项目区兄弟目录如 `E:/专利/P3_L1_data/`）——声明路径查不到 ≠ 产出缺失，先 `find <项目区> -name "<关键文件名>*"` 跨目录找再下结论
3. **红线检查**：有"等待用户指示/停止命令/不自动执行" → **绝不自动启动**，即使数据全齐
4. **选项菜单自检（#7 和 #11 都漏过②，强制逐项勾选）**：
   - ① 越线动作（P4 直启 / P7 直启）
   - ② **不越线 prep 中间档**（P7 前置 ortholog 映射 / chain 文件准备 — 可先放行，用户不必全盘确认）
   - ③ 保持现状 / 其他任务
   - 三项缺一 = 不合格菜单

完整协议（逐样本就位判定、停止后守护进程清理、mid-run 变体）→ `references/post-completion-wakeup-gate.md`

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="ATAC-seq 分析 —— {样本}",
     context="方法: {ArchR/Signac} | 参数: {peak calling参数} | 结果: {n} peaks {m} motifs",
     knowledge_base_info=<KB内容>,
   )
   辩论: peak质量如何？FRiP分数？motif富集合理吗？与RNA数据一致吗？
3. save_conclusions(module="03_advanced", topic="ATAC", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| macaca | hippocampus | aging | 2026-08-02 |  run_motif_figs.R | - | - |  |


| human | hippocampus | aging | 2026-08-08 | P1_da_young_old.R | - | - |  |
## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| 02e cluster-level marker 注释失败：17 clusters 中 16 个被误标 OPC | 02e R 脚本 binarized TSS±2kb 覆盖度绝对值过低（0.005-0.094），8 类 marker 分数拉不开，argmax 被噪声主导。**已排除行序错位**（getFeatures idx == rowData idx，见上方诊断） | 02d Python h5py 直读 Arrow CSC 方案 / 升级注释方法（gene score / 标签转移）；注释后必须做 CellType 分布组织预期验证门 |
| 02b_annotate_human_bg.R → 02c_annotate_human_tile.R | ArchR addGeneScoreMatrix 在 Windows 连续崩溃 2 次 | 绕开 addGeneScoreMatrix：改用 TileMatrix（500bp bins）计算 marker TSS±2kb 覆盖度注释。完整脚本 templates/annotate_human_tilematrix.R |
| run_serial.sh 用 cmd.exe //c "E:\\MemOmics-Agent\\r" | MSYS bash 调用 cmd.exe 时路径参数转义问题（\\r 被解释）+ .bat 中文路径 GBK 乱码（EXIT_CODE=9009） | 改用 run_serial_v2.sh: bash 直接调 Rscript.exe（中文路径放 R 脚本内部，bash 只传 ASCII sample_id）。偶发 segfault 可幂等重试 |

