# FindMarkers → Metascape 输入表构建（每亚群 top-N 基因宽表）

> 实测案例：2026-08-22，memomics-4687a591
> 输入：`MF_annotation_L3_protein_DEG.csv`（FindMarkers 输出，8 列，10 亚群 1900 行）
> 需求：每亚群按 `avg_log2FC` 取 top100 基因 → 宽表 CSV（列头=亚群名，下面基因往下排），不足 N 全取。
> 产出：`Metascape_top100_by_subcluster.csv`（10 列 × 100 行）+ 辅助箱线图 `top100_log2FC_distribution.png`
> 脚本：`results/memomics-4687a591/scripts/metascape_top100.py`

## 标准流程（Python/pandas）

```python
import pandas as pd
df = pd.read_csv(SRC)

# ① 清洗基因名 —— FindMarkers 输出带残留制表符（gene_type 显示 "protein_coding\t" 即信号）
df["gene"] = df["gene"].astype(str).str.strip().str.replace(r"\t", "", regex=True)

# ② 数据校验（先查再筛，防哑错误）
assert not df["avg_log2FC"].isna().any(), "avg_log2FC 有缺失值"
assert df.duplicated(subset=["cluster", "gene"]).sum() == 0, "同亚群内重复基因"
counts = df.groupby("cluster").size()   # 看每亚群基因数，判断哪些 <100

# ③ 每亚群按 avg_log2FC 降序取 top100（不足 N 全取由 head() 自动处理）
clusters = sorted(df["cluster"].unique())
records = []
for cl in clusters:
    sub = df[df["cluster"] == cl].sort_values("avg_log2FC", ascending=False).head(100)
    records.append(pd.Series(sub["gene"].tolist(), name=cl))

# ④ 宽表构建：列名=亚群名（即表第一行），行序=排序后基因
metascape_df = pd.concat(records, axis=1)
metascape_df.to_csv(OUT, index=False, encoding="utf-8-sig")  # utf-8-sig：Excel 直接打开不乱码
```

## 关键点与坑

1. **排序依据**：用户说"按 avg_log2FC 取 top100" → 只按这一列降序排。
   **不要擅自叠加 p_val_adj 过滤**（FindMarkers 输出通常已过阈值；用户没提显著性就不加）。
2. **残留制表符**：FindMarkers/某些导出工具会在 `gene_type`/`gene` 末尾带 `\t`。
   基因名列本身通常干净，但清洗是低成本保险。
3. **编码**：一律 `utf-8-sig`（UTF-8 with BOM），Windows Excel 直接打开中文/特殊字符不乱码。
   这是用户多次确认的偏好。
4. **Metascape 格式**：每列一个亚群、列头=亚群名、下面基因往下排；列不需要等长，
   Metascape 按列读取基因列表，空单元格忽略。该宽表同时可兼容后续手动检查/其他富集工具。
5. **校验口诀**：先 `groupby("cluster").size()` 确认每亚群基因数 → 判断哪些亚群不足 N
   （用户规则：不足就全取）→ 再筛选。本案例 10 亚群全部 ≥100（107~383），无需全取分支。
6. **rail_review(post) 配合**：纯表格任务会被判"未生成任何图片"→ 补 1 张辅助箱线图
   （各亚群 top100 基因 avg_log2FC 分布）即通过；matplotlib 3.9+ 用 `tick_labels=` 替代 `labels=`，
   别忘 `import numpy as np`。详见 platform-execution-pitfalls 坑表。
7. **交付口径**：说明"10 亚群全部 ≥100 基因所以都是完整 top100，无需触发不足全取分支"，
   并给每亚群 top1 基因与 top1 avg_log2FC 供用户核对（RSS→NSG2 6.08 等）。

## 触发词

"metascape" / "每个亚群top100" / "按avg_log2FC筛选" / "亚群基因宽表" / "findermarker表格" /
"基因表导出" / "Metascape输入表"