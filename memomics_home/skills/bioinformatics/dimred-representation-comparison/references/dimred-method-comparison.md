# 降维表示对比配方（PCA vs scVI vs Harmony）：分群质量评估与归因

来源：2026-09-24 会话（MF_2000 人骨骼肌肌核 2132 细胞 × 51227 基因 / 48 样本 / 10 均衡抽样亚型）；
结论经两轮 L2 多角色辩论定级（verdict=modify）。

## 何时用
「用 X 降维和 Y 降维对比，哪个分群更干净」——**方法学结论定级**问题，不是普通出图任务。
交付的不是一张图，而是**带限定词的结论 + 可审阅的证据表**。

---

## 流水线结构（6 脚本，全部落盘可复跑）

| 阶段 | 脚本 | 产物 |
|---|---|---|
| 1 导出 | `01_export_for_scvi.R` | counts.mtx / genes.tsv / barcodes.tsv / meta.csv / pca.csv / harmony.csv / umap_native.csv / pca_variance.csv |
| 2 训练 | `02_scvi_train.py` | `latent_<tag>.csv` ×3 / `scvi_history_<tag>.csv` / `scvi_versions.json` |
| 3 评估 | `03_compare_eval.py` | metrics_summary.csv / louvain_vs_annotation.csv / knn_purity_detail.csv / pairwise_separability_<tag>.csv / `umap_<tag>.csv` / `louvain_<tag>_res<r>.npy` |
| 4 出图 | `04_figures.py` | fig1（各版 UMAP + 局部纯度）/ fig2（指标 6 面板）/ fig3（ELBO + 亚型-簇占比） |
| 5 稳健性 | `05_robustness.py` | robustness_seeds.csv / robustness_bootstrap.csv / robustness_ci.csv / batch_confounding.csv(.json) / fairness_input_route.csv |
| 6 定稿 | `06_final_verdict.py` | table1–3 证据附表 / flip_criteria.md / FINAL_CONCLUSION.md |

### 导出要点（R → Python）
- counts 用 **RNA raw counts** 取 SCT-HVG 子集（与 PCA 同基因集），`Matrix::writeMM` + genes.tsv + barcodes.tsv + meta.csv
- 坐标一并导出：`Embeddings(obj, "pca"/"harmony"/"umap")`
- 校验：全整数、nnz、每细胞总计数范围（`colSums` 419–12514 之类合理性）
- ⚠️ `write.csv` 的行名列读回时是 `Unnamed: 0` → `pd.read_csv(..., index_col=0)`

### ⚠️ 跨脚本字段契约
下游脚本取上游 CSV 时用 `.mean()` / `.reindex` 而非 `.iloc[0]` —— 不同阶段脚本的表示集合可能不同
（实测：`metrics_summary.csv` 来自 03 只有 6 个原始表示，而 `batch_confounding.csv` 来自 05 多了 `PCA_raw30`），
直取会 `IndexError: single positional indexer is out-of-bounds`。

---

## 关键实现片段

### 统一 UMAP + 聚类（严格同参，零新依赖）
```python
def umap_louvain(emb, seed, res, k=30, min_dist=0.3):
    a = ad.AnnData(X=np.asarray(emb, dtype=np.float32), obs=meta.copy())
    sc.pp.neighbors(a, n_neighbors=k, use_rep="X", random_state=seed)
    sc.tl.umap(a, min_dist=min_dist, random_state=seed)
    G = nx.from_scipy_sparse_array(a.obsp["connectivities"])
    parts = nx.algorithms.community.louvain_communities(G, resolution=res, seed=seed)
    lab = np.zeros(a.n_obs, dtype=int)
    for i, c in enumerate(parts): lab[list(c)] = i
    return a.obsm["X_umap"], lab
```
`networkx.louvain_communities` 替代 Leiden/Louvain 包 —— 与 scanpy Louvain 同算法族，无需 leidenalg。

### 指标（避开 sklearn 陷阱）
```python
def knn_purity(emb, lab, k=15):
    idx = NearestNeighbors(n_neighbors=k+1).fit(emb).kneighbors(emb, return_distance=False)[:, 1:]
    return float(np.mean([np.mean(lab[idx[i]] == lab[i]) for i in range(len(lab))]))

def ilisi(emb, batch, k=15):                      # 批次混合度，理想值 = 批次数
    idx = NearestNeighbors(n_neighbors=k+1).fit(emb).kneighbors(emb, return_distance=False)[:, 1:]
    vals = []
    for i in range(len(batch)):
        _, cnt = np.unique(batch[idx[i]], return_counts=True); p = cnt / cnt.sum()
        vals.append(1.0 / np.sum(p ** 2))
    return np.array(vals)

# 🔴 混淆矩阵：用 crosstab，不要用 confusion_matrix
ct = pd.crosstab(pd.Series(labels, name="subtype"), pd.Series(lab, name="cluster"))
row_max = ct.values.max(1) / np.maximum(ct.values.sum(1), 1)   # 每亚型在最佳簇中的占比
```
🔴 `sklearn.metrics.confusion_matrix(labels, lab)` 取两数组标签的**并集**作行列 → 10 个字符串亚型 + 11 个整数簇
= **21×21**，前 10 行全 0 ⇒ purity 中位数算成 **0.000（假结果）**；str×int 混用还会抛
`ValueError: Mix of label input types`。ARI/NMI **不受影响**（内部各自 LabelEncoder）。

### 样本级 bootstrap（评估指标不确定性的正确单位）
```python
uniq_s = np.unique(smpl); rng = np.random.default_rng(42); B = 40
for b in range(B):
    pick = rng.choice(uniq_s, size=len(uniq_s), replace=True)
    idx = np.concatenate([np.where(smpl == s)[0] for s in pick])
    # 在 idx 子集上重算指标 → 收集差值 → 取 2.5 / 97.5 分位 + 方向稳定率 (v>0).mean()
```

### 输入路线解耦（决定性对照 B 腿）
```python
# PCA_raw：与 scVI 同源 —— 同一 raw counts 矩阵、同一 HVG 子集，只换标准化路线
sc.pp.normalize_total(a, target_sum=1e4); sc.pp.log1p(a); sc.pp.scale(a, max_value=10)
sc.tl.pca(a, n_comps=30, svd_solver="arpack", random_state=42)
```

### scVI 训练（小数据 2 分钟跑完 3 版，GPU）
```python
scvi.model.SCVI.setup_anndata(a)                    # 无批次
# 或 setup_anndata(a, batch_key="samplename")        # 含批次
m = scvi.model.SCVI(a, n_latent=n_latent, n_layers=2, dropout_rate=0.1, gene_likelihood="zinb")
m.train(max_epochs=400, early_stopping=True, early_stopping_patience=20,
        check_val_every_n_epoch=5, plan_kwargs={"lr": 1e-3}, enable_progress_bar=False)
lat = m.get_latent_representation()
```
公式化对照：`n_latent` 跑 10（官方默认，<100k 细胞）**与 30（对齐 PCA30，排除维度混杂）**。

---

## 实测结果：MF_2000（人骨骼肌肌核，2132 细胞 / 48 样本 / 10 均衡抽样亚型）

| 表示 | 输入路线 | kNN纯度(原生) | kNN纯度(UMAP) | ARI | 簇数(res0.8) | sil_umap |
|---|---|---|---|---|---|---|
| PCA30 | SCT 正则化表达 | 0.513 | 0.455 | 0.242 | 11 | −0.006 |
| PCA_raw30 | raw→CPM/log1p/scale | 0.381 | 0.356 | 0.150 | 11 | −0.100 |
| scVI 无批次 | raw counts ZINB, l10 | 0.379 | 0.339 | 0.122 | 15 | −0.118 |
| scVI(按样本校正) | raw counts ZINB, l10 | 0.451 | 0.394 | 0.217 | 7 | −0.030 |
| Harmony30 | SCT + Harmony | 0.730 | 0.743 | 0.529 | 9 | +0.232 |

- **归因**：总增益 +0.134 = **SCT 预处理 +0.132** + 算法 +0.001 ⇒ **算法层无优劣**
- **稳定性**：4 seeds(42/1/7/2024) × 3 res(0.3/0.5/0.8) = 60 次重跑排序完全一致；
  B=40 样本级 bootstrap：
  - ΔkNN(PCA30 − scVI无批次) = +0.124 [0.109, 0.140]，稳定率 100%
  - ΔARI(PCA30 − scVI无批次) = +0.118 [0.099, 0.145]，100%
  - ΔkNN(PCA30 − **PCA_raw30**) = +0.128 [0.109, 0.141]，100% ← **归因证据**
  - ΔkNN(PCA30 − Harmony30) = −0.187 [−0.203, −0.165]，0%
- **批次**：iLISI(样本，理想 48) — PCA30 4.38 / scVI无批次 3.21 / scVI+样本 9.76 / Harmony 10.34；
  kNN 同样本 — PCA30 0.378 / scVI无批次 0.516；
  样本×亚型交叉：每样本中位含 10 亚型（min 3）、每亚型见于 40–46 样本、纯单样本亚型 **0%**
  ⇒「靠批次效应分群」的质疑**被证伪**（但样本效应真实存在）
- **共同现象**：所有表示 silhouette 原生 −0.03~+0.006、UMAP **全部 ≤0**；**10/10 亚型都被拆到 ≥2 簇**
  ⇒ 两者**都没有**干净的离散分群（肌纤维类型是连续谱）
- scVI 训练正常收敛（3 版 ELBO 3412→2209 / 3363→2169 / 3645→2219，早停均触发）⇒ 排除欠拟合

---

## 结论定级与翻转判据（两轮 L2 辩论）

**第一轮** verdict=modify：可下「本数据同参下 PCA 略贴近已有注释」弱结论，但设 3 个硬 blocks ——
① 未出多 seed/bootstrap CI 前不得称「稳定优势」；② 未做批次混杂对照前不得把优势归因亚型可分性；
③ 未统一输入前不得下「scVI 算法不如 PCA」。

**第二轮**（补齐三项后）verdict=modify，**定级 = 甲（算法层 PCA≈scVI 无优劣）+ 目标效度限定**；
工作流级说法仅作限域备注。rubrics：input_route_parity 8 / stability_and_ci 8 /
pre_registered_condition 9 / confounding_control 7 / effect_size_practical 6 /
target_validity 4 / **external_validity 3**。

写入 `flip_criteria.md` 的翻转判据：
1. **升级**：统一输入后 B=40 bootstrap ΔCI 仍排除 0 且支持 PCA；或 SCT 增益跨独立数据集复现；
   或 marker/轨迹证明注释是**离散类型**（而非连续谱切分）
2. **降级**：scVI 对称调参（n_latent sweep + 协变量）后追平/反超；或证明技术批次与亚型混杂

> 教训：**先跑输入路线解耦再写结论**。若没跑 B 腿，交付件会写成「PCA 优于 scVI」——
> 而真值是「优势来自 SCTransform 预处理，算法贡献 0.001」。

---

## 交付物清单

- `FINAL_CONCLUSION.md`：直接答案 + 归因分解 + 稳定性 + **限制** + 按目标分档的实操建议
- `table1_input_route_decomposition.csv`：算法 vs 预处理归因（含 `decomposition` 文字列）
- `table2_bootstrap_ci.csv`：差值 CI + 方向稳定率 + 结论列（稳定为正/为负/不显著）
- `table3_confounding_target_validity.csv`：iLISI + 同样本比例 + silhouette + 簇数 + 样本×亚型交叉
- `flip_criteria.md`：何时该回头重审
- figs：fig1 各版 UMAP + 局部纯度着色 / fig2 指标 6 面板 / fig3 ELBO + 亚型-簇占比 / fig4 稳健性

⛔ 结论里**不得出现「A 算法优于 B 算法」**这类无外推依据的表述；
裁决带 `blocks` 未完成项时，**先把补齐的验证做完再定稿**（高影响工具会被硬拦）。