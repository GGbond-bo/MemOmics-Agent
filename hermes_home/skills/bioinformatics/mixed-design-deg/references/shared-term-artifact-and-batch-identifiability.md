# 共享项伪相关 与 批次项可识别性（配方 + 实测数字）

来源：2026-09-25 骨骼肌 MF pseudobulk dreamlet 审计（human / skeletal muscle / 24 供体 × 运动前后 = 48 样本，
Y 10 / O 7 / OD 7，全体女性；`~0+type+(1|individual)`，ddf=Kenward-Roger，亚群内 BH）。

---

## 一、共享项伪相关（shared-term artifact）

### 机理

对比是两个组均值的线性组合：`c'β = Σ cᵢ·μᵢ`。两组对比的估计协方差为

```
Cov(c₁'β̂, c₂'β̂) = c₁' Cov(β̂) c₂ ,   Cov(β̂) = (X'V⁻¹X)⁻¹ ,  V = σ²_b ZZ' + σ²_e I
```

只要 `c₁` 与 `c₂` 在**同一个组均值上取相反符号**，这一项就是**负的**。若两组均值都是正号，
则为正。**与生物学无关**，只由设计矩阵 + 样本量决定。

### 解析推导（无随机效应时）

平衡/半平衡设计下组均值独立 ⇒ `Cov(μᵢ, μⱼ) = 0 (i≠j)`，于是

```
Aging  = O_Pre − Y_Pre       →  Var = σ²(1/n_O + 1/n_Y)
Ex_Old = O_Post − O_Pre      →  Var = σ²(2/n_O)
共享 O_Pre（+1 / −1）        →  Cov = −σ²/n_O
corr = −(1/n_O) / √[(1/n_O + 1/n_Y)(2/n_O)]
```

n_O=7、n_Y=10 ⇒ corr = −0.542。加 `(1|individual)` 后同一供体的 O_Pre/O_Post 共享供体效应
⇒ `Cov(O_Pre,O_Post) > 0` ⇒ |corr| 变小（ICC 0.3 时 −0.454；ICC 0.6 时 −0.343）。

### 后果量化（选择效应）

在 Ex_Old 上按显著性选基因（|t| 大）等价于条件化在 `|Ex_Old|` 极端值上。二元正态下
`Y|X=x ~ N(ρx, 1−ρ²)`，故 x 越极端、Y 越倾向取**相反符号**。模拟 40 万基因（真实效应为 0，
只用上面的协方差矩阵生成噪声），取阈值使入选数 = 实测显著数：

| 供体 ICC | corr | 预期符号一致率 |
|---|---|---|
| 0.0 | −0.542 | 2.2% |
| 0.1 | −0.514 | 4.2% |
| 0.2 | −0.485 | 5.3% |
| 0.3 | −0.454 | 6.3% |
| 0.4 | −0.420 | 9.4% |
| 0.6 | −0.343 | 12.2% |

**实测 15.7%**（Ex_Old 1246 个 FDR<0.05 基因与 Aging 的 logFC 符号一致率）。
⇒ 处在纯伪影预期区间内（略高于 ICC=0.6 的上界，提示存在少量真实同向共享信号，
与「重叠 30.3% > 随机期望 17%」一致，但**远不足以支撑逆转结论**）。

### ⚠️ DiD 不豁免（本条曾判断错误，务必照抄）

直觉认为「DiD 与 Aging 无共享项」是**错的**：

```
Aging      = +O_Pre − Y_Pre
Ex_x_Aging = −O_Pre + Y_Pre + O_Post − Y_Post     ← 共享 O_Pre 与 Y_Pre，且都反号
corr(Aging, Ex_x_Aging) 实测 = −0.707 (ICC 0) / −0.592 (ICC 0.3)
```

⇒ 「用 DiD 就能干净回答"是否逆转衰老"」不成立。DiD 回答的是「运动效应是否随年龄不同」，
**不等于**「转录组向年轻靠拢」。

### ✅ 正确检验「向年轻靠拢」：距离分析

不依赖对比间相关：

1. 取 Young_Pre（或 Young 全部）样本构建质心（per celltype，pseudobulk logCPM）
2. 对每个 O 供体算 `d_pre = dist(O_Pre, Young centroid)`、`d_post = dist(O_Post, Young centroid)`
3. 配对检验 `d_post < d_pre`（Wilcoxon signed-rank / 配对 t）；同时报效应量 `d_av` 与 95% CI
4. 对照组内一致性：逐供体 `Δd = d_pre − d_post` 的符号与分布（防少数供体驱动）

### 复现

`scripts/shared_term_artifact_calc.py` —— 改 `GROUPS`（组名 → (n, 供体组)）与 `CONTRASTS`
（对比名 → (正组, 负组)）即可，输出 corr 与纯伪影预期符号一致率。

---

## 二、批次项是否该加 `(1|batch)`

### 三步实查（不要凭"测序批次"想象）

```python
cols = ["orig.ident","library","samplename","type","sex","age","annotation_L3"]
md = pd.read_csv(meta_csv, usecols=cols, dtype=str)
for c in cols: print(f"{c:14s} 唯一值 {md[c].nunique():5d}")

md.groupby('library')['samplename'].nunique().value_counts()   # 每个 batch level 含几个样本
md.groupby('samplename')['library'].nunique().value_counts()   # 每个样本含几个 batch level
pd.crosstab(md['library'], md['type'])                          # 混淆检查
```

### 实测输出（本例）

```
细胞数 508,661
orig.ident   唯一值     1   ← 全为 "SeuratProject"，无信息
library      唯一值    96   ← 唯一批次候选列
samplename   唯一值    48
type         唯一值     6
sex          唯一值     1   ← 全为 Female（无性别混杂，但泛化性受限）
age          唯一值    15

每个 library 含样本数分布      : {1: 96}   ← 完全嵌套
每个 samplename 含 library 数分布: {2: 48}
library 命名示例: O10C_1_1, O10C_1_2 (O_Pre), O10C_2_1, O10C_2_2 (O_Post)
                  → 命名模式 <donor>_<1=Pre|2=Post>_<rep>
每个 library 只涉及 1 个 type（96/96）→ 与分组零混淆
```

### 判据

| 情形 | 处理 |
|---|---|
| batch level **恰含 1 个样本**（完全嵌套于聚合单元） | ⛔ 加不了：pseudobulk 后每个 level 只剩 1 个观测 → 无自由度可估、不可识别 |
| batch 跨多样本 且 与 group **部分**混淆 | ✅ 可加 `(1\|batch)` |
| batch 与 group **完全**共线 | ⛔ 绝不能加（随机效应会吸走组效应）→ 只能声明局限 |
| 全样本同批 | 无需校正 |

本例结论：**不加**，模型保持 `~0+type+(1|individual)`。Methods 一句：
> 每个样本包含 2 个测序文库；pseudobulk 按样本（donor × timepoint）合并，文库层面技术变异包含在样本级残差中。

L1 辩论门控同判：正方（不加）有嵌套结构数据支持；反方只提质疑、拿不出批次效应或可估自由度证据。

---

## 三、DEG 表体检套餐（用户只给结果表时）

给 5 个对比表（173,950 行 = 10 亚群 × 12,268–26,879 基因）跑这段即可定位大部分问题：

| 检查 | 实测结果 | 结论 |
|---|---|---|
| 行数 / 亚群数 | 5 表均 173,950 行、10 亚群、每亚群基因数恒定 | 无静默丢亚群 ✓ |
| 亚群基因数范围 | 12,268–26,879（**2.2 倍差**） | BH 家族不等，跨亚群比显著数须先报基因数 |
| 名义 P<0.05 占比 | Aging 32.4 / Ex_Old 16.2 / Ex_Young 9.9 / Ex_DM 7.1 / **DM 5.71** | DM 实质全阴性；其余真信号/弱信号 |
| FDR<0.05 计数 | 29,550 / 1,246 / 22 / 4 / 1 | — |
| 阳性对照方向 | ANKRD1 Ex_Old +2.01 P=0.010；FOS Ex_Young +1.93 P=0.068；PPARGC1A 三对比 logFC≈0 | 方向大体正确 ⇒ 效应量小 + 家族大，非伪影 |
| 阴性对比方向性趋势 | IRS1 +0.71 P=0.089、TBC1D4 +0.44 P=0.080、PDK4 +1.20 P=0.081、CS −0.36 P=0.013 | 弱信号、功效不足 → 写「未检出」 |
| 已知基因是否被检验 | 19/20 对照基因在表内（≥min.cells=10 门槛） | 「0 个达标」≠「被过滤掉」 |
| 伪影候选 | 假基因 NPM1P29 +2.31；未注释 AC027097.2 / AC044893.1 / AC006254.1 | 进主结论前须 QC |
| 年龄匹配 | O 组 61–83（均 68.6）vs OD 组 68–78（均 72.4） | DM 对比含轻度年龄混杂，须写入 Limitations |

**元数据核查小技巧**：
- `sex` 唯一值 = 1 ⇒ 全同性别（无混杂，但限制泛化性）
- `age` 唯一值 < 供体数 ⇒ 年龄是分组/取整的，别当连续协变量直接入模
- `orig.ident` 全为 `"SeuratProject"` ⇒ 合并对象的默认值，无样本信息，别拿它当批次