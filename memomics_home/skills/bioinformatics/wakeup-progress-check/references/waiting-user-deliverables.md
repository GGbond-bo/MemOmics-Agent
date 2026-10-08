# waiting_user 期间交付用户点名产物（2026-08-27 memomics-cd677556 唤醒 #4 实测）

## 场景

task_plan Current Phase = waiting_user，但注入上下文的「会话要求」里用户明确点名过可交付产物（如"把8大类的基因都给我，我看看"）。

## 规则

**推进 Phase 被禁 ≠ 无视点名产物。** waiting_user 只限制「自动执行分析/推进勾选」，不限制「用现有数据满足用户点名的产物交付」：
- 判定：该要求是「产物交付」（给基因表/给清单/给某个文件）→ 交付；是「分析推进/方向拍板」（做不做重聚类、Age 映射表）→ 只列挂起决策清单。
- 交付 = 聚合既有产物 → 落盘输出 → 对话展示完整内容 + 产出文件路径。
- 这不违反"无响应期间不自动执行任何分析"红线（没有跑新分析，只是聚合已有结果）。

## 具体案例：8 大注释类基因表补全（human 40 海马 ATAC）

用户点名"8大类的基因都给我"。已有文件：
- `task4/annotation_8classes_genes.csv` — 按 cluster 的 top-marker 汇总，**只含 6 类**（Astro/InN/ExN/Micro/VS/ODC），缺 OPC/ChP。
- `task4/annotation_8classes_by_marker.csv` — **cluster×class 宽表**：每行一个 cluster，列 = ExN_genes/InN_genes/Astro_genes/Micro_genes/OPC_genes/ODC_genes/VS_genes/ChP_genes（逗号分隔基因列表），8 类齐全。

聚合脚本模式（`scripts/extract_8classes_genes.py`）：

```python
import csv, collections
classes = ["ExN","InN","Astro","Micro","OPC","ODC","VS","ChP"]
class_genes = {c: collections.Counter() for c in classes}
with open(SRC, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        for c in classes:
            for g in (r.get(f"{c}_genes","") or "").split(","):
                g = g.strip()
                if g: class_genes[c][g] += 1
# 输出：每类按"基因出现在多少个 cluster 的该类列"排序取 top15
```

要点：
- 频次 `n_cluster` = 该基因被判为该类 marker 的覆盖亚群数，越高越核心。
- 输出文件名用 `_full` 后缀区分部分版；交付时对话里用 markdown 管道表格（**铁律 29**）直接给用户看，附 CSV 路径便于复用/复现。
- record_run 记到 `annotate_celltype_scRNA`（agent 创建限制时记到本 skill 亦可，注明技术归属）。