"""
example_usage.py
================
Minimal example: generate an HTML report for any bioinformatics analysis
using html_report_builder.py.

Run:
    python example_usage.py

Output:
    my_analysis_report.html   (~2–10 MB depending on figure sizes)

Adapt this template for:
  - DEG analysis (volcano plots + DEG tables)
  - GSEA / pathway enrichment
  - scRNA-seq clustering
  - hdWGCNA (see hdwgcna_report_generator.py for the full version)
  - Proteomics, ATAC-seq, spatial transcriptomics, ...
"""

from html_report_builder import ReportBuilder, color_badge, fmt_number

# ── 1. Instantiate the builder ─────────────────────────────────────────────────
rb = ReportBuilder(
    title="Differential Expression Analysis\nDataset Name · DESeq2 · 2025",
    subtitle="RNA-seq | Condition A vs Condition B | n=6 per group",
    author="Your Name",
    logo_text="DEG Report",
    logo_sub="Condition A vs B",
    stats=[
        ("12,450", "Total Genes"),
        ("1,234",  "DEGs (FDR<0.05)"),
        ("678",    "Up-regulated"),
        ("556",    "Down-regulated"),
        ("48",     "Samples"),
    ],
    key_findings=[
        "<strong>Top up-regulated gene:</strong> GENE_A (log2FC=+4.2, FDR=1e-45)",
        "<strong>Top pathway:</strong> Oxidative phosphorylation (NES=2.1, FDR=0.001)",
        "<strong>Key TF:</strong> MYC targets enriched in up-regulated genes",
        "Batch correction with ComBat-seq; PCA shows clean separation after correction",
    ],
)

# ── 2. Section: QC & Overview ──────────────────────────────────────────────────
with rb.section("qc", "1. Quality Control & Overview", "质控与数据概览",
                nav_group="Data"):

    rb.add_callout("info", "Data Summary",
        "Raw counts matrix: 12,450 genes × 48 samples. "
        "Filtered: genes expressed in ≥10% of samples. "
        "Normalization: DESeq2 median-of-ratios.")

    rb.add_figure(
        fig_path="figures/pca_plot.png",          # ← replace with your file
        caption_en="Figure 1. PCA of normalized counts. Samples colored by condition.",
        title_en="Figure 1: PCA Plot",
        title_zh="主成分分析",
        method_zh="使用 DESeq2 的 vst() 方差稳定化转换后进行 PCA，按条件着色。",
        result_zh="PC1 解释 38% 的方差，两组样本在 PC1 上完全分离，批次效应已通过 ComBat-seq 校正。",
        bio_zh="样本间的清晰分离说明条件差异是数据中最主要的变异来源，批次效应已被有效消除，后续差异分析结果可靠。",
    )

    rb.add_figure(
        fig_path="figures/library_size.png",      # ← replace with your file
        caption_en="Figure 2. Library size distribution across samples.",
        title_en="Figure 2: Library Size",
        title_zh="文库大小分布",
        method_zh="统计每个样本的总 read 数，箱线图展示各组分布。",
        result_zh="各样本文库大小在 20–35M reads 之间，组间无显著差异 (Wilcoxon p=0.42)。",
        bio_zh="文库大小均匀分布确保了样本间的可比性，不会引入系统性偏差。",
        full_width=False,
    )

# ── 3. Section: Differential Expression ───────────────────────────────────────
with rb.section("deg", "2. Differential Expression", "差异表达分析",
                nav_group="Analysis"):

    rb.add_callout("warning", "Statistical Thresholds",
        "DEGs defined as: |log2FC| > 1 AND FDR (BH) < 0.05. "
        "Wald test in DESeq2. Independent filtering applied.")

    rb.add_figure(
        fig_path="figures/volcano_plot.png",      # ← replace with your file
        caption_en="Figure 3. Volcano plot. Red: up-regulated; Blue: down-regulated; Grey: NS.",
        title_en="Figure 3: Volcano Plot",
        title_zh="火山图",
        method_zh="DESeq2 Wald 检验，BH 法校正多重检验。横轴为 log2 fold-change，纵轴为 -log10(FDR)。",
        result_zh="共 1,234 个 DEGs (FDR<0.05, |log2FC|>1)：678 个上调，556 个下调。最显著基因：GENE_A (log2FC=+4.2)。",
        bio_zh="上调基因富集于代谢通路，下调基因富集于免疫相关通路，提示条件 A 激活了代谢重编程并抑制了免疫应答。",
    )

    rb.add_figure(
        fig_path="figures/heatmap_top50.png",     # ← replace with your file
        caption_en="Figure 4. Heatmap of top 50 DEGs (by FDR). Z-score normalized.",
        title_en="Figure 4: Top DEG Heatmap",
        title_zh="Top 50 DEG 热图",
        method_zh="取 FDR 最小的 50 个 DEG，对每个基因进行 Z-score 标准化，ComplexHeatmap 绘制。",
        result_zh="样本按条件聚类，两组间基因表达模式清晰分离。上调基因（红色）在条件 A 中高表达，下调基因（蓝色）在条件 B 中高表达。",
        bio_zh="热图直观展示了两组间最显著的转录组差异，为后续功能富集分析提供了候选基因集。",
    )

    # Interactive DEG table
    rb.add_table(
        table_id="tbl_deg",
        csv_path="tables/deg_results.csv",        # ← replace with your file
        title_en="DEG Results Table",
        title_zh="差异表达基因完整结果",
        columns=[
            ("gene",       "Gene"),
            ("log2FC",     "log2FC"),
            ("pvalue",     "p-value"),
            ("padj",       "FDR (BH)"),
            ("baseMean",   "Base Mean"),
        ],
        fmt={
            "log2FC":   lambda v: fmt_number(v, 3),
            "pvalue":   lambda v: fmt_number(v, 4),
            "padj":     lambda v: fmt_number(v, 4),
            "baseMean": lambda v: fmt_number(v, 1),
        },
        tip="可在搜索框输入基因名筛选，点击列标题排序。仅显示 FDR<0.05 的基因。",
    )

# ── 4. Section: Pathway Enrichment ────────────────────────────────────────────
with rb.section("pathway", "3. Pathway Enrichment", "通路富集分析",
                nav_group="Analysis"):

    rb.add_figure(
        fig_path="figures/gsea_dotplot.png",      # ← replace with your file
        caption_en="Figure 5. GSEA enrichment dot plot. Top 20 pathways by NES.",
        title_en="Figure 5: GSEA Results",
        title_zh="GSEA 富集结果",
        method_zh="使用 clusterProfiler::GSEA() 对所有基因按 log2FC 排序后进行基因集富集分析，KEGG + GO-BP 数据库，BH-FDR<0.05。",
        result_zh="共 87 个显著富集通路 (FDR<0.05)。最显著上调通路：Oxidative phosphorylation (NES=2.1)；最显著下调通路：Cytokine signaling (NES=-1.8)。",
        bio_zh="氧化磷酸化通路的上调提示条件 A 增强了线粒体功能；细胞因子信号通路的下调与免疫抑制表型一致，可能与 TGF-β 信号激活有关。",
        full_width=True,
    )

    rb.add_table(
        table_id="tbl_gsea",
        csv_path="tables/gsea_results.csv",       # ← replace with your file
        title_en="GSEA Results Table",
        title_zh="GSEA 完整结果",
        tip="可按通路名称或 NES 方向搜索。NES>0 表示在条件 A 中富集，NES<0 表示在条件 B 中富集。",
    )

# ── 5. Section: Analysis Pipeline ─────────────────────────────────────────────
with rb.section("pipeline", "4. Analysis Pipeline", "分析流程",
                nav_group="Methods"):

    rb.add_pipeline([
        {"icon": "📥", "title": "Raw Counts",
         "subtitle": "Input data",
         "params": "12,450 genes × 48 samples · HTSeq counts",
         "desc": "原始 read counts 矩阵，来自 STAR 比对 + HTSeq 计数。"},
        {"icon": "🧹", "title": "QC & Filtering",
         "subtitle": "Low-expression gene removal",
         "params": "min_count=10 in ≥10% samples",
         "desc": "过滤低表达基因，保留在至少 10% 样本中有 ≥10 reads 的基因。"},
        {"icon": "🔧", "title": "Normalization",
         "subtitle": "DESeq2 median-of-ratios",
         "params": "estimateSizeFactors() · vst()",
         "desc": "使用 DESeq2 的中位数比率法进行标准化，vst() 用于可视化。"},
        {"icon": "📊", "title": "Differential Expression",
         "subtitle": "DESeq2 Wald test",
         "params": "design = ~ batch + condition · BH-FDR",
         "desc": "Wald 检验，模型中包含批次效应协变量，BH 法校正多重检验。"},
        {"icon": "🔍", "title": "Pathway Enrichment",
         "subtitle": "GSEA + ORA",
         "params": "clusterProfiler · KEGG + GO-BP · FDR<0.05",
         "desc": "对所有基因进行 GSEA，对 DEG 进行 ORA，使用 KEGG 和 GO-BP 数据库。"},
    ])

# ── 6. Save ────────────────────────────────────────────────────────────────────
rb.save("my_analysis_report.html")
print("Done! Open my_analysis_report.html in your browser.")
