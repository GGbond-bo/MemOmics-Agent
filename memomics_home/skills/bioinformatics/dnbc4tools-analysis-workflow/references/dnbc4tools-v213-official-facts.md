# dnbc4tools v2.1.3 官方文档要点核录（2026-08-28 从 2.1.3 tag clone 核对）

> 来源：`git clone --branch 2.1.3 https://github.com/MGI-tech-bioinformatics/DNBelab_C_Series_HT_scRNA-analysis-software.git`
> 核对文件：doc/pipeline.md、doc/pipeline/scRNA.md、scATAC.md、scVDJ.md、doc/parameter/scRNA.md、scATAC.md、scVDJ.md、doc/installation.md、doc/io.md、doc/quickstart.md、doc/json.md
> 本地镜像：`results/<sid>/task3/dnb_repo_213/`

## 安装（installation.md 官方事实）

- 系统要求：Linux x86-64、CentOS 7.x+ (kernel 3.10.0+)、≥50GB RAM、≥4 CPU
- 下载：`https://ftp.cngb.org/pub/CNSA/data5/CNP0006367/Single_Cell/CSE0000448/dnbc4tools2.1.3.tar.gz`
- **495M，MD5 = dfda9a3f308aaa3fdaa6c2a971bb2821**（2024-10-09 发布，注意与 index-building skill 旧记录 dac23475... 不同——以 installation.md 为准）
- 解压即用：目录含 dnbc4tools / external / lib / misc / sourceC4.bash
- 2.1.3 新特性：scRNA 5' 转录组分析（--end5）与 scVDJ 模块

## rna run 官方参数表（parameter/scRNA.md）

| 参数 | 默认 | 说明 |
|------|------|------|
| --name | 必需 | 样本 ID，与 HTML 报告一致 |
| --cDNAfastq1/2, --oligofastq1/2 | 必需 | cDNA/oligo 文库 R1/R2；多文件逗号分隔，R1/R2 顺序一致 |
| --genomeDir | 必需 | 含 ref.json + STAR 2.7.2b 索引 + mtgene.list |
| --outdir | 当前目录 | 按 name 建子目录 |
| --threads | 4 | 线程 |
| --calling_method | emptydrops | emptydrops / barcoderanks |
| --expectcells | 3000 | 建议=投入有效细胞数 50% |
| --forcecells | — | 按 UMI 排序强取前 N，最高优先级 |
| --chemistry | auto | scRNAv1HT/v2HT/v3HT/5Pv1 |
| --darkreaction | auto | 逗号分隔 cDNA/oligo：R1,R1R2 / R1,R1 / unset,unset |
| --customize | — | 自定义 whitelist+readstructure JSON（格式见 json.md） |
| --process | data,count,analysis,report | 见下 |
| --no_introns | false | 矩阵不含内含子 |
| --end5 | false | 5' 转录组（scVDJ 前置必须） |

process 分步：data=QC+比对生成 final_sorted.bam + CB_UB_count.txt；count=磁珠合并+raw/filter matrix+饱和度；analysis=过滤+降维聚类注释；report=结果+HTML。
**调 calling/expectcells/forcecells → 建议 --process count,analysis,report（跳过 data）；调 chemistry/darkreaction/customize/no_introns/end5 → 必须全流程。**

rna mkref 输出：chrLength/chrName/Genome/SA/SAindex/exonGeTrInfo/exonInfo/geneInfo/transcriptInfo/sjdbList/mtgene.list/ref.json（含 species/genome/gtf/genomeDir/chrmt/mtgenes）。官方日志 STAR verison 2.7.2b。

## atac run 官方参数表（parameter/scATAC.md）

| 参数 | 默认 | 说明 |
|------|------|------|
| --name, --fastq1, --fastq2, --genomeDir | 必需 | ATAC 单文库 |
| --outdir / --threads | 当前目录 / 4 | |
| --darkreaction | auto | R1R2 / R1 / R2 / unset |
| --customize | — | `[r1|r2|bc]:start:end:strand`，如 bc:6:15,bc:22:31,r1:65:-1,r2:19:-1（位置从0开始） |
| --forcecells | — | 与 peak 重叠 fragments 排序取前 N，最高优先级 |
| --frags_cutoff | 1000 | 过滤 fragments 数低于此值细胞 |
| --tss_cutoff | 0 | 默认不过滤，建议先跑默认按报告再调 |
| --merge_cutoff | 1000 | 合并磁珠最低 fragments；建议与 frags_cutoff 一致或不高于 |
| --process | data,decon,analysis,report | data=QC+比对+raw fragments+磁珠合并(otsu)+peak calling；decon=raw/filter peak matrix+细胞识别+TSS富集+饱和度；analysis=过滤+降维聚类；report=结果+HTML |
| --bam | false | 生成 BAM（显著延长分析时间） |

atac mkref 自带 --tag(默认 transcript 生成 tss bed)、--chrM(默认 auto 识别 chrM/MT/chrMT/mt/Mt)、--chloroplast(植物如 Pt)、--prefix(保留染色体前缀如 chr)。

**2.1.2+ 变更**：blacklist 不再强制存在；genomesize 用于 MACS2 peak calling（如 hs/mm）。

## vdj run 官方参数表（parameter/scVDJ.md）

| 参数 | 默认 | 说明 |
|------|------|------|
| --name, --fastq1, --fastq2, --ref, --chain, --beadstrans | 必需 | ref=human/mouse 仅两物种；chain=TR(TCG)/IG(BCR)；beadstrans=5'RNA output/singlecell.csv |
| --threads | 10 | |
| --darkreaction | auto | R1 / unset |
| --process | data,assembly,filter,report | data=QC+磁珠合并+VDJ比对提取；assembly=按细胞从头组装+IMGT注释；filter=细胞过滤+clonotype；report=结果+HTML |
| --nornafilter | false | 不用 5' 转录组细胞结果过滤 |
| --singleEnd | false | R1 仅测 barcode+UMI 时只用 R2 组装 |

singlecell.csv 列：CELL,Raw,GENE,UMI,GnReads,is_cell_barcode,BARCODE（BARCODE 分号分隔多磁珠）。

## multi 多样本格式

- rna multi --list sample.tsv：三列 tab 分隔 `sample  cDNA_R1;cDNA_R2  oligo_R1;oligo_R2`（多 fastq 逗号分隔）；输出每样本 xxx.sh
- atac multi --list sample.tsv：两列 tab 分隔 `sample  R1;R2`
- 所有样本必须同物种/同参考库

## io.md 输出读取速查

scRNA：output/ 下 raw_matrix/、filter_matrix/、RNAvelocity_matrix/（mex 三文件）、filter_feature.h5ad、singlecell.csv
- Seurat: `Read10X(filter_matrix, gene.column=1)`；RNAvelocity 用官方 ReadMatrix_C4() 读 spliced/unspliced/spanning 三个 mtx
- scanpy: `sc.read_h5ad(filter_feature.h5ad)` 或 read_anndata_C4()

scATAC：output/ 下 all.merge.fragments.tsv.gz、raw_peak_matrix/、filter_peak_matrix/（peaks.bed.gz+barcodes.tsv.gz+matrix.mtx.gz）、singlecell.csv
- Signac: CreateChromatinAssay(counts, sep=c("_","_"), fragments, min.cells=10, min.features=200)；metadata 需算 log10_uniqueFrags / pct_reads_in_peaks=peak_region_fragments/fragments*100 / pct_reads_in_tss
- ArchR: createArrowFiles(filterTSS=4, filterFrags=1000, addTileMat=TRUE, addGeneScoreMat=TRUE)
- anndata: read_atac_C4() barcodes→obs / peaks.bed→var(chr:start-end) / mtx→csr transpose

## json.md 文库结构（customize 白名单 JSON）

键：cell barcode tag(CB) / cell barcode(数组，每段含 location R1:1-10 + distance + white list) / UMI tag(UR) / UMI(location R1:21-30) / read 1(location R2:1-100)。位置从 1 开始（与 atac customize 位置从 0 不同）。scRNAv2HT 参考结构见 json.md 全文。

## Quickstart 官方 GTF 过滤命令

人：`wget gencode v32 GRCh38.primary_assembly.genome.fa.gz + gencode.v32.primary_assembly.annotation.gtf.gz`
`dnbc4tools tools mkgtf --ingtf ...gtf --output genes.filter.gtf --type gene_type`
鼠：Gencode M23 GRCm38 同法。