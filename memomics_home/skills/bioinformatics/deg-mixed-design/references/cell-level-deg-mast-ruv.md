# 细胞级 DEG：MAST / NEBULA / RUV 协变量 —— 合法用法与实现坑表

> 来源：2026-09-26/28 人骨骼肌运动项目（24 供体 / 48 样本 / 6 组 / Pre-Post 配对 / 508,661 细胞）
> 触发背景：用户问"为什么细胞级不可以，非要供体数"，并指出"26 年张潇的猴脑怎么就能用 MAST"
> —— 实证结论：**当时"细胞级不能当主分析"的绝对化表述是错的**，本文件是修正后的口径。

---

## 一、真正的红线（修正版）

**唯一红线：样本/供体层变异必须出现在模型里。用哪种机制是自由选择，不是对错关系。**

| 合法做法 | 检验单位 | 代表 |
|---|---|---|
| 样本级 pseudobulk | 样本 | dreamlet / muscat / DESeq2 |
| 混合模型 `(1\|donor)` | 细胞（带随机效应） | MAST `method="glmer"`、NEBULA |
| **RUV/SVA 因子作固定协变量** | 细胞 | 猴脑 NHPABC（Cell 2026） |
| pseudobulk 残差/PC 作协变量 | 细胞 | 同上篇引用 method 30,32 |

⛔ **禁止的是"朴素细胞级检验"**：把细胞当独立观测、模型里无任何样本层结构（Wilcoxon / FindMarkers / 无校正 MAST）。Squair 2021 (PMID 34584091) 批评的是这个设定，**不是 MAST 本身**。

⚠️ 教训：不要把"某篇 benchmark 批评的方法设定"简化成"某个工具不能用"。MAST 是细胞级 hurdle 框架的原始出处（Finak 2015, PMID 26653891），大量已发表工作（含 Cell）在用。

---

## 二、已发表范式：猴脑图谱（Cell 2026, PMID 42612631）

Zhang X et al., *Multimodal brain cell atlas across the adult macaque lifespan*, Cell 2026, DOI `10.1016/j.cell.2026.07.045`
官方代码 `github.com/3DC-STAR-Anthony/NHPABC` → `snRNA/04.Identification_of_differentially_expressed_genes(DEGs)/RUV_MAST_pDEG_MBA.R`、`RUV-seq_sDEGs.R`
规模：2,955,873 核 / 23 只食蟹猴 / 8 脑区

```
① 按 Sample 聚合 pseudobulk（mat %*% make.tform(Sample)）—— 只用于估 RUV 因子，不用于检验
② edgeR: calcNormFactors(TMM) → estimateGLMCommonDisp → estimateGLMTagwiseDisp → glmFit
③ residuals(fit, type="deviance") → RUVr(k=10) → 取前 5 个因子 W_1..W_5
④ 因子并回细胞级 metadata
⑤ 细胞级 MAST::zlm(~ Age + subtype + W_1+...+W_5)   ← bayesglm，无随机效应项
⑥ p.adjust(p,'fdr')，判据 Q<0.05 且 |log2FC|>0.25
```

- **它确实没用 `(1|donor)`** —— 用 RUV 因子作固定协变量吸收样本层变异。目的一致，机制不同。
- 它的**组成分析**用了混合模型：`n ~ age + modality + (1|sample) + offset(log(total cell))` Poisson GLMM。
  → 该篇逻辑是"表达用细胞级+RUV、组成用样本级随机效应"，**按问题选机制**。
- 基因过滤 `pctcut=0.1`（只在 >10% 细胞中表达的基因入检）+ 个体门槛（该亚型 ≥10 细胞；阶段比较 ≥10 个体）。

### ⚠️ 阈值不可跨层次移植（我犯过的错）

该篇判据 `|log2FC| > 0.25` 设在**细胞级 coef** 上（细胞级 n 大 → 过 FDR 的 coef 可以很小）。
实测搬到 pseudobulk 表上**几乎恒真**（过 FDR 的基因 logFC 本就 >0.25）：

| 对比 | Q<0.05 | 且 \|logFC\|>1.0 | 且 \|logFC\|>0.25 |
|---|---:|---:|---:|
| Aging | 29,550 | 12,265 | **29,542** |
| Ex_Old | 1,246 | 799 | **1,246** |
| Ex_Young | 22 | 12 | **22** |

→ "按 0.25 重跑能解决基因太少"的预测**作废**。阈值必须与检验层次匹配才会改变结果。

---

## 三、MAST + 随机效应：实现坑表（全部实跑踩出）

环境：R 4.5.3 内核 + MAST 1.32.0（跨库借用 R-4.4.2 用户库成功）

| # | 坑 | 症状 | 修法 |
|---|---|---|---|
| 1 | **`cData` 必须含随机效应变量** | 沿用原文 `model.matrix()` 输出当 cData → 报 "sca must inherit from data.frame"，**伪装得极难定位** | 传**原始变量**（含 `individual`），不传 model.matrix 结果 |
| 2 | **glmer 下 `summary()` 不可用** | 取不到 p 值 | `coef(fit,'C')` + `vcov(fit,'C')` **手算 Wald** |
| 3 | **`vcov` 维度序** | 是 (系数, 系数, 基因)，非 (基因, 系数, 系数) | 写自动识别维度序的稳健版 |
| 4 | **`MAST::CoefficientHypothesis` 未导出** | `MAST::` 前缀调用报错 | 改用 `coef()`/`vcov()` 裸泛型（**S4 泛型不能用 `MAST::` 前缀**） |
| 5 | **D 组件 NA** | glmer 在二值响应遇完全分离（某基因在某组近全 0）→ SE 为 NA | **非 bug**，剔除+留痕，别静默输出 NA 列 |
| 6 | **`zlm` 随机效应语法** | — | `method` 支持 `"glm"`/`"glmer"`/`"bayesglm"`（官方 `zlm.Rd` 原文确认） |
| 7 | **`RUVr` 位置参数** | 误判用户代码写错 | 官方签名 `RUVr(x, cIdx, k, residuals, center, round, ...)` —— `RUVr(counts, rownames(counts), k=n, res1)` **正确**（cIdx=全基因是 vignette 惯例） |

实测性能（24 供体 / 3000 基因 / Pure Type IIA）：glmer+(1|individual) **0.13 s/基因 → 约 6.6 min**；RE 与无 RE 的 coef 相关 **0.964**。

### RUV 阶段与随机效应必须分工

- **配对比较（Pre/Post）**：RUV 阶段的 design 也要加 `individual` → `~ stim + individual`，让残差不再含供体效应；否则 RUVr 会把供体效应当 unwanted variation 吸收，**与模型里的 `(1|individual)` 争抢同一份方差** → 过度校正/估计不稳。
  分工原则：**RUV 管技术变异，随机效应管供体**。
- **组间独立比较（Aging/DM）**：每供体只在 1 组 → `individual` **完全嵌套在 `stim` 内 → design 奇异（秩亏）** → 必须自动检测秩亏并回退 `~stim`，且日志留痕。

---

## 四、"为什么不能只用细胞数当 n"的定量论证（用户问过，值得复用）

同一个人的细胞**不是独立观测**。实测（Pure Type IIA，标称 171,320 细胞）：

- **ICC = 0.418** → 设计效应 2984 → **有效 n = 171,320 ÷ 2984 ≈ 57**（≈ 还是那 24 个人）
- 零假设模拟（随机把 24 供体分两组，本无差异）：

| 每供体抽细胞数 | 细胞级 p<0.05 | 供体级 p<0.05 |
|---|---:|---:|
| 5 | 25.0% | 6.0% |
| 20 | 53.5% | 6.5% |
| 100 | 73.0% | 5.0% |
| 500 | 92.0% | 9.0% |
| 1000 | **93.5%** | 3.5% |

→ **细胞越多，细胞级错得越狠**（正确值 5%）。细胞级 n 不是"更准"，是把噪声当信息。

方差分解（正确 SE/σ vs 细胞级假设）：
```
Var(组均值) = σ² × [ ICC/n_g  +  (1−ICC)/(n_g × m) ]
                     ↑ 只由供体数决定      ↑ 随细胞数变小，趋于 0
m=7138：ICC/n_g = 0.03483，第二项仅 0.0000068 → 99.98% 方差来自供体之间
细胞数 5→7138（1427 倍），正确 SE 只降 11.5%；细胞级假设下 SE 降 97.4%（低估 54.6 倍）
```
→ **借力方式是在建模里用供体随机效应 / RUV，而不是把细胞当独立样本计数。** NEBULA 也突破不了"供体数决定精度上限"这条线。

副产品（可写进结果的生物学）：ICC 大小本身是信号 —— scoreI_AUC **0.418**、scoreSarcomeric 0.374、scoreOxPhos 0.272、scoreIIa 0.154、scoreIIx 0.093、scoreInflammatory 0.028。
肌纤维类型程序 ICC 最高（构成是全身固有属性）、炎症类最低（细胞间更随机）。

---

## 五、结果取舍口径（多方一致时才升格）

- 两种方法**同向** → 可写稳健结论（本项目 `DM` 对比在 pseudobulk 与细胞级 MAST 下**都是 0** → "基线无差异表达信号"可信）。
- DiD 类对比在细胞级下 C=71~77 个显著，**判"未确认"**：唯一能定真假的是**供体内条件标签置换 ≥100 次**看是否超出零分布 —— 不做这一步不升级为结论。
- 组合方案（本项目最终建议）：**双主分析** —— pseudobulk LMM（Aging 检出 29,550 基因，自证流程无误）+ 细胞级 RUV-MAST（对小幅协调变化更敏感）；DiD 与跨对比结论单独声明为探索性。