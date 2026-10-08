# 多对比 DEG 整合：完整判据与实测记录

## 一、开工前：把 DEG 表的"形态"先摸清（过度假设会直接算错）

不同方法/工具导出的 DEG 表形态差别很大，**先看形态再写代码**：

| 形态 | 表现 | 影响 |
|---|---|---|
| **宽表**（一次对比一张表） | 一个文件 = 一个对比 | 直接并表 |
| **长表**（多对比堆在一张表） | 行数 = 基因数 × 对比数 × 亚群数；含 `contrast` / `celltype` 列 | **必须按 `contrast` + `celltype` 拆分后再交集**，否则把不同对比的同一基因混成一行 |
| `.xlsx` vs `.csv` | 文件名后缀不预告内容 | 用 `glob` 同时抓两种后缀；实探到"以为全是 csv、实际是 xlsx"就白跑一轮 |

实测（本数据集）：

- 新方法 = 5 个 `.xlsx`，文件名即对比：`merged_<A>_vs_<B>.xlsx`
- 老方法 = 长表 `.csv`，**173,950 行 / 27,015 唯一基因**，含 `contrast` + `celltype`
  → 说明可**按亚群拆分**，能与亚群层面口径对齐

**必做**：先跑 `scripts/deg_table_power_probe.py <dir>`，拿到每个文件的
`行数 / 唯一基因数 / 列名 / 各阈值下显著数 / |effect| 中位数`，再决定怎么并表。

---

## 二、锁定正负号语义（Step 1.5 的 1a）

`merged_Y_Pre_vs_O_Pre.xlsx` 这种名字**只说明比了哪两组，不说谁减谁**。
三种常用约定都可能出现：

- `A_vs_B` = A − B（差异分析惯例：A 相对 B 的 logFC）
- `A_vs_B` = B − A（部分管线按"case vs control"写，实际取对照减处理）
- 列名 `coef` 可能已经是 `log2FC`，也可能是别的尺度

**核实方式**（不要猜）：

1. 读该对比的分组计数，找一个**方向已知的 marker** 做正对照：
   例如衰老对比里，已知随衰老**上调**的基因（本类组织用 SASP / 炎症 / 衰老 marker）
   看它的 `coef` 是正还是负 → 反推符号约定
2. 或用**同一批数据的两套方法**做交叉：两法同向显著（Tier1）里若方向一致率高，说明约定相同

**后果量级**：锁错 → 全部"逆转"结论整体反过来。这是本类分析最昂贵的错误，值得多花十分钟。

---

## 三、随机重叠期望：完整算式与呈现方式

```
E[|A ∩ B|] = |A| × |B| / N            N = 实际检测基因数
Jaccard    = |A ∩ B| / |A ∪ B|
OR         = (|A∩B| × |非A∩非B|) / (|A∩非B| × |非A∩B|)     Fisher 精确检验给 p
```

**实测示例**（新方法 Aging 集 16,535、N ≈ 27,015，与某运动上调集 231）：

```
E = 16535 × 231 / 27015 ≈ 141.4      # 占 231 的 61%
```

呈现规则：**任何交集数字旁边必须有基线**。表格形如

| 集合对 | 交集数 | 随机期望 E | 倍数 | OR | Jaccard |
|---|---|---|---|---|---|

**工具引用诚实线**：
多集合交集显著性 `SuperExactTest`、阈值无关排序聚合 `RobustRankAggreg` 是 R 包、方法确实存在；
但本会话两次检索（含 "SuperExactTest multi-set intersection statistical significance gene lists"）
**未命中其原始方法学文献的 PMID** → 引用前核实原文，**不许凭记忆编 PMID**。

---

## 四、功效表：交集能不能做，先看这张表

实测（同一批数据，老方法 pseudobulk dreamlet，`|logFC|>0.25 & FDR<0.05` 的显著行数）：

| 对比 | Aging | Ex_Old | Ex_Young | Ex_DM | DM |
|---|---|---|---|---|---|
| 显著行数 | 29,542 | 1,246 | 22 | 4 | 1 |

判读：

- `DM`=1、`Ex_DM`=4 → 逆转该疾病这条线**在本方法上不存在**；给交集数（必然是 0）会误导读者
- `Ex_Young`=22 → "三组共同响应"撑不起来
- → 结论必须写成"该对比仅由细胞级方法支持"，而不是"没有重叠说明无关"

**阈值选 ~50 的依据**：低于此数时，任何两集合的交集期望都 < 1，且抽样波动主导，
Jaccard/OR 的置信区间宽到没有信息量。

---

## 五、阈值有效性诊断：中位数 vs 阈值

```python
med = df[effect_col].abs().median()
binding = med > threshold      # True → 阈值没在筛选
```

实测：
- 老方法 Aging：中位数 **0.3475** > 0.25 → 29,550 → 29,542（**只砍 8 行**）= 阈值不设防
- 新方法 Aging：0.20→0.25 砍掉 **11,111 行** = 阈值在强力筛选

**同一个 0.25 在两种方法上作用完全不同** —— 因为两法效应量分布不同。
所以：① 别跨方法搬"阈值砍掉多少"的经验；② 报阈值时必须同时报**该方法 |effect| 的中位数**，
否则读者无法判断这个阈值有没有起作用。

---

## 六、逆向推理：为什么"细胞级方法检出多"不等于"方法更好"

同一批数据：糖尿病对比老方法 **1 行**、新方法约 **269 个基因**（125↑/144↓，8 亚群合计）——
差 ~270 倍。两种解释都可能，**必须先诊断再结论**：

| 可能 | 诊断手段 |
|---|---|
| 老方法功效不足（供体少、随机效应吸收方差） | 看老方法的 `t` / `se` 分布、供体数、有效自由度 |
| 新方法 SE 被低估 → 假阳性膨胀 | 看 p 值分布（是否整体左移/呈异常尖峰）、`p:se` 关系、up:down 比（正常应接近，如 43:1 就是膨胀指纹） |
| 真实差异 | 用**独立数据集**或**文献真值集**做正对照（如 T2D 肌肉的已知调控特征集） |

**方向偏倚是膨胀的免费指纹**：某条件集 up:down ≈ 43:1 时，几乎不可能是生物学，
先假设统计问题。这条要在报告里明说，不要把它当成"该条件以激活为主"的发现。

---

## 七、脚本骨架

### 7.1 并表 + 亚群拆分（长表）

```python
# 长表：按 contrast + celltype 拆分，不要直接整表求交
for (ctr, ct), sub in df.groupby(['contrast', 'celltype']):
    sub[['gene', 'logFC', 'P.Value', 'adj.P.Val']].to_csv(f'out/{ctr}__{ct}.csv', index=False)
```

### 7.2 方向感知交集 + 期望校正

```python
def quad(A, B, N):
    """A/B: dict[gene] -> signed effect。返回四象限 + 期望基线"""
    common = set(A) & set(B)
    q = {'same_up': 0, 'rev_up': 0, 'rev_dn': 0, 'same_dn': 0}
    for g in common:
        a, b = A[g], B[g]
        if   a > 0 and b > 0: q['same_up'] += 1
        elif a > 0 and b < 0: q['rev_up']  += 1      # ← 逆转（上调侧）
        elif a < 0 and b > 0: q['rev_dn']  += 1      # ← 逆转（下调侧）
        else:                 q['same_dn'] += 1
    E = len(A) * len(B) / N
    return q, E, len(common)
```

### 7.3 排序法（阈值无关）

```python
# s 用带符号强度；Rg 负 = 反向
s_A = {g: np.sign(c[g]) * -np.log10(max(p[g], 1e-300)) for g in genes}
s_E = {g: np.sign(c2[g]) * -np.log10(max(p2[g], 1e-300)) for g in genes}
Rg  = {g: s_A[g] * s_E[g] for g in genes}          # < 0 → 逆转候选
rho = spearmanr([s_A[g] for g in genes], [s_E[g] for g in genes])   # 全局：负 = 整体反向
```

---

## 八、出图配方

### 2×2 象限散点（本类分析的招牌图）

```python
ax.axhline(0, lw=0.6, color='#999'); ax.axvline(0, lw=0.6, color='#999')
ax.scatter(eff_cond, eff_int, s=4, c=color_by_quadrant, alpha=.6, linewidths=0)
# 四象限在各角标基因数：
for (x, y, txt) in [(-.9, .95, f'shared down {n1}'), (.9, .95, f'REVERSED {n2}'), ...]:
    ax.text(x, y, txt, transform=ax.transAxes, ha='center', fontsize=7)
```

- 只标**逆转象限**的基因名（top 10–15，按 `|Rg|` 排）
- 轴 = 效应量（`coef` / `logFC`），不是 p 值 —— p 值在象限图里会把一切挤到角落
- 若两组量纲不同（如细胞级 coef vs pseudobulk logFC），**先 z 标准化再用象限图**，并在图注声明

### UpSet（≥4 集合）

`ComplexUpset`（R）/ `upsetplot`（Python）。集合顺序人工指定，别让字母序替你排
（读者会把集合顺序当语义）。交集的表格附件里必须带每对的期望 E 与 OR。

---

## 九、文献依据（本类"干预逆转"范式 + 方法学约束）

| 文献 | 关键方法 | 关键发现 | 用来支撑什么 |
|---|---|---|---|
| Melov 2007 PLoS One [PMID:17520024] | 抗阻训练前后肌肉转录组（老年 vs 年轻） | 训练使老年肌肉转录组朝年轻方向扭转 | **"干预逆转条件"的原始范式** |
| Ma 2024 J Aging Phys Act [PMID:38684216] | 微阵列 + 功能富集 + PPI + ROC | 45 个基因被抗阻训练逆转；PPI 定位 hub | 逆转集的下游路线模板（PPI/ROC 可照搬） |
| Yang & Li 2026 Genes [PMID:42510843] | 老年配对活检；配对 DEG + GO/KEGG/GSEA，三种运动模式对比 | 不同干预模式分子响应不同；配对设计控个体差异 | **"交集 → 富集"这套顺序的方法模板** |
| Voisin 2024 Aging Cell [PMID:37128843] | 甲基化组 + 转录组，运动者 vs 非运动者 | 长期运动者肌肉更"年轻"；部分年龄改变被干预抵消 | 逆转方向的外部预期 |
| Barberio 2021 Front Endocrinol [PMID:34690929] | 术后肌肉基因表达按疾病状态分层 | **疾病状态会改变肌肉对干预的转录组反应** | 支撑"逆转疾病"这条线存在生物学前提 |
| Scott 2016 Nat Commun [PMID:27353450] | 人骨骼肌 T2D 遗传调控图谱 | T2D 在肌肉有可重复的调控特征 | **疾病对比的参照真值集**（判新方法检出是真信号还是假阳性） |
| Crowell 2020 Nat Commun [PMID:33257685] | muscat：多条件多供体 pseudobulk 框架 | 原文写明 *"relying on thresholds alone is prone to bias"* | **直接支撑：不能拿阈值交集当结论** |
| Wu 2025 Innovation in Aging DOI:10.1093/geroni/igaf122.235 | snRNA-seq，老年 vs 年轻男性 | 亚群比例与代谢/钙信号通路改变 | 亚群层面的文献预期值 |
| Pino 2019 Physiol Genomics [PMID:31588872] | 疾病 + 耐力训练，肌肉磷脂组 + 线粒体呼吸 | 训练重塑疾病肌肉线粒体 | 干预+疾病线的机制落点 |

**引用纪律**：以上 PMID 均在本会话检索结果中出现过。**检索没命中的就不要写进去**
（如 `SuperExactTest` / `RobustRankAggreg`），或先核实原文再补。

---

## 十、交付口径（用户会核对的几件事）

1. **每一步都说明用的是哪套 DEG**（细胞级 or pseudobulk）、哪个阈值、哪一层（全局 or 亚群）
2. **交集数必须与随机期望并排**，否则不给
3. 检出数不够的对比，**不给数字、给原因**（"该对比在本方法上仅 N 个显著基因，不足支撑交集分析"）
4. 供体数、配对关系、多重检验策略写进方法段
5. 任何"逆转"结论要标明**方向锁定的依据**（用哪个 marker 做的正对照）