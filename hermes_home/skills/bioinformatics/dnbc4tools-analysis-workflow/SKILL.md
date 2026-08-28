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
- 典型工作流：Windows 下载 FASTA/GTF + `gzip -t` 验证 → scp 到 Linux → 装 dnbc4tools → mkref → run。
- 若用户在 Windows 本机 → 提供 WSL2 / Linux 集群 / 云服务器三条出路，不硬跑。

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