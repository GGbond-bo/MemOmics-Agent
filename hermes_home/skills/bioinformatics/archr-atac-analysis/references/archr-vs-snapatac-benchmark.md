# ArchR vs SnapATAC/SnapATAC2 — Benchmark 证据库（2026-08-11 调研）

## 一句话结论

SnapATAC2 在聚类精度和运行速度上优于 ArchR（复杂脑组织亚型、稀有类型、>2万细胞尤其明显）；
ArchR 内存最省，且 footprinting/共可及性（Co-accessibility）是独占强项。
跨物种 CRE 专利项目双轨并行（猴侧 ArchR、人侧官方 SnapATAC2）时注意方法学混杂。

## 一手文献（已核实 PMID/DOI）

| 文献 | 定位 |
|---|---|
| Luo S et al. **Benchmarking computational methods for single-cell chromatin data analysis.** Genome Biol 2024, PMID 39152456, DOI 10.1186/s13059-024-03356-x | **中立 benchmark（5方法×8管线×6数据集×10指标，embedding/SNN/partition 三层次）**。全文已下载 work/papers/PMC11328424_pdf_render.pdf |
| Granja JM et al. **ArchR: a scalable software package...** Nat Genet 2021, PMID 33633365 | ArchR 原文：IterativeLSI（线性 SVD），Arrow on-disk HDF5，120万细胞/8h |
| Fang R et al. **Comprehensive analysis of single cell ATAC-seq data with SnapATAC.** Nat Commun 2021, PMID 33637727 | SnapATAC v1 原文：diffusion maps + Nyström 采样，5000bp bins，纯内存 |
| Zhang K, Zemke NR et al. **SnapATAC2: a fast, scalable and versatile tool...** Nat Methods 2024, PMID 38191932 | SnapATAC2 原文：Laplacian eigenmaps，on-disk AnnData(HDF5)，线性扩展，scATAC/scRNA/scHi-C/多组学 |

## 方法定位速查

| 维度 | ArchR | SnapATAC v1 | SnapATAC2 |
|---|---|---|---|
| 语言 | R | R | Python (AnnData) |
| 降维 | Iterative LSI（线性） | Diffusion maps（Nyström） | Laplacian eigenmaps（非线性） |
| 特征 | 500bp tiles 或 peaks | 5000bp bins | 500bp bins |
| 存储 | Arrow on-disk HDF5 | 内存 | on-disk AnnData HDF5 |
| 规模 | 120万/8h | 最高100万（Nyström） | 线性扩展 |
| 双联体 | 内置 | — | Scrublet 集成 |

## Benchmark 实证关键结论（Luo 2024）

1. **聚类精度**：简单数据集 aggregation > SnapATAC2 > SnapATAC > Signac > ArchR（ArchR/Signac 难识别稀有类型）；
   复杂数据集（层级结构+高相似亚型，如脑组织）**SnapATAC/SnapATAC2_cosine 最强，ArchR 最差**（>60% 细胞负 Silhouette）。
2. **库大小偏差（重要陷阱）**：LSI 方法（ArchR/Signac）嵌入与测序深度强相关，第一成分几乎总被片段数主导（需手动去掉 r>0.75 成分，过滤后相关性仍 0.5–0.75）；**SnapATAC/SnapATAC2（Jaccard 距离）几乎不受影响（<0.3）**。
   → 跨样本/跨年龄/跨个体比较可及性时，库大小混杂会污染"年龄效应"。
3. **基因活性打分**：SnapATAC/SnapATAC2 优于 ArchR/Signac（与 ArchR 原文宣称相反——须中立 benchmark）。
4. **速度/内存**：SnapATAC2 运行最快；**ArchR 内存最省**；SnapATAC v1 小数据内存低但随数据量急剧上升 → **>2万细胞不可扩展**。
   ArchR_peaks 比 ArchR_tiles 慢近 2 倍（二轮聚类+peak call）。
5. **参数建议**：SnapATAC/2 潜在维度 10–30；Signac/ArchR 10–50。peaks vs bins、一步 vs 两步 peak calling 性能基本无差异。

## 对跨物种 CRE 专利项目的影响

- 猴海马侧 ArchR 管线已跑通（Arrow + TileMatrix + GroupCoverages + Motif），专利实施例（L2 可及性 Spearman、L3 footprinting、CRECS 打分）**全部建立在 ArchR 输出上** → 换管线=实施例重跑+重新验证，方法论变更而非工具偏好。
- 人海马侧 GSE278576 官方流程是 SnapATAC2（fragments → import → filter_cells → tile matrix → scrublet → spectral → leiden → MACS3）。Windows 装不上 SnapATAC2（无 wheel）→ 官方 cCRE 复用路径可跳过；Linux 集群跑 40 样本应优先官方原生路径。
- **方法学混杂风险**：人侧 SnapATAC2 vs 猴侧 ArchR，两侧聚类/特征定义逻辑不同 → L2/L3 跨物种对比被工具差异污染。严格做法：两侧统一特征定义（如都按 500bp tile 矩阵对比，而非一侧 tile 一侧 peaks）。

## 抓摘要/全文的可用路径（本次实测有效）

```bash
# Europe PMC REST 抓摘要（含 abstractText 全文段）
curl -s 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:<PMID>&resultType=core&format=json'

# PMC 全文 PDF 直链可下载（OA 论文）
# https://europepmc.org/articles/PMC<id>?pdf=render

# PDF 提文本：pdftotext（extract_params_from_pdf 脚本路径失效时的替代）
pdftotext '<pdf>' '<out>.txt' && grep -n -i '<keyword>' '<out>.txt'
```

坑：execute_code 内 `python -c "..."` 里写 f-string 带 `{}` 会报 f-string 语法错 → 用 write_file 落独立脚本再 `python script.py` 执行。

## 2026-08-11 第三次调研补充（完整 15 维度报告：results/memomics-1f916507/archr_vs_snapatac_report.md）

### 引用勘误（铁律：委托给的 PMID/DOI 引用前必须先 query_ncbi/pubmed 核实）
- 实测委托资料给错 PMID：31072930 实为 PNAS 纹状体论文（10.1073/pnas.1901712116）、31061468 实为 Sci Rep 植物 RNAi 论文（10.1038/s41598-019-43443-9），均与 ArchR/SnapATAC 无关。
- SnapATAC2 正式版 DOI 是 10.1038/s41592-023-02139-9（PubMed 核实），网上流传的 10.1038/s41592-024-02229-8 无法匹配。
- SnapATAC 2019 预印本：Fang et al. bioRxiv 615179, DOI 10.1101/615179。

### SnapATAC v1 维护状态（GitHub API 实测 2026-08）
- 322 stars/134 forks，最后 push 2023-04-27；README 标注 "Latest Updates: 2019-09-19" 且首行推荐 SnapATAC2 → **确认 EOL，新项目禁用**。
- 组件：SnapTools（Python 2.7，构建 .snap 文件）+ SnapATAC R 包（R 3.4–3.6）。后期版本补齐 leiden/批次校正/chromVAR motif/scRNA 整合，但**无内置双联体、无伪重复**。

### SnapATAC2 官方管线细节（scverse 文档 2.10.0 实测；文档域名 kzhang.org → 301 到 https://scverse.org/SnapATAC2/）
- 标准流程：import_fragments（backed h5ad，自动算 n_fragment/frac_dup/frac_mito）→ metrics.tsse/frip/frag_size_distr → filter_cells(min_counts, min_tsse, max_counts) → add_tile_matrix（500bp 默认，bin_size 可调）→ select_features(n_features=250000，支持 blacklist) → scrublet+filter_doublets（定制 Scrublet）→ tl.spectral → tl.umap → pp.knn + tl.leiden → 注释。
- Peak calling：**tl.macs3(groupby=, replicate= 参数支持可重复 peak)** → tl.merge_peaks（统一非重叠固定宽）→ pp.make_peak_matrix。GSE278576 官方同款：`macs3 --ext 150 --shift -75 --nomodel -g hs -q 0.1 --call-summits`。
- 差异可及性：tl.marker_regions（z-score 快筛）vs **tl.diff_test（单细胞级回归检验，min_log_fc=0.25/min_pct=0.05 预过滤，比 ArchR 伪 bulk wilcoxon 粒度更细）**。
- 批次校正：pp.mnc_correct(batch=, groupby= 保留组间生物学差异)；另有 harmony / scanorama_integrate。
- Atlas 规模参考：92 样本 645,353 细胞（AnnDataSet）谱嵌入 ~15min、knn+leiden ~5min（普通服务器）。
- **缺失模块**：无 footprinting / chromVAR deviations / co-accessibility（需自组装）；注释走 make_gene_matrix→MAGIC→scanpy 或 SCANVI 标签转移（官方教程）。

### ArchR 手册核实细节（bookdown 章节实测）
- 伪重复 5 级优先级（sample-aware → 跨样本无放回 → 组内有放回），参数 minCells/minReps/maxReps/sampleRatio；第 4/5 级含细胞重叠，下游需谨慎。
- iLSI：默认 2 轮、varFeatures=25000、dimsToUse=1:30；**corCutOff 自动剔除与测序深度高相关维度**（对库大小偏倚的内置对策，但不彻底，Luo 2024 实测 |r| 残留 0.5–0.75）。
- GeneScore 模型：基因体 + 指数衰减 e^(-|d|/5000) + 基因边界 + 1/基因长度加权（硬上限 5），默认 ±100kb 窗口；Arrow 创建时默认算好（GeneScoreMatrix）。
- 双联体：in silico 合成双联体（混合 reads）→ UMAP 投影找最近邻；10 细胞系 demuxlet 验证 AUC>0.90。
- 输入：fragments/BAM → 分块临时 HDF5 → Arrow "fragments" 组（scanTabix/scanBam）。

### 抓取路径实测补充（2026-08 有效）
- **github.com 页面 HTML**（README 在 `<article class="markdown-body">`，python urllib + UA header 可抓，含完整 README 文本）✅；api.github.com/repos/<owner>/<repo> JSON（stars/forks/pushed_at/language）✅
- scverse.org/SnapATAC2/tutorials/*.html ✅（含完整代码块+运行日志，可直接提取性能数字）；archrproject.com/bookdown/*.html ✅（手册每章独立页面，目录见 index.html）
- europepmc REST 摘要（EXT_ID:<pmid>&resultType=core）✅；fullTextXML 对 Nature Methods 收费论文不可靠（返回空）→ **兜底：摘要 + 官方 README + 中立 benchmark 全文三方交叉验证，不依赖单篇收费全文**。
- 抓取失败时依次尝试：github.com HTML（README 内嵌）→ api.github.com → Bioconductor/PyPI 包页 → europepmc 摘要；用 write_file 落独立 python 脚本批量抓（curl -o 在部分网络下会静默 0 字节）。
