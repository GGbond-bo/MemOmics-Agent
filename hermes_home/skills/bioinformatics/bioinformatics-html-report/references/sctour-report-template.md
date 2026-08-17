# scTour 综合 HTML 报告模板

> 基于 2026-07-08 人类骨骼肌衰老·糖尿病·运动 scTour 分析的成功实践。
> 生成的报告：5.4 MB，9 个章节，10 张图，4 个表格，5 轮辩论，离线可查看。

## 报告结构（9 章节）

| # | 章节 | 内容 | 数据来源 |
|:-:|:----|:----|:--------|
| 1 | 分析流程 | 7 步 Pipeline 流程图 | 代码中的 `add_pipeline(steps=[...])` |
| 2 | 数据概览 | 分组统计表 + 亚群统计表 | `results/final_group_stats.csv`, `final_subcluster_stats.csv` |
| 3 | UMAP 概览 | scTour 伪时间总览图 + UMAP 细胞类型标注 | `figures/sctour_overview.png`, `final_umap_overview.png` |
| 4 | 三配置对比 | KS 热图 + Δ均值对比 + 箱线图对比 | `comparison/figures/` 下所有 PNG |
| 5 | 最终结果 | 6 张图：向量场、伪时间vs年龄、运动效应、箱线图 | `run1_balanced/figures/final_*.png` |
| 6 | 参数来源 | 6 个关键参数的自上而下来源追溯 | 每次 `debate_analysis` 裁决中的 `action` 字段 |
| 7 | 辩论记录 | 5 轮完整辩论（35 独立论点 + 5 裁判裁决） | `log/debate_*.json` 读取后渲染 |
| 8 | 自进化日志 | 运行记录列表 | `log/run_record_*.json` 读取后渲染 |
| 9 | 结论 | 结论辩论 + 分析总结 | `debate_analysis` 裁决 + 用户确认 |

## 关键代码模式

### 1. 图片健康度检查（生成前验证）

```python
import os
MIN_SIZE = 5 * 1024  # 5KB
for fig in all_figures:
    size = os.path.getsize(fig)
    if size < MIN_SIZE:
        print(f"WARN: {fig} is only {size} bytes — will be blank!")
```

### 2. 辩论 JSON 读取渲染

```python
import glob, json
debate_files = sorted(glob.glob(f"{LOG}/debate_*.json"))
for df in debate_files:
    with open(df) as f:
        debate = json.load(f)
    rb.add_debate(
        topic=f"辩论: {debate['topic']}",
        rounds=[{
            "round": 1,
            "pro": "\n".join(a["argument"] for a in debate["pro_args"]),
            "con": "\n".join(a["argument"] for a in debate["con_args"]),
            "verdict": debate["judge_verdict"]["reasoning"],
            "pro_score": debate["judge_verdict"]["pro_score"],
            "con_score": debate["judge_verdict"]["con_score"],
            "action": debate["action"],
        }]
    )
```

### 3. 运行记录渲染

```python
run_records = sorted(glob.glob(f"{LOG}/run_record_*.json"))
for rp in run_records:
    with open(rp) as f:
        rec = json.load(f)
    rb.add_html(
        f'<div class="param-source">'
        f'<span class="param-source-label">📄 {os.path.basename(rp)}</span>'
        f'<div class="param-source-body">'
        f'<b>skill:</b> {rec.get("skill_name","N/A")} | '
        f'<b>params:</b> {rec.get("params_used","N/A")} | '
        f'<b>result:</b> {rec.get("result_summary","N/A")}'
        f'</div></div>'
    )
```

### 4. 统计表渲染

```python
rb.add_table(
    table_id="tbl_group_stats",
    csv_path=f"{RES_R1}/final_group_stats.csv",
    title_en="Group Statistics",
    columns=[
        ("type", "实验组"),
        ("count", "细胞数"),
        ("mean", "均值"),
        ("std", "标准差"),
        ("median", "中位数"),
    ],
    fmt={
        "mean": lambda v: f"{float(v):.4f}",
        "std": lambda v: f"{float(v):.4f}",
        "median": lambda v: f"{float(v):.4f}",
    },
    tip="运动干预后（Post）伪时间显著降低",
)
```

## 后报告验证（必须执行）

```python
with open(report_path, encoding='utf-8') as f:
    html = f.read()

checks = {
    "doctype": "<!DOCTYPE html>" in html[:200],
    "sidebar": "id=\"sidebar\"" in html,
    "hero": "id=\"hero\"" in html,
    "sections": html.count("report-section") >= 5,
    "figures_embedded": html.count("data:image/png;base64") >= 8,
    "tables": html.count("dt-table") >= 2,
    "debate_panels": html.count("debate-panel") >= 3,
    "lightbox_js": "openLightbox" in html,
    "datatables_js": "DataTable" in html,
    "conclusion_debate": "conclusion-debate" in html,
    "pipeline_flow": "pipeline-flow" in html,
    "param_source": "param-source" in html,
}
```

## 报告文件命名规范

| 版本 | 命名 | 包含 | 大小参考 |
|:----|:----|:----|:--------:|
| 完整版 | `scTour_Comprehensive_HTML_Report.html` | 全部 9 章节 + 所有图 + 辩论 + 日志 | 5-15 MB |
| 标准版 | `scTour_Complete_Report.html` | 主要 7 章节 + 图 + 辩论 | 3-8 MB |
| 精简版 | `scTour_Trajectory_Report.html` | 图 + 统计 + 结论 | 1-3 MB |

> **注意**：所有图片必须 base64 嵌入，禁止路径引用。小于 500KB 的报告意味着图片未嵌入。