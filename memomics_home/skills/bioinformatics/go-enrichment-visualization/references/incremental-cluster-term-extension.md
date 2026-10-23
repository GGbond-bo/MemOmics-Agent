# 增量补亚群 / 补词条（vN → vN+1）配方

来源：2026-10-13 会话 memomics-440038cf，v14 → v15（48×15 → 53×17）。
用户原话：*"从 `D:\肌肉锻炼\file\HAD_MF_BO_Selected_Paths_v2.xlsx` 这个表格里，补充两个亚群，RSS 和 Specialized MF，1.把 RSS 改名成为 SORBS+, Specialized MF 改名成 RUNX1+ 2.增加这两个亚群的词条。词条如下：… 完成 v15"*

---

## 0. 先读源表定位（不要猜插入位置）

```python
import pandas as pd
df = pd.read_excel(r"D:\肌肉锻炼\file\HAD_MF_BO_Selected_Paths_v2.xlsx", sheet_name=0)
seen = []
for c in df['Cluster']:
    if pd.notna(c) and c not in seen:
        seen.append(c)
for i, c in enumerate(seen, 1):
    print(f"{i}. {c}  ({(df['Cluster']==c).sum()} 条)")
```

本次输出（源表 82 行 / 18 个 cluster 位次）：

```
 1. Pure Type I (5)      6. OTUD1+(I) (5)     11. Specialized MF (5)
 2. Pure Type IIA (6)    7. OTUD1+(II) (5)    12. NMJ (4)
 3. Pure Type IIX (6)    8. RP_high(I) (4)    13~18. cluster1..6
 4. LRP1B+(I) (3)        9. RP_high(II) (4)
 5. Cluster (4)         10. RSS (5)
```

图上既有列序（来自 `MF_SMF_GO_select.xlsx`）：
`Pure Type IIA | IIX | I | LRP1B+(I) | OTUD1+(I) | OTUD1+(II) | RP_high(I) | RP_high(II) | NMJ | cluster1..6`

⇒ 源表里 RSS / Specialized MF 正好夹在 `RP_high(II)` 与 `NMJ` 之间（第 10、11 位），两表在此段完全一致 ⇒ **新列插在 `RP_high(II)` 之后、`NMJ` 之前**。
（两表在 Pure Type I/IIA/IIX 三者内部顺序不同，那部分**保持图上原有顺序**，不要按源表重排——用户已定稿。）

## 1. 矩阵增量构建（只做增量）

```python
import pathlib, pandas as pd
base = pathlib.Path(r"<安装目录>")
m = pd.read_csv(base/"data/MF_SMF_go_matrix.csv", index_col=0)   # 48 x 15

# (a) 插两列
cols = list(m.columns); ins = cols.index("RP_high(II)") + 1
m2 = m.reindex(columns=cols[:ins] + ["SORBS+", "RUNX1+"] + cols[ins:], fill_value=0)

# (b) 新增 5 个独立词条行，插在 RP_high 段末（ATP biosynthetic process 之后）
new_rows = {
    "cell-cell adhesion": {"SORBS+": 3.8},
    "developmental growth": {"SORBS+": 3.2},
    "regulation of small GTPase mediated signal transduction": {"SORBS+": 2.3},
    "regulation of cell projection organization": {"RUNX1+": 4.8},
    "regulation of anatomical structure morphogenesis": {"RUNX1+": 3.8},
}
newdf = pd.DataFrame(0.0, index=list(new_rows), columns=m2.columns)
for k, v in new_rows.items():
    for c, val in v.items(): newdf.loc[k, c] = val
pos = list(m2.index).index("ATP biosynthetic process") + 1
m3 = pd.concat([m2.iloc[:pos], newdf, m2.iloc[pos:]])

# (c) 共享词条合并：只补新列的值，不新增行
m3.loc["muscle structure development", "RUNX1+"] = 4.4
m3.loc["supramolecular fiber organization", "RUNX1+"] = 3.0

m3.to_csv(base/"data/MF_SMF_go_matrix_v15.csv", float_format="%g")
```

注意：
- `read.csv(..., check.names = FALSE)` 读回时**列名保持原样**（含 `+`、`(`、`)`），R 端必须加 `check.names=FALSE`，否则 `Pure Type IIA` 会被改成 `Pure.Type.IIA`。
- 源表 q 值为负（`-3.8`），`-log10(q)` = 取绝对值 ⇒ 3.8；本次新增值全部 <10，**不需要再截断**（矩阵既有值已在 0-10 内）。
- 落盘后**打印前后 shape + 列序 + 新列非零值**，作为核对证据（见脚本的 `print` 段）。

## 2. 基因表增量

```python
g = pd.read_csv(base/"data/MF_SMF_go_genes.csv", index_col=0)     # 48 行，列名 genes
g2 = g.reindex(index=list(g.index) + list(new_genes.keys()))
for k, v in new_genes.items(): g2.loc[k] = v
g2.to_csv(base/"data/MF_SMF_go_genes_v15.csv")
```

新词条基因（按「单亚群 2-3 / 共享 4」规则从用户给的基因池挑，优先选亚群标志基因）：

| 词条 | 挑出 | 理由 |
|---|---|---|
| cell-cell adhesion (SORBS+) | EFNA5, PCDH9, THBS4 | 粘附分子 + 细胞突起接触 |
| developmental growth (SORBS+) | SORBS2, BMPR1B, SLIT2 | SORBS2 = 该亚群命名基因 |
| regulation of small GTPase mediated signal transduction (SORBS+) | DOCK3, ARHGAP26, DOCK9 | GEF/GAP 代表 |
| regulation of cell projection organization (RUNX1+) | MYO10, MDM2, LIMA1, SYNE1 | 膜突起重塑 |
| regulation of anatomical structure morphogenesis (RUNX1+) | RUNX1, SASH1, MACF1, TGFB2 | RUNX1 = 该亚群命名基因 |

## 3. 出图（同一 render 函数出双版）

```r
render <- function(mat, tag, Wi, Hi){          # 与 v14 逐字同源：配色/字号/45°/padding/legend 全不动
  draw <- function(){
    p  <- pheatmap(mat, color=cols, cluster_rows=FALSE, cluster_cols=FALSE,
      display_numbers=FALSE, fontsize_row=8, fontsize_col=9, angle_col=45,
      border_color=NA, legend=FALSE, main="", silent=TRUE)
    gt <- gtable_add_padding(p$gtable, unit(c(1.0, 4.0, 1.8, 5.0), "cm"))
    grid.newpage(); grid.draw(gt); make_legend()
  }
  png(sprintf("figures/GO_heatmap_MF_SMF_v15_%s.png", tag), width=Wi, height=Hi, units="in", res=300); draw(); dev.off()
  pdf(sprintf("figures/GO_heatmap_MF_SMF_v15_%s.pdf", tag), width=Wi, height=Hi); draw(); dev.off()
  svg(sprintf("figures/GO_heatmap_MF_SMF_v15_%s.svg", tag), width=Wi, height=Hi); draw(); dev.off()
}
render(m,  "words_only",  9.5, 11.0)   # 延续 v14 用户满意尺寸
m2 <- m; rownames(m2) <- paste0(rownames(m), "  (", g[rownames(m), "genes"], ")")
render(m2, "with_genes", 11.5, 11.0)   # 行名更长 ⇒ 画布加宽
```

- 行数 48→53、列数 15→17 ⇒ 画布比 v14（9.2×10.4）略放大即可，**不要重做成 v13 那种 10.23×11.5**。
- 单独出两版（纯词条 + 末尾括号基因）的成本很低（同一个 render），比猜用户要哪版划算。

## 4. 交付必带的一句核对

用户给的条目数 ≠ 源表条目数时，交付时列出未纳入项及其 -log10(q)：

> HAD 表里这两个亚群实际各有 5 条词条，你消息里给的是 RSS 3 条 + Specialized MF 4 条，表里还有 3 条没纳入 —— `sensory system development`(-1.9)、`neuron projection development`(-1.8)（属 RSS）、`modulation of chemical synaptic transmission`(-2.0)（属 Specialized MF）。要不要补进去？

## 5. 门禁与自进化

- 本轮每次 `terminal` 后系统强制 `skill_evolution(action="record_run")` 才能继续下一个 terminal；矩阵构建脚本与出图脚本各记一次。
- `rail_review(phase="post")` 的 `location` 会**自动推断成集群 node4**（本机有常驻集群会话时）—— 该审查对本机 R 图任务只是形审，包检查按 location 判定，inferred 的问题只报警告不拦截。