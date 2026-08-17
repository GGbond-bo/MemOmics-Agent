"""
scTour 双路线 HTML 报告生成模板（可复用）
=============================================
基于 bioinformatics-html-report skill 的 ReportBuilder。
适配 2026-07-08 人类骨骼肌衰老 SMF 双路线分析验证通过。

使用方式：
1. 修改 BASE 路径为你的 scTour 结果目录
2. 调整 ROUTE_A / ROUTE_B 路径指向你的最佳配置
3. 修改 key_findings/stats 为你的实际数据
4. 调整 add_figure 中的图路径和解读文本
5. 运行：python generate_html_report.py
"""
import sys, os

# 路径配置 —— 使用时修改此处
BASE = "results/<species>_<tissue>_<direction>_<date>/03_advanced/scTour"
ROUTE_A = f"{BASE}/routeA/run1_balanced"
ROUTE_B = f"{BASE}/routeB/run1_balanced"
SCRIPTS_DIR = f"{BASE}/scripts"

# 加载 ReportBuilder
builder_dir = "MEMOMICS_HOME/hermes_home/skills/bioinformatics/bioinformatics-html-report"
sys.path.insert(0, builder_dir)
from html_report_builder import ReportBuilder


def check_figures():
    """图片健康度检查：确保所有图片 > 5KB，无空白图"""
    figs = [
        f"{ROUTE_A}/figures/umap_overview.png",
        f"{ROUTE_A}/figures/pseudotime_boxplot.png",
        f"{ROUTE_A}/figures/vector_field.png",
        f"{ROUTE_A}/figures/age_gradient.png",
        f"{ROUTE_B}/figures/umap_overview.png",
        f"{ROUTE_B}/figures/pseudotime_boxplot.png",
        f"{ROUTE_B}/figures/vector_field.png",
        f"{ROUTE_B}/figures/age_gradient.png",
    ]
    for f in figs:
        if not os.path.exists(f):
            print(f"⚠️ 缺失: {f}")
        else:
            sz = os.path.getsize(f)
            status = "❌" if sz < 5*1024 else "✅"
            print(f"{status} {os.path.basename(f)}: {sz/1024:.0f} KB")


def build_report():
    rb = ReportBuilder(
        title="scTour 双路线轨迹分析\n<物种> · <组织> · <方向>",
        subtitle="scTour VAE 伪时间 | 双路线独立分析",
        author="MemOmics (Hermes Agent)",
        logo_text="MemOmics",
        logo_sub="scTour · Dual Route",
        stats=[
            ("<N>", "总细胞数"),
            ("2条", "独立路线"),
            ("200", "epochs/配置"),
            ("run1_balanced", "最佳配置"),
        ],
        key_findings=[
            "🧬 路线A: 关键发现1",
            "📊 路线B: 关键发现2",
            "📉 统计验证结果",
        ],
    )

    # ─── 第1节: 分析流程 ─────────────────────────────────
    with rb.section("pipeline", "1. 分析流程", "分析流程", nav_group="概述"):
        rb.add_pipeline(steps=[
            {
                "icon": "🔬",
                "title": "数据准备",
                "subtitle": "亚群提取",
                "params": "路线A/路线B 独立子集",
                "desc": "从原始数据中提取双路线各自的亚群,独立分析",
            },
            {
                "icon": "🧬",
                "title": "scTour 训练 — 路线A",
                "subtitle": "路线A描述",
                "params": "n_epochs=200, latent_dim=20",
                "desc": "路线A细胞数及训练结果概述",
            },
            {
                "icon": "🧬",
                "title": "scTour 训练 — 路线B",
                "subtitle": "路线B描述",
                "params": "n_epochs=200, latent_dim=20",
                "desc": "路线B细胞数及训练结果概述",
            },
            {
                "icon": "📊",
                "title": "验证分析",
                "subtitle": "年龄梯度 + 条件锚点",
                "params": "Spearman相关 + KS检验",
                "desc": "伪时间方向与年龄/条件严重度的相关性验证",
            },
        ])

    # ─── 第2节: 数据概览 ─────────────────────────────────
    with rb.section("data_overview", "2. 数据概览", "数据概览", nav_group="概述"):
        rb.add_table(
            table_id="tbl_route_a",
            csv_path=f"{ROUTE_A}/results/zone_stats.csv",
            title_en="Route A — Zone Statistics",
            title_zh="路线A — 各亚群伪时间+年龄统计",
            columns=[
                ("zone", "亚群"),
                ("mean_ptime", "平均伪时间"),
                ("median_ptime", "中位伪时间"),
                ("n_cells", "细胞数"),
                ("mean_age", "平均年龄"),
            ],
            fmt={
                "mean_ptime": lambda v: f"{float(v):.4f}",
                "median_ptime": lambda v: f"{float(v):.4f}",
                "mean_age": lambda v: f"{float(v):.1f}",
            },
        )
        rb.add_table(
            table_id="tbl_route_b",
            csv_path=f"{ROUTE_B}/results/zone_stats.csv",
            title_en="Route B — Zone Statistics",
            title_zh="路线B — 各亚群伪时间+年龄统计",
            columns=[
                ("zone", "亚群"),
                ("mean_ptime", "平均伪时间"),
                ("median_ptime", "中位伪时间"),
                ("n_cells", "细胞数"),
                ("mean_age", "平均年龄"),
            ],
            fmt={
                "mean_ptime": lambda v: f"{float(v):.4f}",
                "median_ptime": lambda v: f"{float(v):.4f}",
                "mean_age": lambda v: f"{float(v):.1f}",
            },
        )

    # ─── 第3节: 路线A ─────────────────────────────────
    with rb.section("route_a", "3. 路线A", "路线A", nav_group="路线A"):
        rb.add_figure(
            fig_path=f"{ROUTE_A}/figures/umap_overview.png",
            title_en="Route A — UMAP Overview",
            title_zh="路线A — UMAP伪时间总览",
            caption_en="scTour pseudotime visualization on Route A.",
            method_zh="scTour VAE 200 epoch, latent_dim=20, run1_balanced配置.",
            result_zh="各亚群伪时间分布及梯度模式.",
            bio_zh="生物学意义解读.",
            param_source_zh="scTour skill v1.5.0 | 参数来源",
        )
        rb.add_figure(
            fig_path=f"{ROUTE_A}/figures/pseudotime_boxplot.png",
            title_en="Route A — Pseudotime by Zone",
            title_zh="路线A — 各亚群伪时间箱线图",
            caption_en="Boxplot of pseudotime for each zone.",
            method_zh="scTour伪时间按亚群分组箱线图.",
            result_zh="各亚群伪时间中位数和分布范围.",
            bio_zh="伪时间梯度反映的生物学过程.",
            param_source_zh="scTour skill v1.5.0",
        )
        rb.add_figure(
            fig_path=f"{ROUTE_A}/figures/age_gradient.png",
            title_en="Route A — Pseudotime vs Age",
            title_zh="路线A — 伪时间 vs 年龄",
            caption_en="Spearman correlation between pseudotime and age.",
            method_zh="Spearman相关分析,每个细胞伪时间vs实际年龄.",
            result_zh="Spearman ρ / p值.",
            bio_zh="年龄梯度方向验证.",
            param_source_zh="scTour skill v1.5.0",
        )
        rb.add_figure(
            fig_path=f"{ROUTE_A}/figures/vector_field.png",
            title_en="Route A — Vector Field",
            title_zh="路线A — 向量场",
            caption_en="scTour neural ODE vector field.",
            method_zh="scTour神经ODE向量场,流线图展示细胞状态转换方向.",
            result_zh="向量场方向描述.",
            bio_zh="向量场方向与生物学过程的一致性.",
            param_source_zh="scTour skill v1.5.0",
        )

    # ─── 第4节: 路线B ─────────────────────────────────
    with rb.section("route_b", "4. 路线B", "路线B", nav_group="路线B"):
        rb.add_figure(
            fig_path=f"{ROUTE_B}/figures/umap_overview.png",
            title_en="Route B — UMAP Overview",
            title_zh="路线B — UMAP伪时间总览",
            caption_en="scTour pseudotime on Route B.",
            method_zh="scTour VAE 200 epoch, 独立训练.",
            result_zh="各亚群伪时间分布.",
            bio_zh="生物学意义解读.",
            param_source_zh="scTour skill v1.5.0",
        )
        rb.add_figure(
            fig_path=f"{ROUTE_B}/figures/pseudotime_boxplot.png",
            title_en="Route B — Pseudotime by Zone",
            title_zh="路线B — 各亚群伪时间箱线图",
            caption_en="Boxplot of pseudotime values.",
            method_zh="scTour伪时间按亚群分组箱线图.",
            result_zh="各亚群伪时间统计.",
            bio_zh="生物学意义解读.",
            param_source_zh="scTour skill v1.5.0",
        )
        rb.add_figure(
            fig_path=f"{ROUTE_B}/figures/vector_field.png",
            title_en="Route B — Vector Field",
            title_zh="路线B — 向量场",
            caption_en="Vector field for Route B.",
            method_zh="scTour神经ODE向量场.",
            result_zh="向量场方向描述.",
            bio_zh="与路线B生物学过程的一致性.",
            param_source_zh="scTour skill v1.5.0",
        )
        rb.add_figure(
            fig_path=f"{ROUTE_B}/figures/age_gradient.png",
            title_en="Route B — Pseudotime vs Age",
            title_zh="路线B — 伪时间 vs 年龄",
            caption_en="Pseudotime vs age for Route B.",
            method_zh="Spearman相关分析.",
            result_zh="Spearman ρ / p值.",
            bio_zh="路线B的年龄相关性解读（注意年龄和状态的区别）.",
            param_source_zh="scTour skill v1.5.0",
        )

    # ─── 第5节: 参数来源 ─────────────────────────────────
    with rb.section("param_sources", "5. 参数来源追溯", "参数来源", nav_group="方法"):
        rb.add_param_source(sources=[
            {"param": "n_epochs", "value": "200", "source": "skill",
             "citation": "scTour skill v1.5.0 — 默认值", "note": ""},
            {"param": "latent_dim", "value": "20", "source": "literature",
             "citation": "Li et al. 2023 Genome Biology", "note": ""},
            {"param": "run1_balanced vs run2_encoder", "value": "run1_balanced", "source": "debate",
             "citation": "三配置对比 — KS检验+箱线图对比裁决", "note": ""},
        ])

    # ─── 第6节: 辩论记录 ─────────────────────────────────
    with rb.section("debates", "6. 关键辩论记录", "辩论记录", nav_group="方法"):
        rb.add_debate(
            topic="双路线拆分 vs 联合训练",
            rounds=[{
                "round": 1,
                "pro": "正方论据",
                "con": "反方论据",
                "verdict": "裁决",
                "pro_score": 9, "con_score": 7,
                "action": "实施双路线独立分析",
            }],
            title_en="Route Split Decision",
            title_zh="双路线拆分决策辩论",
        )

    # ─── 第7节: 结论 ─────────────────────────────────
    with rb.section("conclusion", "7. 总结论与解读", "结论与解读", nav_group="结论"):
        rb.add_conclusion_debate(
            conclusion="核心生物学结论",
            pro_argument="支持论据",
            con_argument="质疑论据",
            verdict="最终裁决",
            confidence="高 (基于N个独立证据链)",
        )

    # ─── 第8节: 自进化日志 ─────────────────────────────────
    with rb.section("evolution_logs", "8. 自进化日志", "自进化日志", nav_group="日志"):
        rb.add_pipeline(steps=[
            {
                "icon": "📝",
                "title": "经验1: 双路线独立分析",
                "subtitle": "核心方法论",
                "params": "双路线拆分 → 各自伪时间梯度清晰",
                "desc": "两条生物学过程方向不同时,不要放在一起跑scTour.拆分后每条路线各自方向清晰.",
            },
            {
                "icon": "📝",
                "title": "经验2: 年龄梯度锚点法",
                "subtitle": "独立验证方向",
                "params": "Spearman ρ vs 年龄",
                "desc": "用年龄作为伪时间方向的独立验证锚点,不依赖分子标记.",
            },
            {
                "icon": "📝",
                "title": "经验3: 内部梯度分析",
                "subtitle": "亚群内部精细分析",
                "params": "关键基因沿伪时间LOWESS",
                "desc": "在单个亚群内部按伪时间排序,分析关键基因的表达变化,揭示过程细节.",
            },
        ])

    # 保存
    output = f"{BASE}/scTour_Dual_Route_Report.html"
    rb.save(output)
    print(f"\n{'='*60}")
    print("图片健康度检查:")
    check_figures()
    print(f"{'='*60}")
    return output


if __name__ == "__main__":
    build_report()