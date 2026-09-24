---
name: doublet-detection-validation
description: "双细胞检测结果的**可信度验证与剔除决策**。触发：检测一下双细胞 / 双细胞比例高不高 / 要不要剔除 / doublet 比例 / DoubletFinder、scrublet、scDblFinder 的结果怎么解读 / 两个方法结论不一致。核心立场：双细胞检出率是需要被验证的量，不是能直接读出来的量 —— 弱信号数据上算法标签可错到 F1≈0.3，据标签直接剔除等于删掉约 2/3 真细胞。"
when_to_use: "拿到单细胞数据被要求『检测双细胞 / 判断双细胞比例 / 决定是否剔除』时；或已有 DoubletFinder/scrublet/scDblFinder 输出、需要判断该相信哪些标签时；或两法结论差异很大（Kappa 低）不知如何取舍时。**先读本 skill 再写检测代码**——本 skill 管『判定与决策』，scrna-qc 管『过滤参数与流程』。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [doublet, scrna, qc, benchmark, decision]
    difficulty: intermediate
    language: R+Python
    category: bioinformatics
prerequisites:
  r_packages: ["Seurat", "DoubletFinder", "Matrix"]
  python_packages: ["scrublet", "scanpy", "anndata", "scipy", "numpy", "pandas", "scikit-learn", "matplotlib"]
---

# 双细胞检测验证与剔除决策协议

> 适用范围：任何"检测一下双细胞 / 比例高不高 / 要不要剔除"的请求。
> **本文档管判定**（该不该信这些标签、该不该剔、剔多少）；具体 QC 过滤参数与流程见 `scrna-qc`。

## 0. 先看判据表

| 情形 | 结论 |
|------|------|
| in silico benchmark 的 **F1 ≤ ~0.35** | **不应硬剔**：全保留 + `doublet_flag` + 下游敏感性分析 |
| benchmark **F1 ≥ ~0.6 且 FPR ≤ 5%** | 可按该档剔除，并在报告中给出 precision/recall |
| **未做 benchmark** | **没有资格**说"比例 = 算法标签数"，只能并列多口径 + 明确标注"未验证" |

三条配套铁律：

1. 报"双细胞比例"**必须同时给出口径**（哪档阈值 / 几个细胞 / 分母是什么）。单点估计禁止。
2. 剔除任何细胞前，必须已有**四步证据链**（§2）。
3. **不允许把 flag 率当真实比例报**（例：flag 7.50% 而 benchmark precision 0.31 ⇒ 检测到的真 doublet 下界仅 ≈2.3%）。

---

## 1. 口径必须写清（最容易出错的地方）

同一数据集能算出横跨一个数量级的"双细胞比例"，而且全都"正确"：

| 口径 | 含义 | 陷阱 |
|------|------|------|
| 算法 flag 率 | 某阈值判为 doublet 的细胞占比 | **不是真实比例**，含大量假阳性 |
| 双方法交集（core） | 两法都判为 doublet | 若其中一方来自假阳性档，交集同样不安全 |
| **真实比例下界** | `precision × flag 率` | 最可信的"真 doublet 至少有这么多" |
| 传统经验率 | 0.8%/1000（新化学）或 7.5%/1000（旧文献） | 是**先验**，不是本数据测出来的 |

报告表格必须含四列：**口径名 / 细胞数 / 占比 / 该口径的性质（推荐 · 仅敏感性 · 已废弃）**。
分母要审计——"4.55% core"若不写清来自哪两组交叉，等于没交代。

---

## 2. 四步证据链（缺任一步 → 不给剔除建议）

### 步骤 1 — 双方法交叉比对

两个**输入同一份 counts**、算法原理相互独立的方法：

- R：`DoubletFinder`（PCA + KNN + pANN）
- Python：`scrublet`（模拟双细胞 + 分类器）

输出：混淆矩阵、**Jaccard、Cohen's Kappa**、交集 / 差集 / 并集。

> 🔑 **关键预期：kappa 0.035–0.165 是常态**（示例数据实测）。低一致性本身说明"信号弱、单法不可信"，
> 而**不是**"需要挑一个更对的方法"。**不要把低 kappa 当作选方法的依据，它是"必须做 benchmark"的信号。**

两档敏感性都要跑（用来暴露假阳性爆炸）：

| 档 | DoubletFinder `nExp` | scrublet `expected_doublet_rate` |
|----|---------------------|----------------------------------|
| 保守 | `n_cells/1000 × 0.8` | `0.008` |
| 传统 | `n_cells/1000 × 7.5` | `0.075` |

🔴 **假阳性爆炸的特征信号**：自动阈值**低于该档分数的中位数/p95** → 判出的比例远超预期。
症状是"score 分布整体被压低、无双峰分离"。
⇒ 该档**只能作假阳性诊断，不得作剔除口径**。
（实测：`rate=0.008` 档阈值 0.0142 而 obs median 0.0095 → 判 27.3% 为 doublet，而真细胞误判 32.8%。）

### 步骤 2 — in silico benchmark（决定性的那一步）

用**本数据真实 counts** 造已知真值：

```python
# 合成 doublet = 随机两个真实细胞 counts 相加（异源配对）
pairs = rng.integers(0, n_obs, size=(INJ, 2))
pairs = pairs[pairs[:, 0] != pairs[:, 1]]
X_syn = X[pairs[:, 0], :] + X[pairs[:, 1], :]
X_mix = sp.vstack([X, X_syn]).tocsr()
is_syn = np.r_[np.zeros(n_obs, bool), np.ones(X_syn.shape[0], bool)]   # ← 真值标签
```

- 注入量取"预期档对应的数量"（如 `INJ = n_cells/1000 × 7.5`），让真值率贴近真实场景
- 对**同一个混合集**重算两法分数，逐档输出
  `recall_synthetic` / `false_positive_rate_on_real` / `precision` / `F1`
- **多 seed 重跑 ≥5–10 次**给均值 ± 95% CI，用 CI 是否重叠判断"哪一档稳健最优"
- 同时给固定阈值（0.10 / 0.15 / 0.25）作敏感性参考

### 步骤 3 — 特异性假阳性核查（区分"真 doublet"与"生物学现象"）

| 检查项 | 真 doublet 的预期 | 生物学假阳性的预期 |
|--------|------------------|-------------------|
| **nCount 中位数倍数** | **≈1.8–2.0×**（两细胞 RNA 相加） | ≈1.0×（单细胞，只是表达强） |
| 跨谱系共表达率 | **显著高于全库基线** | 仅本谱系标记高 |
| 非本谱系标记（间质/内皮/免疫） | **多谱系同时升高** | 不变 |
| ambient 分层（按 nCount 四分位） | 各深度层稳定升高，**高深度层仍显著** | 仅低 nCount 层升高（可被稀释） |

⚠️ **组织特异性陷阱：多核组织**（骨骼肌肌纤维、心肌是合胞体）——hybrid fiber 会同时高表达
`MYH7` + `MYH2`，**但通常不会同时高表达 `COL1A1` / `PECAM1` 这类非肌源谱系标记**。
**判据：同谱系双高可能是生物学 hybrid，跨谱系双高才指向双细胞。**

### 步骤 4 — 下游剔除敏感性（决定"剔多少才安全"）

对每个候选口径（0 / 最小交集 / 次优档 / 最优档 / 上限档）重算下游比例：

- N 组 × M 类 × K 亚群的**比例最大绝对偏移（百分点）**
- 受影响样本数、单样本最大剔除数、驱动样本命名
- 判据：偏移 ≤ ~2 百分点 ⇒ 剔除不改变全局结论，决策风险低

---

## 3. 决策输出模板

```
双细胞比例：不高 —— 真实约 X–Y%（检测真阳性下界 = precision × flag率）
            ⚠️ 同时列出各口径表（含已废弃档及其废弃原因）
要不要剔除：建议不硬剔（benchmark F1 ≤ 0.35，剔了会删掉约 2/3 真细胞）
            主分析保留全部 + doublet_flag（给出 flag 列清单）
            若必须去污染 → 剔 <最优档名>（N 细胞 = P%），注明其 precision/recall
残留不确定性：① 缺 10X 化学版本/装载浓度 → 先验率无法校准
              ② 子集化/富集流程不明 → 本数据比例不可外推
              ③ <未做的直接对比> 尚未完成
```

🔴 **诚实性要求**：benchmark 的比较对象若与决策要求的比较对象不一致（例：测的是"方法 A vs 方法 B"，
而升格条件是"档 X vs 档 Y 的 precision 差异"），必须**显式说明未直接满足**，不得含糊合并后宣称已达成。

---

## 4. 脚本骨架（按顺序，两法共用同一份 counts）

| # | 脚本 | 作用 |
|---|------|------|
| 01 | `01_export_for_doublet.R` | 读 Seurat rds → 校验 counts 为整数 → 导出 `counts.mtx` / `features.tsv` / `barcodes.tsv` / `metadata.csv` |
| 02 | `02_probe_r442_doublet.R` | 环境实测：`tryCatch(library(p))` 逐包**真加载**（不用 `requireNamespace`，后者只查描述不加载 DLL） |
| 04 | `04_doubletfinder_pooled.R` | 全池 DF：`NormalizeData → FindVariableFeatures(2000) → ScaleData → RunPCA(30)` → `paramSweep(pN=0.25)` → `summarizeSweep` → `find.pK` → 双档 `nExp` |
| 05 | `05_scrublet_detection.py` | 全池 scrublet 双档（含 `call_doublets` monkey-patch 绕开 skimage） |
| 06 | `06_cross_compare.py` | 混淆矩阵 + Jaccard/Kappa + 共识分类 + 每样本分层 + 标记复核 + 诊断图 |
| 07/07b | benchmark（Py + R） | in silico 合成 doublet → 各档 F1 / FPR / recall |
| 08 | `08_downstream_sensitivity.py` | 口径固化表 + 下游比例最大偏移 |
| 09 | `09_final_flags_crosslineage.py` | 最终 flag 表（**全保留，仅打 flag**）+ 跨谱系共表达 + nCount 倍数 |
| 10/10b | 多 seed benchmark（Py + R） | ≥5–10 seeds + 95% CI，判断最优档是否稳健 |

存储（会话组件式目录）：`data/` 中间矩阵、`results/` CSV、`figures/` PNG、`scripts/`、`log/`。

⚠️ `rail_review(post)` 的 `output_dir` 传**会话根目录**（同层可见 `figures/` 与 `results/`）；
传单一子目录会因"只见一半产物"被误判 `figure_count=0 → failed`，**脚本不必重跑**。

---

## 5. 常见反模式（做过就不要再做）

- ❌ 报"双细胞比例 = 7.5%"而不说明这是 flag 率
- ❌ 拿 `expected_doublet_rate=0.008` 档的自动阈值结果当真值（阈值压到分布底部时专产假阳性）
- ❌ 因 kappa 低就"换个更好的方法"重跑，而不是去做 benchmark
- ❌ 直接把两法交集当"高置信集"——若交集一方来自假阳性档，交集不可信
- ❌ 只报全局比例偏移就宣称"剔除对下游无影响"（稀有亚群 / DE / 轨迹的局部影响必须另说）
- ❌ 把 benchmark 结论外推到原始未子集化的数据集
- ❌ 单个随机种子跑一次 benchmark 就下结论（方差未估，需 ≥5 seeds + CI）
- ❌ 自己造 `doubletFinder_v3` / 硬编码列名正则 / 假定 `n_prin_comps` 在 `__init__`（见 references）

---

## 6. 相关 skill 与边界

- **`scrna-qc`** — 管 QC 过滤参数与流程（MT%/min_genes/过滤顺序）。本 skill 管**判定与决策**。
  两者常配合使用：先用 `scrna-qc` 的流程跑检测，再用本 skill 判该不该信、该不该剔。
- **版本漂移与语言互操作细节**（DoubletFinder 2.0.6 API 改名、skimage ABI → monkey-patch、
  Python bool 落 CSV 在 R 端报错、R 合成矩阵列名重复、pooled vs 分样本的样本量判据）
  → `references/doublet-toolchain-pitfalls.md`
- **完整实测案例与逐档数字**（人骨骼肌 2132 细胞 / 48 样本 / 弱信号，四档 F1 全 ≤0.344）
  → `references/worked-example-weak-signal-muscle.md`