"""
hdwgcna_report_generator.py
============================
Complete hdWGCNA report generator using html_report_builder.py.
This is the exact script used to generate hdwgcna_report.html.

Usage:
    python hdwgcna_report_generator.py

Inputs  (edit the path constants below):
    FIG_DIR  — directory containing the 14 PNG figures
    TAB_DIR  — directory containing the 8 CSV tables
    OUT_PATH — output HTML file path

Output:
    hdwgcna_report.html  (~4–8 MB, single self-contained file)
"""

import os
from html_report_builder import ReportBuilder, color_badge, fmt_number

# ── PATHS (edit these) ─────────────────────────────────────────────────────────
FIG_DIR  = "/mnt/results/06_hdwgcna/figures"
TAB_DIR  = "/mnt/results/06_hdwgcna/tables"
OUT_PATH = "/mnt/results/hdwgcna_report.html"

def fig(name):
    return os.path.join(FIG_DIR, name)

def tab(name):
    return os.path.join(TAB_DIR, name)

# ── MODULE COLOR MAP ───────────────────────────────────────────────────────────
MOD_COLORS = {
    "M1":"#4CAF50","M2":"#00BCD4","M3":"#2196F3","M4":"#795548",
    "M5":"#FFEB3B","M6":"#E91E63","M7":"#F44336","M8":"#FF69B4",
    "M9":"#212121","M10":"#9C27B0",
}
MOD_TEXT = {
    "M1":"#fff","M2":"#fff","M3":"#fff","M4":"#fff",
    "M5":"#333","M6":"#fff","M7":"#fff","M8":"#333",
    "M9":"#fff","M10":"#fff",
}

def mod_badge(m):
    return color_badge(m, MOD_COLORS.get(m,"#999"), MOD_TEXT.get(m,"#fff"))

# ── TRAIT LABEL MAP ────────────────────────────────────────────────────────────
TRAIT_LABELS = {
    "age_group":     "Age (Old vs Young)",
    "diabetes":      "Diabetes",
    "tp_numeric":    "Exercise (Post vs Pre)",
    "condition_num": "Condition (ordered)",
}

# ══════════════════════════════════════════════════════════════════════════════
# BUILD REPORT
# ══════════════════════════════════════════════════════════════════════════════

rb = ReportBuilder(
    title="hdWGCNA Co-expression Network Analysis\nSkeletal Muscle · Aging × Diabetes × Exercise",
    subtitle="hdWGCNA v0.4.11 | WGCNA v1.72 | Seurat v5 | R 4.4 | 2025",
    author="Biomni (Phylo)",
    logo_text="hdWGCNA Report",
    logo_sub="Skeletal Muscle · Aging × Exercise",
    stats=[
        ("11,630", "Total Cells"),
        ("48",     "Samples"),
        ("7",      "Cell Subtypes"),
        ("1,296",  "Metacells"),
        ("9,875",  "Network Genes"),
        ("10",     "Modules"),
    ],
    key_findings=[
        "<strong>M1 (应激/萎缩)</strong>：衰老 r=−0.42，运动 r=−0.42，hub genes: ZBTB16, SESN1, FKBP5",
        "<strong>M7 & M10 (运动响应)</strong>：M10 r=+0.47 (最强)，M7 DME log2FC=+21.2，受 MYOD1/LEF1 调控",
        "<strong>M5 (ECM/纤毛)</strong>：在衰老和糖尿病肌肉中完全丧失保守性 (Zsummary≈0)",
        "<strong>M6 (TGF-β/纤维化)</strong>：随年龄上调 r=+0.25，受 SMAD2/3 调控",
        "<strong>M9 (线粒体)</strong>：衰老中下调 r=−0.29，但在糖尿病肌肉中高度保守 (Z=23.4)",
        "<strong>M8 (肌生成)</strong>：受 MYOD1 调控，所有比较中高度保守 (Z>10)",
    ],
)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: PIPELINE
# ══════════════════════════════════════════════════════════════════════════════
with rb.section("pipeline", "1. Analysis Pipeline", "分析流程概览",
                nav_group="Overview"):

    rb.add_html("""
    <div class="subsection">
      <h3>Why hdWGCNA for Single-Cell Data? <span class="zh-sub">为什么用 hdWGCNA？</span></h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div class="interp-block method-block">
          <span class="interp-label">传统 WGCNA 的局限</span>
          <p>传统 WGCNA 设计用于 bulk RNA-seq，直接应用于 scRNA-seq 时面临两大问题：
          ① 细胞数量过多导致计算不可行；
          ② scRNA-seq 的 dropout 效应使基因共表达信号极度噪声化。</p>
        </div>
        <div class="interp-block bio-block">
          <span class="interp-label">hdWGCNA 的解决方案</span>
          <p>通过 <strong>metacell 聚合</strong>（将 k=25 个相似细胞合并为一个 metacell）
          将细胞数量压缩至可处理规模，同时平均化 dropout 噪声。
          本研究从 11,630 个细胞构建了 1,296 个 metacell，信噪比大幅提升。</p>
        </div>
      </div>
    </div>""")

    rb.add_pipeline([
        {"icon":"📥","title":"Input Data","subtitle":"Seurat Object",
         "params":"11,630 cells · 7 subclusters · 48 samples","desc":""},
        {"icon":"⚙️","title":"SetupForWGCNA","subtitle":"Gene Selection",
         "params":"fraction ≥ 0.05 → 9,875 genes",
         "desc":"选择在 ≥5% 细胞中表达的基因，过滤低表达噪声基因，确保网络构建的统计可靠性。"},
        {"icon":"🔬","title":"MetacellsByGroups","subtitle":"Metacell Aggregation",
         "params":"k=25 · 1,296 metacells · min_cells=25",
         "desc":"将相似细胞聚合为 metacell，消除 scRNA-seq 的 dropout 噪声，使共表达信号更稳健。"},
        {"icon":"📐","title":"TestSoftPowers","subtitle":"Scale-Free Topology",
         "params":"Power = 6 · R² = 0.944",
         "desc":"选择使网络满足无标度拓扑 (R²≥0.8) 的最小软阈值，确保网络符合生物网络的幂律分布特性。"},
        {"icon":"🕸️","title":"ConstructNetwork","subtitle":"TOM Network",
         "params":"Signed · minModuleSize=30 · mergeCutHeight=0.25",
         "desc":"基于拓扑重叠矩阵 (TOM) 构建加权基因共表达网络，层次聚类识别模块。"},
        {"icon":"📊","title":"ModuleEigengenes","subtitle":"Module Summarization",
         "params":"10 modules (M1–M10) · PC1 per module",
         "desc":"每个模块的第一主成分 (PC1) 作为模块特征基因 (ME)，代表该模块的整体表达水平。"},
        {"icon":"🔗","title":"ModuleConnectivity","subtitle":"Hub Gene Ranking",
         "params":"kME = correlation(gene, ME)",
         "desc":"计算每个基因与其所在模块 ME 的 Pearson 相关系数 (kME)，kME 最高的基因为 hub gene。"},
        {"icon":"🗺️","title":"RunModuleUMAP","subtitle":"Network Visualization",
         "params":"n_hubs=10 · supervised · target_weight=0.5",
         "desc":"将基因网络降维可视化，hub gene 标注，直观展示模块内部结构和模块间关系。"},
        {"icon":"🔍","title":"Downstream Analyses","subtitle":"Trait · DME · Preservation · TF/GO",
         "params":"4 downstream modules","desc":""},
    ])

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: NETWORK CONSTRUCTION
# ══════════════════════════════════════════════════════════════════════════════
with rb.section("network", "2. Network Construction", "共表达网络构建",
                nav_group="Network"):

    rb.add_figure(
        fig("hdwgcna_softpower.png"),
        "Figure 1. Soft power threshold selection for scale-free network topology.",
        title_en="Figure 1: Soft Power Threshold",
        title_zh="软阈值选择",
        method_zh="WGCNA 使用软阈值幂函数 (β) 将基因相关系数转化为网络连接权重 (w = |r|^β)。通过扫描不同 β 值，选择使网络满足无标度拓扑 (R²≥0.8) 的最小 β 值。",
        result_zh="在 β=6 时，无标度拓扑拟合度 R²=0.944，超过 0.8 的阈值要求，同时平均连接度保持在合理范围。最终选择 <strong>soft power = 6</strong>。",
        bio_zh="生物网络普遍遵循幂律分布（少数 hub 节点连接度极高，大多数节点连接度低）。选择满足无标度拓扑的 β 值，确保构建的共表达网络符合真实生物网络的结构特征。",
    )

    rb.add_figure(
        fig("hdwgcna_dendrogram.png"),
        "Figure 2. Hierarchical clustering dendrogram with module color assignments.",
        title_en="Figure 2: Gene Co-expression Dendrogram",
        title_zh="基因共表达树状图",
        method_zh="基于拓扑重叠矩阵 (TOM) 计算基因间相似性，层次聚类后用动态树切割 (Dynamic Tree Cut) 识别模块，mergeCutHeight=0.25 合并高度相似的模块。",
        result_zh="共识别 <strong>10 个模块 (M1–M10)</strong>，大小从 30 (M10) 到 1,260 (M2) 个基因不等。7,083 个基因 (72%) 被分配到灰色模块（未归入任何模块）。",
        bio_zh="树状图中聚集在同一分支的基因具有高度相似的表达模式，意味着它们可能受相同的转录因子调控，或参与相同的生物学过程。10 个模块代表了骨骼肌中 10 种不同的基因共表达程序。",
    )

    rb.add_figure(
        fig("hdwgcna_metacell_umap.png"),
        "Figure 3. UMAP of 1,296 metacells colored by subtype, sample, group, and timepoint.",
        title_en="Figure 3: Metacell UMAP",
        title_zh="Metacell UMAP 可视化",
        method_zh="将 k=25 个最近邻细胞聚合为一个 metacell (min_cells=25)。对 metacell 对象进行标准化、FindVariableFeatures (2000 个高变基因)、PCA，再用 Harmony 对 samplename 进行批次校正，最后 UMAP 降维可视化。",
        result_zh="共构建 <strong>1,296 个 metacell</strong>，来自 6 种细胞亚群 (zone1–zone6) × 48 个样本。Harmony 批次校正后，不同样本的 metacell 混合良好，细胞亚群分离清晰。",
        bio_zh="Metacell UMAP 验证了数据质量：细胞亚群分离良好，说明不同区域的肌纤维具有不同的基因表达特征；Harmony 批次校正有效消除了样本间批次效应。",
    )

    rb.add_figure(
        fig("hdwgcna_module_umap.png"),
        "Figure 4. Gene co-expression network UMAP. Hub genes labeled.",
        title_en="Figure 4: Gene Network UMAP",
        title_zh="基因网络 UMAP",
        method_zh="基于 TOM 矩阵对所有网络基因 (9,875 个) 进行有监督 UMAP 降维 (supervised=TRUE, target_weight=0.5)，以模块归属作为监督信号，使同一模块的基因在 UMAP 上更紧密聚集。",
        result_zh="10 个模块在 UMAP 上形成清晰的聚类，模块间分离良好。Hub gene (如 ZBTB16、SESN1 in M1；TNNT1、COL1A1 in M2) 位于各自模块的核心区域。",
        bio_zh="基因网络 UMAP 直观展示了共表达网络的拓扑结构。Hub gene 位于模块核心，是该模块最具代表性的基因，也是最可能的关键调控节点，在后续功能验证中应优先关注。",
    )

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: MODULE CHARACTERIZATION
# ══════════════════════════════════════════════════════════════════════════════
with rb.section("modules", "3. Module Characterization", "模块特征分析",
                nav_group="Network"):

    rb.add_figure(
        fig("hdwgcna_hubgene_network.png"),
        "Figure 5. Hub gene co-expression network. Edge width ∝ TOM similarity.",
        title_en="Figure 5: Hub Gene Network",
        title_zh="Hub Gene 网络图",
        method_zh="对每个模块选取 top 5 hub gene (kME 最高)，加上 3 个其他高连接度基因，构建模块内和模块间的共表达网络图。节点颜色对应模块颜色，边的粗细代表 TOM 相似性，edge_prop=0.6 保留最强的 60% 边。",
        result_zh="M1 的 hub gene (ZBTB16、SESN1、FKBP5) 形成紧密的应激响应核心；M2 的 hub gene (TNNT1、COL1A1) 代表肌肉收缩和 ECM 功能；M9 的 hub gene (COX6A2、COX7A1、MT-ATP6) 均为线粒体基因。",
        bio_zh="Hub gene 是共表达模块的核心节点，具有高连接度和调控潜力。扰动 hub gene 可能影响整个模块的表达，适合作为功能验证实验的优先靶点和临床生物标志物候选。",
    )

    rb.add_figure(
        fig("hdwgcna_kme_ranking.png"),
        "Figure 6. Gene connectivity (kME) ranking within each module.",
        title_en="Figure 6: kME Connectivity Ranking",
        title_zh="kME 连接度排名",
        method_zh="kME 定义为每个基因的表达向量与其所在模块特征基因 (ME) 的 Pearson 相关系数。kME 越高，该基因与模块整体表达模式越一致，是模块的核心成员。",
        result_zh="各模块的 kME 分布显示出典型的长尾特征：少数 hub gene 具有极高的 kME (>0.6)，大多数基因的 kME 在 0.3–0.5 之间。M1 最高 kME 为 0.674 (ZBTB16)。",
        bio_zh="kME 排名有两个重要用途：① Hub gene 筛选：kME 最高的基因是模块的最佳代表，适合用于功能验证实验；② 模块质量评估：kME 分布越集中，说明模块内部共表达越紧密，模块质量越高。",
    )

    rb.add_figure(
        fig("hdwgcna_module_feature_umap.png"),
        "Figure 7. Module eigengene (ME) activity projected onto single-cell UMAP.",
        title_en="Figure 7: Module Feature UMAP",
        title_zh="模块特征基因在细胞 UMAP 上的活性",
        method_zh="将每个模块的特征基因 (ME) 值投影到原始单细胞 UMAP 上，颜色深浅代表该细胞中模块的活性强弱。ME 是模块内所有基因表达的第一主成分。",
        result_zh="不同模块在细胞 UMAP 上呈现出不同的空间分布模式：M2 在所有细胞亚群中均有活性；M9 在 zone4–zone6 中活性更强；M5 和 M10 等小模块的活性分布更局限。",
        bio_zh="模块在细胞 UMAP 上的分布模式揭示了模块与细胞类型的对应关系。活性集中在特定区域的模块可能代表该细胞亚群的特征基因程序；活性分布广泛的模块代表骨骼肌的普遍功能程序。",
        full_width=True,
    )

    rb.add_figure(
        fig("hdwgcna_dotplot_modules.png"),
        "Figure 8. DotPlot: module activity across cell subtypes. Size = % ME>0; Color = avg ME.",
        title_en="Figure 8: Module Activity DotPlot",
        title_zh="模块活性 × 细胞类型点图",
        method_zh="对每种细胞亚群，计算各模块 ME 的平均值 (颜色) 和 ME>0 的细胞比例 (点大小)，生成点图。红色表示模块在该细胞类型中高度活跃，蓝色表示低活性。",
        result_zh="M2 (肌肉收缩) 在所有 zone 中均高度活跃；M9 (线粒体) 在 zone4–zone6 中活性更强，提示这些区域的肌纤维氧化代谢更活跃；NMJ 细胞在多数模块中活性较低。",
        bio_zh="模块-细胞类型对应关系为后续研究提供了重要线索：细胞类型特异性高的模块可能代表该细胞亚群的功能特征，适合作为细胞类型标志物；结合 DME 分析，可判断哪些细胞亚群的哪些模块在衰老/运动中发生了最显著的变化。",
    )

    rb.add_table(
        tab("hdwgcna_hub_genes.csv"),
        table_id="tbl_hub",
        title_en="Hub Genes (Top 25 per Module)",
        title_zh="Hub Gene 完整列表（可搜索/排序）",
        columns=[("gene_name","Gene"), ("module","Module"), ("kME","kME")],
        fmt={"module": mod_badge, "kME": lambda v: fmt_number(v, 4)},
        tip="可在搜索框中输入基因名或模块名进行筛选，点击列标题排序。共 250 个 hub gene（每模块 top 25，按 kME 降序）。",
    )

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: TRAIT CORRELATION
# ══════════════════════════════════════════════════════════════════════════════
with rb.section("trait", "4. Module-Trait Correlation", "模块-表型关联分析",
                nav_group="Downstream"):

    rb.add_figure(
        fig("hdwgcna_trait_correlation.png"),
        "Figure 9. Pearson correlation between module eigengenes and clinical traits. * FDR<0.05, ** FDR<0.01, *** FDR<0.001.",
        title_en="Figure 9: Module-Trait Correlation Heatmap",
        title_zh="模块-表型相关性热图",
        method_zh="对每个细胞，提取其所在模块的 ME 值，与四个数值型表型变量 (age_group: 0=Young/1=Old；diabetes: 0=无DM/1=有DM；tp_numeric: 0=Pre/1=Post；condition_num: 0-5 有序编码) 计算 Pearson 相关系数，BH 法校正多重检验 (FDR)。",
        result_zh="所有 40 个模块-表型对均达到统计显著性 (FDR~0)。主要发现：M1 (r=-0.42) 和 M4 (r=-0.37) 随年龄下调；M10 (r=+0.47) 和 M7 (r=+0.31) 运动后上调；M6 (r=+0.25) 随年龄上调。",
        bio_zh="M1 的双重下调 (衰老 r=-0.42，运动 r=-0.42) 提示应激/萎缩程序在老年肌肉中持续受抑；M10 的强运动响应 (r=+0.47) 结合 LEF1 调控提示 Wnt 信号在运动适应中的核心作用；M6 的年龄上调结合 SMAD2/3 调控，为老年肌肉纤维化提供了分子证据。",
    )

    rb.add_table(
        tab("hdwgcna_trait_cor.csv"),
        table_id="tbl_trait",
        title_en="Module-Trait Correlation Table",
        title_zh="完整相关系数表",
        columns=[("module","Module"),("trait","Trait"),("r","Pearson r"),("fdr","FDR (BH)")],
        fmt={
            "module": mod_badge,
            "trait": lambda v: TRAIT_LABELS.get(v, v),
            "r": lambda v: fmt_number(v, 4),
            "fdr": lambda v: fmt_number(v, 4),
        },
        tip="r 值为 Pearson 相关系数 (-1 到 +1)，FDR 为 BH 校正后的 p 值。正值表示该表型增加时模块活性升高，负值表示降低。",
    )

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: DME
# ══════════════════════════════════════════════════════════════════════════════
with rb.section("dme", "5. Differential Module Eigengene (DME) Analysis",
                "差异模块特征基因分析", nav_group="Downstream"):

    rb.add_callout("warning", "重要注意事项：DME 的 log2FC 解读",
        "模块特征基因 (ME) 是 PCA 的第一主成分得分，<strong>不是归一化到 [-1,1] 的值</strong>，"
        "因此 DME 的 avg_log2FC 反映的是 ME 得分差异，数值可能很大 (如 M7 的 +21.2)。"
        "<strong>不应将其与传统基因表达 fold-change 直接比较</strong>。"
        "在论文中应报告方向性 (上调/下调) + FDR，而非 fold-change 数值本身。")

    rb.add_figure(
        fig("hdwgcna_dme_volcano.png"),
        "Figure 10. DME volcano plots: Aging, Aging+DM, Exercise. Wilcoxon test, BH-FDR.",
        title_en="Figure 10: DME Volcano Plots",
        title_zh="差异模块特征基因火山图",
        method_zh="FindDMEs() 函数对每个模块的 ME 值在两组细胞间进行 Wilcoxon 秩和检验，BH 法校正多重检验。三个对比：① Aging: Old_normal_Pre vs Young_normal_Pre；② Aging+DM: Old_diabete_Pre vs Young_normal_Pre；③ Exercise: Old_normal_Post vs Old_normal_Pre。",
        result_zh="衰老：M3 (↓)、M1 (↓)、M9 (↑)、M6 (↑)、M4 (↓) 显著变化。衰老+糖尿病：M1 (↓)、M9 (↑)、M4 (↓)、M6 (↑↑) 显著；M7 不显著 (FDR=1.0)。运动：M7 (↑↑↑)、M10 (↑↑)、M1 (↓↓) 均显著，几乎所有模块均响应运动。",
        bio_zh="衰老与衰老+糖尿病共同下调 M1、M3、M4，共同上调 M6、M9，说明这些变化是衰老的核心特征。M7 在糖尿病中不响应运动 (FDR=1.0)，提示糖尿病可能损害了运动诱导的肌肉适应性。",
    )

    rb.add_figure(
        fig("hdwgcna_dme_violin.png"),
        "Figure 11. Violin plots: ME score distributions across six conditions for all 10 significant modules.",
        title_en="Figure 11: DME Violin Plots",
        title_zh="显著模块 ME 分布小提琴图",
        method_zh="对所有在任意对比中显著的模块 (FDR<0.05)，绘制 ME 值在 6 个条件 (Young_normal_Pre/Post, Old_normal_Pre/Post, Old_diabete_Pre/Post) 下的分布小提琴图。",
        result_zh="10 个模块均在至少一个对比中显著。M1 在 Young_normal 中 ME 最高，随年龄和运动后降低；M7 和 M10 在运动后 (Post) ME 显著升高；M6 在 Old 组中 ME 升高，在 Old_diabete 中最高。",
        bio_zh="M7/M10 的运动特异性激活（仅在 Post 条件下升高）说明这是急性运动响应而非慢性适应；M6 的年龄特异性上调与纤维化的慢性进展一致。",
        full_width=True,
    )

    rb.add_table(
        tab("hdwgcna_dme_results.csv"),
        table_id="tbl_dme",
        title_en="DME Results Table",
        title_zh="差异模块分析完整结果",
        columns=[("module","Module"),("contrast","Contrast"),
                 ("avg_log2FC","ME Score Diff"),("p_val_adj","FDR")],
        fmt={
            "module": mod_badge,
            "avg_log2FC": lambda v: fmt_number(v, 3),
            "p_val_adj": lambda v: fmt_number(v, 4),
        },
        tip="avg_log2FC: ME 得分差异 (正值=group1高于group2)；FDR: BH校正p值。",
    )

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6: PRESERVATION
# ══════════════════════════════════════════════════════════════════════════════
with rb.section("preservation", "6. Module Preservation Analysis",
                "模块保守性分析", nav_group="Downstream"):

    rb.add_callout("warning", "方法局限性",
        "本分析使用 50 次置换检验 (nPermutations=50, quickCor=1) 以节省计算时间。"
        "对于发表级别的结果，建议增加到 200 次置换 (nPermutations=200, quickCor=0)，"
        "以获得更精确的 Zsummary 估计。当前结果的方向性可靠，但具体 Z 值可能有轻微偏差。")

    rb.add_figure(
        fig("hdwgcna_preservation.png"),
        "Figure 12. Module preservation. Zsummary > 10: highly preserved; 2-10: moderate; < 2: not preserved.",
        title_en="Figure 12: Module Preservation",
        title_zh="模块保守性分析",
        method_zh="使用 WGCNA::modulePreservation() 函数，以 Young_normal 的 metacell 表达矩阵为参考，分别与 Old_normal 和 Old_diabete 的 metacell 矩阵比较。Zsummary 综合了多个保守性统计量，Z>10 表示高度保守，2<Z<10 表示中等保守，Z<2 表示不保守。",
        result_zh="vs Old_normal：M1 (Z=15.0)、M2 (Z=14.9)、M8 (Z=11.0) 高度保守；M5 (Z=1.9) 不保守。vs Old_diabete：M9 (Z=23.4)、M4 (Z=19.1)、M1 (Z=18.8) 极高保守；M5 (Z=0.003) 完全不保守。",
        bio_zh="M5 (ECM/纤毛模块) 在衰老和糖尿病肌肉中完全不保守，说明这些基因在老年/糖尿病肌肉中不再协同表达，可能是 Young_normal 特有的肌肉维护程序。M9 在糖尿病肌肉中超高保守性 (Z=23.4) 提示线粒体基因程序结构完整，但整体活性下降。",
    )

    rb.add_table(
        tab("hdwgcna_preservation.csv"),
        table_id="tbl_pres",
        title_en="Module Preservation Table",
        title_zh="模块保守性完整结果",
        columns=[("module","Module"),("comparison","Comparison"),
                 ("Zsummary","Zsummary"),("medianRank","Median Rank")],
        fmt={
            "module": mod_badge,
            "Zsummary": lambda v: fmt_number(v, 2),
            "medianRank": lambda v: fmt_number(v, 1),
        },
        tip="Zsummary > 10: 高度保守；2-10: 中等保守；< 2: 不保守。Median Rank 越低表示保守性越好。",
    )

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7: TF / GO ENRICHMENT
# ══════════════════════════════════════════════════════════════════════════════
with rb.section("enrichment", "7. TF & GO Enrichment Analysis",
                "转录因子与 GO 富集分析", nav_group="Downstream"):

    rb.add_callout("info", "方法说明",
        "TF 富集使用 enrichR (ChEA_2022 + ENCODE_TF_ChIP-seq_2015 数据库)，"
        "对每个模块的 top 25 hub gene 进行富集分析。"
        "GO 富集使用 clusterProfiler (GO-BP 本体，org.Hs.eg.db)，BH-FDR<0.05。"
        "注：本分析使用 enrichR 替代 TFBSTools (CNEr 依赖编译失败)，"
        "结果基于 ChIP-seq 实验数据，可靠性高。")

    rb.add_figure(
        fig("hdwgcna_tf_enrichment.png"),
        "Figure 13. TF enrichment for hub genes. enrichR, ChEA_2022 + ENCODE. FDR < 0.05.",
        title_en="Figure 13: TF Regulatory Enrichment",
        title_zh="转录因子调控富集",
        method_zh="对每个模块的 top 25 hub gene，使用 enrichR 在 ChEA_2022 (TF ChIP-seq 靶基因数据库) 和 ENCODE_TF_ChIP-seq_2015 中进行富集分析。点的大小和颜色均代表 -log10(FDR)，越大/越红表示富集越显著。",
        result_zh="共 105 个显著 TF-模块关联 (FDR<0.05)。主要发现：TBX20→M1 (FDR=3.4e-5)；MYOD1→M8 (FDR=5.2e-4)；SMAD2/3→M6 (FDR=0.015)；LEF1→M10 (FDR=4.9e-4)；NELFE→M9 (FDR=3.1e-6)；LXR→M4。",
        bio_zh="MYOD1→M8：MYOD1 是骨骼肌分化的主调控因子，M8 的高保守性与 MYOD1 的核心调控地位一致；SMAD2/3→M6：TGF-β/SMAD 信号驱动的纤维化模块在衰老中上调，为抗纤维化干预提供了分子靶点；LEF1→M10：Wnt/LEF1 信号在运动后激活，提示 Wnt 激动剂可能模拟运动对老年肌肉的保护效应。",
    )

    rb.add_figure(
        fig("hdwgcna_hub_enrichment.png"),
        "Figure 14. GO Biological Process enrichment for hub genes. clusterProfiler, BH-FDR < 0.05.",
        title_en="Figure 14: Hub Gene GO Enrichment",
        title_zh="Hub Gene GO 生物过程富集",
        method_zh="对每个模块的 top 25 hub gene，使用 clusterProfiler::enrichGO() 进行 GO 生物过程 (GO-BP) 富集分析，BH-FDR<0.05，每个模块展示 top 5 显著条目。",
        result_zh="7/10 个模块有显著 GO-BP 富集 (FDR<0.05)。M2：muscle contraction (FDR=0.0018)；M4：triglyceride biosynthetic process (FDR=0.0028)；M3：lncRNA-mediated post-transcriptional regulation (FDR=0.014)；M10：regulation of small GTPase mediated signaling (FDR=0.011)。",
        bio_zh="GO 富集分析验证了基于 hub gene 的模块命名：M2 的肌肉收缩富集与 hub gene TNNT1 一致；M4 的脂质代谢富集与 LXR 调控和衰老中的下调一致；M3 的 lncRNA 调控富集提示 lncRNA 介导的转录后调控在衰老肌肉中受损，是一个值得深入研究的新颖衰老机制。",
    )

    rb.add_table(
        tab("hdwgcna_tf_enrichment.csv"),
        table_id="tbl_tf",
        title_en="TF Enrichment Table (Top 80)",
        title_zh="转录因子富集完整结果",
        columns=[("module","Module"),("TF","Transcription Factor"),
                 ("database","Database"),("Adjusted.P.value","FDR"),("Overlap","Overlap")],
        fmt={"module": mod_badge, "Adjusted.P.value": lambda v: fmt_number(v, 4)},
        tip="可按模块名 (如 M1) 或 TF 名称搜索。Overlap 列显示 hub gene 中有多少个是该 TF 的靶基因。",
        max_rows=80,
    )

    rb.add_table(
        tab("hdwgcna_go_enrichment.csv"),
        table_id="tbl_go",
        title_en="GO Enrichment Table",
        title_zh="GO 生物过程富集完整结果",
        columns=[("module","Module"),("Description","GO Term"),
                 ("p.adjust","FDR"),("Count","Gene Count")],
        fmt={"module": mod_badge, "p.adjust": lambda v: fmt_number(v, 4)},
        tip="可按模块名或 GO 条目关键词搜索。Count 列显示富集到该 GO 条目的 hub gene 数量。",
    )

# ══════════════════════════════════════════════════════════════════════════════
# SAVE
# ══════════════════════════════════════════════════════════════════════════════
rb.save(OUT_PATH)
print(f"Report saved to: {OUT_PATH}")
