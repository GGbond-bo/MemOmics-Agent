---
name: dnbc4tools-analysis-workflow
description: >
  华大智造 MGI dnbc4tools v2.1.3 完整单细胞比对与分析流程（DNBelab C 系列官方开源软件，
  仓库 MGI-tech-bioinformatics/DNBelab_C_Series_HT_scRNA-analysis-software tag 2.1.3）。
  覆盖三大标准模块：scRNA（rna run，STAR 2.7.2b 剪接感知比对）、scATAC（atac run，
  chromap 0.2.6-r490 比对 + peak calling）、scVDJ（vdj run，预建库）。含 multi 多样本合并与
  输出解读（Seurat/scanpy 读取）。索引构建（rna/atac mkref）见 dnbc4tools-index-building。
  ⚠️ 触发前必须先走规则0触发门禁（澄清厂家+类型+是否已有库），禁止直接执行。
version: 1.0.0
source: memomics-created
when_to_use: 用户提到 DNBelab/dnbc4tools/华大BGI/华大基因 单细胞 RNA 或 ATAC 的比对/分析流程、
  rna run / atac run / vdj run / multi、DNBelab FASTQ 数据处理（区别于只建索引的 mkref 需求）
license: MIT
---

# dnbc4tools 完整比对/分析流程（华大智造 MGI · DNBelab C 系列）

华大智造（MGI，华大 BGI 旗下）官方开源单细胞分析软件 dnbc4tools v2.1.3。
官方仓库：`https://github.com/MGI-tech-bioinformatics/DNBelab_C_Series_HT_scRNA-analysis-software/tree/2.1.3`
（文档在 `doc/` 目录，2.1.3 tag 下均有中文版：pipeline.md 总览 + pipeline/scRNA.md、pipeline/scATAC.md、pipeline/scVDJ.md + parameter/scRNA.md、parameter/scATAC.md、parameter/scVDJ.md + installation.md + io.md + quickstart.md + json.md(customize 文库结构)。本仓曾 clone 至本地 `results/<sid>/task3/dnb_repo_213/` 供核对。）
>
> 📎 **`references/dnbc4tools-v213-official-facts.md`** — v2.1.3 官方文档要点核录（安装 MD5/参数表/process 分步/io 读取/文库结构 JSON），写脚本前先查这份权威参数。

## 🔴 规则0 触发门禁（用户特别指定，最高优先级）

命中触发词（DNBelab/dnbc4tools/华大/mkref/索引/比对等）时，**禁止直接执行**，必须先依次澄清：

| # | 必问 | 用户答「是」 | 用户答「否」 |
|---|------|------------|------------|
| ① | 是华大 BGI / MGI / DNBelab 平台吗？ | → 继续问 ② | ❌ 不触发：10X→Cell Ranger/STARsolo；常规 RNA-seq→STAR/hisat2；ATAC→其他流程 |
| ② | 建 RNA 还是 ATAC 索引/跑 RNA 还是 ATAC 流程？ | RNA→`rna mkref`→`rna run`；ATAC→`atac mkref`→`atac run` | scVDJ→`vdj run` 预建库（无需 mkref）；其他→redirect |
| ③ | 已有 ref.json 库了吗？ | 有→不重建，直接 `rna run --genomeDir` 复用 | 无→先建库（见 dnbc4tools-index-building）再分析 |

**✅ 触发条件（必须全部满足）**：① 厂家已确认=华大 BGI/MGI/DNBelab；② 类型已确认=RNA 或 ATAC；
③ 状态已确认=无现成 ref.json 库（或用户明确要重建）。

**❌ 不触发场景（redirect）**：厂家未知→先问；10X→Cell Ranger；bulk RNA→标准 STAR/hisat2；
scVDJ 只需要分析→`vdj run` 预建库；已有 ref.json→复用不建；只有 FASTA 无 GTF→标准 STAR；
只讨论不执行→只回答方案；跑的是其他平台数据→分流到对应 skill。

## 环境要求（官方硬性）

- 仅 Linux x86-64（闭源二进制，CentOS 7.x+ / kernel 3.10.0+）。Windows 本机不能直接跑。
- mkref 需 **≥50GB RAM、≥4 CPU**（建库 RAM 密集）；实际运行视数据量。
- 安装：官方 2.1.3 下载直达 `https://ftp.cngb.org/pub/CNSA/data5/CNP0006367/Single_Cell/CSE0000448/dnbc4tools2.1.3.tar.gz`（**495M，MD5 dfda9a3f308aaa3fdaa6c2a971bb2821**，安装说明见 doc/installation.md）→ 解压即用，无需编译。目录应含: dnbc4tools / external / lib / misc / sourceC4.bash。
- **另一官方渠道（2026-09-01 curl 实测确认）**：`ftp://ftp.cngb.org/pub/CNSA/data7/CNP0008672/Single_Cell/CSE0000574/` 含 `dnbc4tools-3.1.tar.gz`（527,613,238B）与 `dnbc4tools-3.0.tar.gz`（537,527,818B）+ **test1_barcodes/features/matrix 官方测试数据**（装完先用 test1 验证比对流程再跑真实数据）。⚠️ **FTP 上的 3.1/3.0 版本比 GitHub/tag 2.1.3 新**——装 3.1 后必须先 `dnbc4tools atac mkref --help`（或 rna）核对命令与 v2 文档是否一致再跑，勿假设参数表相同。
- **v3.1 命令差异（2026-09-01 实测 --help 核对）**：① `tools mkgtf --action` 由 v2 的 `stat`/`check` 变为 **`stats`/`check`/`mkgtf`**（默认=mkgtf 过滤，统计动作名改 `stats`）；② `tools mkgtf --type` 默认 `auto` 自动检测（实测识别出 gene_type），可不传；③ `atac mkref` **删除 `--threads`**（chromap 建索引单线程，传了直接报 `unrecognized arguments` 退出——2.1.3 的 `--threads 10` 示例不能照抄），**新增 `--tag`(默认transcript)/`--kmer`(17)/`--window`(7)/`--noindex`/`--chloroplast`**；④ `--prefix` 默认 None，人类 GRCh38 必须显式 `--prefix chr`，混合物种不支持 prefix；⑤ **⚠️ 指定 `--species Homo_sapiens` 后产物自动建到 `<genomeDir>/Homo_sapiens/` 子目录**（ref.json、fasta/、genes/、regions/ 全在子目录内），验证/下游路径必须带子目录。详细实测记录 → windows-bioinformatics-batch-processing/references/wsl-linux-binary-execution.md；ATAC mkref 3.1 完整实测与假失败判据 → references/dnbc4tools3.1-atac-mkref-notes.md
- 典型工作流：Windows 下载 FASTA/GTF + `gzip -t` 验证 → scp 到 Linux → 装 dnbc4tools → mkref → run。
- 若用户在 Windows 本机 → 提供 WSL2 / Linux 集群 / 云服务器三条出路，不硬跑。
- **Windows 本机 WSL2 落地（2026-09-01 实测通过）**：dnbc4tools 对 WSL2 Ubuntu 可直接运行；mkref 建议 ≥50GB RAM，默认 WSL 只分一半内存 → 创建 `C:\Users\<user>\.wslconfig` 写入 `[wsl2] memory=48GB, processors=16, swap=8GB` → `cmd.exe /c "wsl --shutdown"` 后下次启动生效（验证 `free -g`）。数据盘经 `/mnt/f/...` 访问（UTF-16 输出乱码时用落盘重定向或 iconv 规避）；WSL 内需 apt 装 curl/tar 等基础工具。

## 三大标准流程模块（官方确认）

| 模块 | 子命令 | 主流程 |
|------|--------|--------|
| scRNA | `rna run` | FASTQ(cDNA+oligo 双文库) → QC+比对(STAR)+注释 → 合并磁珠 → 原始矩阵 → 过滤矩阵 → 降维聚类 → 注释 → HTML 报告 |
| scATAC | `atac run` | FASTQ → QC+比对(chromap) → 合并磁珠 → peak calling → raw peaks 矩阵 → filter peaks 矩阵 → 降维聚类 → HTML 报告 |
| scVDJ | `vdj run` | **必须先完成 5' scRNA（`rna run --end5`）**，用其 `output/singlecell.csv` 作 `--beadstrans`；从 VDJ 文库 FASTQ 组装 TCR(chain TR)/BCR(chain IG) → IMGT 注释 → clonotype → HTML 报告；**使用官方预建库 human/mouse（无需 mkref，其他物种不支持）** |
| 多样本 | `multi` | `rna multi`(三列TSV: sample/cDNA/oligo) / `atac multi`(两列TSV: sample/R1;R2)，生成每样本 xxx.sh；所有样本必须同物种同参考库 |

## rna run 要点（scRNA）

- 输入：cDNA 文库 FASTQ + oligo（样本标签/UMI）文库；单/双端可按官方参数。
- 比对：STAR 2.7.2b（剪接感知）；需 `--genomeDir` 指向 `rna mkref` 产物（含 ref.json 即成功）。
- 试剂/暗反应自动检测（官方有自动识别机制）；参数参考 `doc/parameter.md` 与 `doc/io.md`。
- 输出：表达矩阵（raw + filtered）、QC 统计、降维聚类结果、注释、HTML 报告。
- 命令示例（官方 doc/pipeline/scRNA.md）：
  ```shell
  dnbc4tools rna run --name sample \
    --cDNAfastq1 /data/sample_cDNA_R1.fastq.gz --cDNAfastq2 /data/sample_cDNA_R2.fastq.gz \
    --oligofastq1 /data/sample_oligo1_1.fq.gz,/data/sample_oligo2_1.fq.gz \
    --oligofastq2 /data/sample_oligo1_2.fq.gz,/data/sample_oligo2_2.fq.gz \
    --genomeDir /opt/database/Homo_sapiens --threads 10
  # 成功标志: Analysis Finished；日志先输出 Chemistry(darkreaction) determined in ...
  ```
- **关键参数**：`--calling_method`(emptydrops默认/barcoderanks)、`--expectcells`(默认3000，建议=投入有效细胞数50%)、`--forcecells`(按UMI排序强取前N，最高优先级)、`--chemistry`/`--darkreaction`(auto推荐；试剂 scRNAv1HT/v2HT/v3HT/5Pv1)、`--no_introns`、`--end5`(5'转录组，scVDJ前置必须)。
- **--process 分步跳过**（默认 data,count,analysis,report）：data=QC+比对生成 final_sorted.bam/CB_UB_count.txt；count=磁珠合并+raw/filter矩阵+饱和度；analysis=过滤+降维聚类注释；report=结果+HTML。调 calling_method/expectcells/forcecells → 建议 `--process count,analysis,report`（跳过data）；调 chemistry/darkreaction/customize/no_introns/end5 → 必须全流程。
- 下游：`doc/io.md` 有 Seurat/scanpy 读取矩阵与对象构建的标准示例（DNBelab 矩阵为

## atac run 要点（scATAC）

- 输入：scATAC FASTQ；比对 chromap 0.2.6-r490（通用短读）。
- 需 `--genomeDir` 指向 `atac mkref` 产物（genome.index + TSS/promoter/blacklist/chrom.sizes + ref.json）。
- 流程：比对 → 合并磁珠 → peak calling → raw/filter peaks 矩阵 → 降维聚类 → HTML 报告；
  含 fragments/可及性统计（TSS/promoter 区域覆盖）。
- 命令示例（官方 doc/pipeline/scATAC.md）：
  ```shell
  dnbc4tools atac run --name sample \
    --fastq1 /sample/data/test1_R1.fastq.gz,/sample/data/test2_R1.fastq.gz \
    --fastq2 /sample/data/test1_R2.fastq.gz,/sample/data/test2_R2.fastq.gz \
    --genomeDir /opt/database/Mus_musculus --threads 10
  ```
- **关键参数**：`--frags_cutoff`(默认1000，过滤低fragments细胞)、`--tss_cutoff`(默认0不过滤)、`--merge_cutoff`(默认1000，合并磁珠最低frags，建议与frags_cutoff一致或不高于)、`--forcecells`(与peak重叠frags排序取前N，最高优先级)、`--darkreaction`(auto；R1R2/R1/R2/unset)、`--customize`(`[r1|r2|bc]:start:end:strand` 格式)、`--bam`(标志，生成BAM但显著延长运行时间，不需别加)。
- **⚠️ v3.1 `atac run` 参数实测差异（2026-09-01 --help 核对，勿按 v2 文档照抄）**：
  - `--threads` 仍支持且默认 **10**（注意：mkref 删了 threads，但 run 有）；
  - 输入二选一：`--fastqs <DIR>` 目录输入自动检测 R1/R2（v3.1 新增，推荐单库单目录） 或 `--fastq1/--fastq2` 逗号合并多 lane（顺序必须一一对应）；
  - **`--outdir` 指定输出目录**（默认当前目录——批量跑必须显式给，否则输出撒在当前目录）；
  - **`--merge_cutoff` 默认 500（v2=1000）**、`--frags_cutoff` 默认 1000 不变、新增 `--jaccard_cutoff`(0.02)；
  - **BAM 标志改名 `--need_bam`**（v2 是 `--bam`，照抄 v2 参数会报 unrecognized）；
  - 新增 `--sample_read_pairs <N>`：抽样前 N 对 reads 快速验证全流程（试跑首选，避免拿 88G 全量试）；
  - **`--genomeDir` 必须指向含 ref.json 的** `<索引根>/Homo_sapiens/` 子目录**——v3.1 atac mkref 带 `--species` 后 ref.json/fasta/genes/regions 全建于子目录，ref.json 内部路径（genome/index/gtf/chromeSize/tss/promoter）均为相对该子目录的相对路径。传父目录会找不到索引。
- 批量循环实测记录 → `references/dnbc4tools3.1-atac-run-batch-notes.md`；可复用的循环脚本模板 → `templates/atac_run_batch.sh`。
- **夜间批量排队（"先跑两三个，我早上醒来再看看"）**：试点单库(SLIB)跑完即退出 → 另写排队脚本等其完成标志 `<outdir>/output/singlecell.csv` 后用 `wsl -e bash -c "nohup bash atac_queue_next.sh ... &"` 挂后台串行接后续库；Hermes 的 background process 对象随会话消失但 WSL 内 nohup 存活；选库先 `du -sh | sort -h` 取最小 2–3 个（磁盘紧时最快出结果+可推算总账）。完整骨架与教训 → `references/overnight-batch-queue-pattern.md`。
- **--process 分步跳过**（默认 data,decon,analysis,report）：data=QC+比对+raw fragments+磁珠合并(otsu)+peak calling；decon=raw/filter peak矩阵+细胞识别+TSS富集+饱和度；analysis=过滤+降维聚类；report=结果+HTML。调 forcecells/frags_cutoff/tss_cutoff(decon参数) → 可 `--process decon,analysis,report`；调 darkreaction/customize/merge_cutoff/bam(data参数) → 必须全流程。
- **2.1.2+ blacklist 变化**：atac mkref 不再强制要求 blacklist 文件；可手动添加，不影响分析结果，黑名单区片段数记录在 `output/singlecell.csv` 的 `blacklist_region_fragments` 列。
- **chromap 限制**：官方明确 chromap 目前无法处理极大基因组，某些物种无法做 scATAC。
- 下游：peak 矩阵供 ArchR/Signac 等继续分析。

## vdj run 要点（scVDJ）

- **前置必须**：先完成对应样本 5' 转录组分析 `rna run --end5`，得到 `output/singlecell.csv`（含 CELL/BARCODE/is_cell_barcode 列）。
- 命令示例（官方 doc/pipeline/scVDJ.md）：
  ```shell
  dnbc4tools vdj run --name sample_tcr \
    --fastq1 /data/sample_tcr_R1.fastq.gz --fastq2 /data/sample_tcr_R2.fastq.gz \
    --ref human --chain TR --beadstrans /sample_5rna/output/singlecell.csv --threads 10
  # BCR: --chain IG；--ref 仅 human/mouse 预建库
  ```
- **关键参数**：`--ref`(必需，human/mouse)、`--chain`(必需，TR=TCR/IG=BCR)、`--beadstrans`(必需，5'RNA的singlecell.csv)、`--process`(默认 data,assembly,filter,report：data=QC+磁珠合并+VDJ比对提取；assembly=按细胞从头组装+IMGT注释；filter=细胞过滤+clonotype；report=结果+HTML)、`--nornafilter`(不用5'转录组细胞结果过滤)、`--singleEnd`(R1仅测barcode+UMI时只用R2组装)。
- 输出：clonotype 表（组装 contigs、IMGT 注释、clone 信息）+ HTML 报告。

## multi 多样本

- `rna multi --list sample.tsv --genomeDir ...`（三列 TSV：sample / cDNA_R1;cDNA_R2 / oligo_R1;oligo_R2；多fastq逗号分隔）；`atac multi --list sample.tsv`（两列 TSV：sample / R1;R2）。输出每样本 xxx.sh 再逐个执行；所有样本必须同物种同参考库。
- long 任务 → 后台执行 + 进度轮询（参考 windows-bioinformatics-batch-processing）。

## 输出解读（官方 doc/io.md，下游分析直接读）

**scRNA 输出目录**（`outdir/name/output/`）：`raw_matrix/`、`filter_matrix/`、`RNAvelocity_matrix/`、`filter_feature.h5ad`、`singlecell.csv`（CELL/BARCODE 对应）。

| 工具 | 官方读取方式 |
|------|------------|
| **Seurat (R)** | `Read10X(data.dir="/output/filter_matrix", gene.column=1)`；或官方 `ReadMatrix_C4()`（支持 spliced.mtx.gz/unspliced.mtx.gz/spanning.mtx.gz 分离矩阵，读做 list(spliced/unspliced/spanning)） |
| **scanpy (Python)** | `sc.read_h5ad('/output/filter_feature.h5ad')`；或官方 `read_anndata_C4(path)`：mmread matrix.mtx.gz → transpose → csr → AnnData（features[0]→var_names+gene_symbols，barcodes→obs_names） |

**scATAC 输出目录**：`all.merge.fragments.tsv.gz`、`raw_peak_matrix/`、`filter_peak_matrix/`（peaks.bed.gz + barcodes.tsv.gz + matrix.mtx.gz）、`singlecell.csv`。

| 工具 | 官方读取方式 |
|------|------------|
| **Signac (R)** | `read_signac_C4(mex_dir_path, fragments, singlecellmetadata)`：peaks.bed 拼 chr:start-end → 矩阵 → CreateChromatinAssay(counts, sep=c("_","_"), fragments, min.cells=10, min.features=200)；metadata 自动算 log10_uniqueFrags / pct_reads_in_peaks / pct_reads_in_tss |
| **ArchR (R)** | `createArrowFiles(inputFiles=FragmentFiles, filterTSS=4, filterFrags=1000, addTileMat=TRUE, addGeneScoreMat=TRUE)` |
| **anndata (Python)** | 官方 `read_atac_C4(path)`：barcodes→obs / peaks.bed→var(chr:start-end) / matrix.mtx.gz→csr transpose → AnnData |

## 与 dnbc4tools-index-building 的分工

| skill | 范围 |
|-------|------|
| `dnbc4tools-index-building` | **建库**：`rna mkref`(STAR) / `atac mkref`(chromap) / `tools mkgtf`，输出 genomeDir，ref.json 判定成功 |
| `dnbc4tools-analysis-workflow`（本 skill） | **完整流程**：建库后的 `rna run` / `atac run` / `vdj run` / `multi` + 输出解读 |

调用顺序：本 skill 流程需要库时前置执行 index-building 的 mkref 步骤（两 skill 共用规则0触发门禁）。

## 常见坑（已核实）

1. **触发前必澄清**（用户特别指定）：厂家/类型/是否已有库，三问缺一不可，禁止凭触发词直接动手。
2. **Windows 不能跑**：闭源 Linux 二进制；别在 execute_r/execute_python 里尝试加载。
3. **mkref 内存不足**：<50GB RAM 会 OOM；生成 SA/SAindex 前先确认机器规格。
4. **rna 与 atac 库不可混用**：`rna run` 必须配 rna mkref 产物（Genome/SA），`atac run` 必须配 atac mkref 产物（genome.index）；混用 STAR/chromap 直接报找不到索引文件。
5. **ref.json 是成功标志**：建库/运行前检查 genomeDir 下 ref.json 存在，缺则库不完整。
6. **gencode v32 GRCh38.primary_assembly 为 rna mkref 标准输入**（FASTA+GTF 均需 EBI 下载并 gzip -t 验证）。
7. **git clone 该仓库**：本机 git 代理可能失效 → `git -c http.proxy= -c https.proxy= clone ...` 直连。
8. **GTF 缺 gene/transcript 行** → 主流程注释报错，用 `tools mkgtf --action check --output corrected.gtf` 校正；多基因重叠位置会 Warning，该区 reads 被过滤。GFF 不支持。
9. **expectcells 不准**：官方建议填投入有效细胞数的 50%；调参后可用 `--process count,analysis,report` 跳过 data 重跑。
10. **scVDJ 必须先进 5' RNA**：`--beadstrans` 指向 `rna run --end5` 的 `output/singlecell.csv`，缺前置直接报错。
11. **严禁合并不同实验/样本 FASTQ**：仅同一文库多 lane 可逗号合并，测序模式/暗反应必须一致。
12. **rna run 命令示例必须带 `--name`**：name 决定 HTML 报告样本 ID 与输出子目录名。
13. **3.1 版 atac mkref "假失败"（2026-09-01 实测）**：包装脚本按 2.1.3 结构去 `genomeDir/` 根目录 cat ref.json → 3.1 产物在 `genomeDir/Homo_sapiens/` 子目录 → cat 失败 + `set -e` → exit 1，看起来"失败"但 mkref **实际成功**（日志内 `MKREF_EXIT=0` + `ATAC reference building finished`）。判成功读真实 log——不要因退出码误判重跑（GRCh38 索引 ~16GB，重跑纯浪费）。产物规模参考：genome.fa 3.15GB + genome.index 12.3GB + genes.gtf 1.3GB。
14. **⚠️ Git Bash 看不到 WSL 挂载路径（2026-09-01 实测，最烧钱的坑）**：Host Windows 侧 `terminal` 跑在 Git Bash（MSYS），只有 `/f/`（盘符映射）而**没有 `/mnt/*`、`/data` 这些 WSL 内部路径**——直接 `ls /mnt/e` 会报 No such file or directory，被误判为目录不存在。**所有需要访问 WSL 内路径的命令必须 `wsl -e bash -lc "..."` 前缀**，例如 `wsl -e bash -lc "ls /data/; df -h /mnt/f"`。WSL 输出 UTF-16 乱码时管道 `| iconv -f UTF-8 -t UTF-8 -c`（实测有效）或落盘重定向再读。教训：把探测做成 `wsl -e bash -lc` 的一次性脚本，别在 Git Bash 直接猜路径。
15. **批量 atac run 前必须先做磁盘空间核算 + 试点**（2026-09-01 实测）：24 文库 ATAC 全量输出可达 **500GB–2TB**；跑之前 `df -h` 确认输出盘余量，余量不足 → 与用户确认输出盘/边跑边删策略。**先跑最小文库试点**（`SLIB=<文库名>` 单库模式），实测单库输出体积与耗时后按比例算总账，再决定是否全量——避免脚本循环跑到一半爆盘中断。多 lane 文库（同目录 4–6 个 fq）用 `_1/_2` 后缀拍序配对后逗号合并传给 `--fastq1/--fastq2`。
16. **单库磁盘占用实测量级（2026-09-01）**：88–174G fq.gz 输入 → 仅 PISA parse 阶段（READS_QC_FILTER）中间文件就 **r1/r2/cb 三份 reads 合计 ~64G**，加比对 BAM/peak 输出，**单库全流程 >180G**。输出盘余量 <200G/库 就撑不完一个库——批量前按这个量级核算，别只看输入 gz 大小。
17. **排队脚本挂载后必须 ps 验证（2026-09-01 教训）**：`wsl -e bash -lc "nohup bash atac_queue_next.sh ... & echo started"` 之后，**必须 `wsl -e bash -lc "ps -ef | grep atac_queue"` 确认进程真在**——本会话声称"排队脚本已挂好"但实际 ps 里只有 `atac_run_batch.sh` 单库实例，2200 跑完不会自动接后续库，用户要的"两三个"只会有第一个。报"已启动/已挂好"前必须工具验证（铁律-1）。
18. **完成标志实际路径带 name 子目录（2026-09-01 修正）**：`atac run --outdir $OUT --name $s` 的最终产物在 **`$OUT/$s/output/singlecell.csv`**（outdir 下多一层 name，不是 `$OUT/output/`）。排队/断点续跑脚本等完成标志时路径必须带 `/$s/`，否则永远等不到。
19. **⚠️ 磁盘告急时停库止损 = 先问用户再停（2026-09-01 用户信任教训）**：发现输出盘将爆（如 160G 余量 vs 单库 180G）时，**不要单方面 kill 正在跑的用户任务**——先展示实测数据（进程/余量/中间文件）+ 止损方案（换盘/边跑边删/只跑试点）征求用户选择。用户明确"靠你了"≠ 授权杀掉已启动的比对进程；先斩后奏会破坏信任。唯一例外：用户明确说停止/取消。
20. **QC 中间件不自动清理 + 续跑策略（2026-09-01 实测）**：dnbc4tools `atac run` 的 READS_QC_FILTER 中间件（`<outdir>/<name>/ATAC_ANALYSIS_WORKFLOW_PROCESSING/READS_QC_FILTER/atac.reads.{r1,r2,cb}.fq`，合计 ~64-65G/库）**跑完仍保留，不自动删**。输出盘按此核算：如 F 盘可用 224G → 稳跑 **2 库**；每库验证完成后手工清理该库 READS_QC_FILTER（约 65G）→ 可续跑第 **3 库**；**24 库全量必须改输出盘**（E 盘 398G 等），否则无解——把空间账写进 task_plan 的空间账节供用户决策。清理写法：`rm -rf <outdir>/<name>` 或写脚本执行（见 platform-execution-pitfalls 删除门禁条目）。
21. **自动轮自主推进边界（2026-09-01 自动唤醒轮实测）**：用户说"靠你了" + 系统自动唤醒轮（用户不在场）时——**可自主做**：清理半截残留、重启试点、挂监控循环、更新 task_plan；**不可擅自做**：改变用户明确指定的参数（如输出位置 F 盘）、停掉用户已启动的进程（见 #19）、替用户拍板空间方案（A/B/C）——这些留给用户醒来定，但要把空间账/决策依据写进 task_plan 的 Decisions 与空间账节，方便用户醒来快速决策。重启试点用 `SLIB=<文库名> bash atac_run_batch.sh` 单库模式（background=true + notify_on_complete=true），并在清残留/重启后**必须 ps 验证 dnbc4tools 进程真在跑**（PISA parse 出现即进入 QC 阶段）。
22. **⚠️ ATAC 进度/结果汇报必须盯官方产物，禁止把 reads 中间件当"结果"（2026-09-01 用户直接质疑："结果文件怎么会是 reads 数？你看过官方ATAC比对的输出文件吗？你自己调查看看"）**：`atac run` 的 READS_QC_FILTER 阶段产生的 `atac.reads.{r1,r2,cb}.fq`（PISA parse 后中间件，~64-65G/库）是**过程中间件，不是交付产物**。用户拿官方输出对照，汇报"跑了多少 reads / QC 后剩多少 reads / reads 占 65G"会被当场判定"流程不对"。官方 scATAC 结果= `$OUT/$name/output/` 下的 **`all.merge.fragments.tsv.gz` + `raw_peak_matrix/`（peaks.bed.gz+barcodes.tsv.gz+matrix.mtx.gz）+ `filter_peak_matrix/` + `singlecell.csv`**（见上方"输出解读"节）。**纪律**：① 进度/结果汇报以这些官方产物是否出现为准（singlecell.csv 出现=data 阶段完成），reads 中间件只算"处理中"；② 给用户交付前自查输出树是否有 fragments/peak matrix/singlecell.csv，没有就不能声称"跑完了比对/出了结果"；③ 监控脚本完成后检查也等 `$OUT/$name/output/singlecell.csv`（见 #18），不要盯 READS_QC_FILTER 目录。

23. **⚠️ 监控循环必须验证进程存活，磁盘写满时 dnbc4tools 会静默死亡（2026-09-01 试点失败实录）**：monitor 循环（每 10 分钟 du 输出 + df 可用 + tail 日志错误数）在试点进程写满 F 盘期间持续报「运行中 | 输出 137G→209G 增长 | 可用 88G→14G | 日志错误 0」——**dnbc4tools 磁盘写满时进程静默消失（无错误日志），监控只看「日志错误 0 + 输出在增长」会被骗**。试点终局 = 输出累计 **209G（88G gz 单库输入，仍未到输出阶段）+ 官方产物 0 个（无 fragments/peak matrix/singlecell.csv）+ 进程死亡**（ps 只剩 monitor 循环，dnbc4tools/PISA parse 全消失）——比 #16 预估的 >180G 更狠，F 盘 224G 余量连一库都跑不完，24 库全量在 F 盘物理不可能。纪律：① 监控循环每轮必须同时查进程存活（`ps -ef | grep dnbc4tools`），不能只看输出增长/日志错误数；② 报「运行中」前确认 dnbc4tools 进程在 + 官方产物未出现 才有意义；③ 输出盘可用 < 100G 时优先报「磁盘告急」而不是「还在跑」；④ 磁盘写满是**静默失败**高发场景——跑批前按最保守量级核算空间（单库 209G+ 仍可能不够），且用户问「结果文件怎么会是 reads」时先自查是否进程已死于盘满、只留下 QC 中间件（与坑 #22 同源）。

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| - | - | - | 2026-09-01 | wsl_path_probe.sh | - | - |  |
| - | - | - | 2026-09-01 | wsl_precheck.sh | - | - |  |
| - | - | - | 2026-09-01 | atac_run_help_v31.sh | - | - |  |
| - | - | - | 2026-09-01 | atac_run_batch.sh | - | - |  |
| - | - | - | 2026-09-01 | atac_run_batch.sh | - | - |  |
| human | brain | atac | 2026-09-01 | atac_run_batch.sh | - | - |  |
| human | brain | atac | 2026-09-01 | atac_run_batch.sh | - | - |  |
| human | brain | atac | 2026-09-01 | atac_run_batch.sh | - | - |  |
| human | brain | atac | 2026-09-01 | atac_run_batch.sh | - | - |  |
| human | brain | atac | 2026-09-01 | atac_queue_next.sh | - | - |  |
| human | brain | atac | 2026-09-01 | atac_queue_next.sh | - | - |  |
| human | atac | atac-seq | 2026-09-01 | atac_run_batch.sh | - | - |  |


| - | - | - | 2026-09-01 | wsl_probe_output_tree.sh | - | - |  |
| - | - | - | 2026-09-01 | atac_output_audit.sh | - | - |  |
| human | brain | atac | 2026-09-01 | atac_output_audit.sh | - | - |  |
| human | brain | - | 2026-09-01 | atac_run_batch.sh | - | - |  |
| human | brain | - | 2026-09-01 | atac_run_batch.sh | - | - |  |
## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| F盘仅剩161G，2200单库输入93G gz，PISA parse解压中间fq已占64G且继续增长 | 输出目录选在接近满盘的F盘(3.7T用3.5T)，dnbc4tools ATAC | - |

