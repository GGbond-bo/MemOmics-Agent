# 跨物种细胞类型构成比例 concordance 分析 — 复现配方（2026-08-27/29 人猴海马实证）

## 输入
- `human_meta.csv` / `monkey_meta.csv`：每细胞一行，含 `individual`（人=hc77/hc78...，猴=M1_Hip_1→M1）、`age_group`（已统一为 Young/Middle/Old/Exceptionally old）、`celltype`（8 大类）
- 已有脚本：`scripts/celltype_agegroup_proportion.R`、`scripts/celltype_stack_boxplot_v2.py`、`scripts/concordance_astro_opc.py`

## 个体水平比例表（统计单位 = 个体，防伪重复）

```python
import pandas as pd
h = pd.read_csv("human_meta.csv"); m = pd.read_csv("monkey_meta.csv")
# 猴 individual 从 Sample 库名提取（M1_Hip_1 → M1；_1/_2/_3/_4 是文库不是个体）
m["individual"] = m["Sample"].str.extract(r"^(M\d+|O\d+|V\d+|Y\d+)")
# 人 individual 已是 hc 号
# 每 individual × celltype 计数 → 每行一个个体
cnt = h.groupby(["individual","age_group","celltype"]).size().unstack(fill_value=0)
pct = cnt.div(cnt.sum(axis=1), axis=0) * 100
pct.to_csv("celltype_pct_individual.csv")
# 同样处理猴 → 两表合并（加 species 列）
```

## 统计（Spearman + KW + Bootstrap CI）

```python
from scipy.stats import spearmanr, kruskal
import numpy as np
STAGES = ["Young","Middle","Old","Exceptionally old"]
def trend(df, ct):
    """df 每行一个个体；返回 ρ/p/CI。年龄取序数 1-4。"""
    x = df["age_group"].map({s:i+1 for i,s in enumerate(STAGES)})
    y = df[ct].astype(float)
    rho, p = spearmanr(x, y)
    # Bootstrap 5000 次 95% 百分位 CI
    rng = np.random.default_rng(0); boots = []
    for _ in range(5000):
        idx = rng.integers(0, len(y), len(y))
        boots.append(spearmanr(x.iloc[idx], y.iloc[idx]).statistic)
    ci = np.percentile(boots, [2.5, 97.5])
    kw = kruskal(*[y[df["age_group"]==s] for s in STAGES]).pvalue
    return rho, p, ci, kw
# 每个 celltype 两个物种各算一遍（Astro/OPC/InN 实测值见结论表）
```

## 图

1. **堆叠柱状**：x=species×stage，y=celltype 构成%，统一配色。
2. **箱线图 6 面板**：每个共有 celltype 一个面板；x=stage，y=个体 %；
   `sns.boxplot` + `sns.stripplot(jitter=True)`（每个个体一个点）；
   右上角两行文本：`hum: ρ={:.2f} {stars}` / `mon: ρ={:.2f} {stars}`。
   **显著性文本放面板内侧顶部（y 取面板内高分位，两行），别放轴底部**（压 x 刻度）。
3. **单细胞类型专图（concordance）**：两物种均值 ± SEM 线（x=stage）+ 个体散点 +
   面板右上 `ρ/95%CI/p` 标注。InN→Astro→OPC 每细胞类型一图。

## 解读规则（辩论裁决 + 审稿人防线）
| 情形 | 写法 |
|---|---|
| 双侧同向显著（Astro/OPC） | "declined concordantly in both species" — 最强证据 |
| 双不显著 + CI 跨 0（InN） | "no detectable age-associated change in either species; directions concordant but CIs span zero" — 禁止说"证明稳定" |
| 物种分歧（ODC 反例） | 单列进 Discussion："species-divergent pattern underscores cell-type-specific validation remains necessary" |
| 部分支撑（Micro 人显著猴 ns） | "partial support" |
| 人男+猴全雌 | 性别仅人侧协变量，不能跨物种比 |

## 已知坑
- 猴 n=20 vs 21：必须按 individual 列去重（曾把 63 文库当个体数出错）；M4 仅 61 cells 做敏感性分析。
- 年龄列名/值两侧不一致 → 先统一 stage 再合并。
- bootstrap 用随机种子固定（审稿可复现）。
- scipy 由 check_env 安装到项目 venv（rail_review 检查系统 python 可能误报，以 execute_python 实跑为准）。