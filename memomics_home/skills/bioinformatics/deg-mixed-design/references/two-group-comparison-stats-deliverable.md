# 完成实验后的两组比较交付（小面板表达矩阵 → 固定表头 CSV）

> 实战来源：2026-10-18，`expr.csv`（long format: `sample,group,gene,expr`，6 基因 × {Aging,T2D} × n=6）
> → `out.csv` 固定 8 列表头 + 3–5 句方法说明。同一请求在历史会话跑过一次，本次**逐位复现**。
> 与本文档同一统计家族：独立比较（Hedges' `g`）/ 小 n / FDR 族 / 离散下限。区别只在于
> **这是「设计后、单次两组、小面板」的交付形态**，不涉及混合模型或 pseudobulk。

## 何时用本配方

用户给出**已经测完的数据**（表达矩阵 / 峰表 / 临床指标），要求「A 组 vs B 组比较」，并**指定了
输出格式与列名**。⚠️ 这类请求与 `deg-mixed-design` 主流程（pseudobulk + dream/muscat、配对建模）
不是同一件事：这里没有配对、没有模型，只有每基因一次两组检验 ⇒ 别把混合模型硬套上去。

## 交付契约（先照用户给的列名，⛔ 不要自己设计列）

本例固定表头（逐字）：
```
gene,mean_Aging,mean_T2D,pvalue,effect_size,qvalue,test_method,differential
```

| 规矩 | 说明 |
|---|---|
| 表头逐字对齐 | 顺序 / 下划线 / 大小写 / 列名全按用户给的字符串；写完 **`read_file` 回读一次核表头** |
| `test_method` 写真名 | 写 `Welch t-test (two-sided)`，⛔ 不写泛词 `t-test` / `t检验` |
| **小数位 ≥6（关键坑）** | 用户说「数值保留 4 位小数以上」时，**4 位会把小 p 值抹平**：`p=3.94e-4 → 0.0004`、`q=2.37e-3 → 0.0024`。⇒ **p / q 一律 6 位**，均值 6 位，效应量 4–6 位 |
| `differential` 判据必须可见 | 见下方「双旗」一节 |

## 口径（本例已确认，可直接复用）

| 项 | 取值 |
|---|---|
| 主检验 | **Welch t-test 双侧**（不假设方差齐性）。本例 GENE4 SD 1.29 vs 0.55、GENE6 1.50 vs 0.62 ⇒ 等方差假设不成立 |
| 敏感性 | **Mann-Whitney U 双侧**（结论方向一致即稳健性证据） |
| 效应量 | **Hedges' `g`** = `(mean_T2D − mean_Aging) / s_pooled × J`，`J = 1 − 3/(4(n1+n2) − 9)` |
| 符号约定 | ⚠️ **必须在回复里写明「正 = T2D 高」** —— 表里只有数字，读者会猜方向 |
| 多重校正 | **BH-FDR**，族 = 本次比较的基因集（本例 6 个基因；族口径见 `references/fdr-family-definition-audit.md`） |
| `differential` | **双旗**：`p < 0.05` **且** `abs(g) >= 0.8` |

### ⚠️ 双旗产物必然出现「yes 但 q>0.05」

本例 **GENE3**：`p=0.0271`、`g=1.400` → `differential=yes`，但 `q=0.0813`（未过 FDR）。
⇒ 判据**必须写进回复/图注**，否则 `yes` 会被读成「FDR 显著」。
（对照：GENE4 `g=0.933 p=0.125`、GENE6 `g=0.953 p=0.119` —— 效应已过 `|g|` 旗但 p 旗没过 ⇒ `no`。）

## 小 n 的两堵墙（写「局限性」时必须给，⛔ 别只说"样本少"）

### 墙 A：非参数检验的离散下限 = `2 / C(n1+n2, n1)`

本例 n=6 vs 6 ⇒ 最小可达双侧 p = **0.00216**；而 GENE1 的 Welch `p = 3.94e-4` **低于该下限**。
⇒ **在这组数据上 Mann-Whitney U 数学上到达不了 Welch 那个量级**，「MWU 不显著」**不能**当
「结果不稳」讲。⇒ 主口径留参数检验、非参数仅作方向验证；要拿非参数做主口径，**先算下限**。
（完整下限表、资格 vs 功效两堵墙的分工、所需 n 表 → `references/nonparametric-discrete-floor-and-null-defense.md`
＋ `scripts/check_nonparametric_floor.py`、`scripts/sample_size_feasibility.py`。）

### 墙 B：事后（achieved）功效 —— n=6/组，α=0.05，非中心 t

| 基因 | Cohen's d | 功效 |
|---|---|---|
| GENE1 | 3.01 | 0.997 |
| GENE3 | 1.52 | 0.659 |
| GENE6 | 1.03 | 0.366 |
| GENE4 | 1.01 | 0.354 |
| GENE5 | −0.23 | 0.065 |
| GENE2 | −0.17 | 0.058 |

达到 80% 功效所需**每组 n**：`|d|=0.8 → 26`、`1.0 → 17`、`1.4 → 10`、`2.8 → 4`。

⇒ 「大效应 + 不显著」（GENE4 `g=0.933 p=0.125`）只能写「**样本量不足以检出**」，
⛔ 禁写「无差异 / 没有效应」（与 §"报告铁律 0 显著 ≠ 无效" 同一条纪律）。

## 可复用片段（scipy，无需额外依赖）

```python
from scipy import stats
import numpy as np

t, p = stats.ttest_ind(y, x, equal_var=False)                       # 主检验：Welch
u, p_mw = stats.mannwhitneyu(y, x, alternative="two-sided", method="asymptotic")  # 敏感性
s_pooled = np.sqrt(((n1-1)*s1**2 + (n2-1)*s2**2) / (n1+n2-2))
g = (m2 - m1) / s_pooled * (1 - 3/(4*(n1+n2) - 9))                   # Hedges' g（含 J）

# 事后功效（双侧，非中心 t）
ncp  = abs(d) * np.sqrt(n1*n2/(n1+n2)); df_ = n1+n2-2
crit = stats.t.ppf(0.975, df_)
power = stats.nct.sf(crit, df_, ncp) + stats.nct.cdf(-crit, df_, ncp)
```

**BH 自实现即可**（基因数少时别为此引入 statsmodels）：按 p 升序排序，从最大 p 往回累积
`q_i = min(prev, p_i * m / rank_i)`，再 clip 到 [0,1]。
⚠️ 并列 p 取组内最大 rank（本 skill 的 BH tie 规则同此）。

## 重发同一请求时：**先取回上次的口径，再动手**

`search_knowledge(query="两组独立样本比较 Welch t检验 效应量 Hedges g BH FDR 多重检验")`
会命中一条 empirical 知识库条目（挂在 `experimental-design-statistics` 名下，
路径 `Homo_sapiens/synthetic_expression/aging/03_测序方法/RNA`），里面**逐字**记着
`test / effect / differential 判据`。⇒ **直接复用同一口径**，本次结果与历史记录逐位复现
（GENE1 `g=2.777749 p=0.000394 q=0.002366`）。
⛔ 不要重新选检验族 —— 换了就与用户既有交付、与已入库结论**不可比**。

## 「3–5 句方法说明」的骨架（用户常要求的收尾）

① 检验选择理由（独立性 / 方差齐性 / 样本量）→ ② 敏感性检验结论是否一致 → ③ 小 n 两堵墙
（离散下限 + 功效，**给所需 n 的具体数字**）→ ④ **设计信息缺失**：样本名 `Aging_1..6 / T2D_1..6`
没有 donor ID ⇒ **无法证明是否配对**，本次按独立样本处理；若实际是配对设计应改 paired t /
Wilcoxon signed-rank，功效更高、结论可能变 → ⑤ 数据层面（基因数少、单一比较、无批次/协变量、
无归一化单位说明）。

## 交付纪律

- **纯表格任务也必须出 1 张图**：`rail_review(post)` 在 `figure_count=0` 时判 failed。
  本例 = 双面板（均值 ± SEM + Hedges' `g`，标 `|g|=0.8` 参考线，柱顶标 `ns/*/**/***`）。
- 产物：用户指定路径的 `out.csv`（逐字表头）+ 会话内**完整版**（增补 SD/SE/MWU p/U/t 值）
  + 图 + 落盘脚本（`scripts/<名>.py`，含数据完整性断言：列名 / 分组集合 / 每组每基因 n）。
- **口径已确认 / 复现既有交付 ⇒ 不辩论**（活选项 <2，辩完不改变下一步动作），
  在回复里一句说明即可；`rail_review(pre/post)` 照走。
- 顺序：`skill_view` → `search_knowledge`（取口径）→ `rail_review(pre)` → 落盘脚本 → 跑 →
  `rail_review(post)`（`code_executed` 传完整脚本）→ `record_run`。