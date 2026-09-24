---
name: dimred-representation-comparison
description: "降维/embedding 表示对比与分群质量定级（PCA vs scVI vs Harmony 等）。触发：'哪个分群更干净'、'scVI 和 PCA 对比'、'换个 embedding 会不会更好'、'降维方法对比'、'embedding 对比'、'用 scVI 做个 embedding 和 PCA 的 UMAP 比一下'。含严格同参原则、输入路线解耦归因、指标集与 sklearn 陷阱、多 seed×多分辨率+样本级 bootstrap 稳定性验证、结论定级与限定词写法。"
when_to_use: "用户要求比较两种及以上降维/embedding 表示（PCA / scVI / Harmony / scANVI / NMF…），或问'哪个分群更干净 / 哪个 UMAP 更好'，或需要为降维选择给出可审阅的结论时。也可用于审查他人已有的降维对比结论是否站得住。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [dimensionality-reduction, scvi, pca, harmony, clustering-quality, benchmark, conclusion-grading, 02_基础分析]
    difficulty: intermediate
    language: R+Python
    category: scRNA
prerequisites:
  python_packages: ["scanpy", "anndata", "scikit-learn", "umap-learn", "networkx"]
---

# 降维表示对比与分群质量定级

> 这是**方法学结论定级**类任务，不是出图任务。用户问「哪个分群更干净」时，他要的是
> **带限定词的结论 + 可审阅的证据表**；一张 UMAP 并排图说服不了任何人。

## ⛔ 三条铁律（违反任一条，结论就是错的）

1. **严格同参**：基因集 / neighbors k / UMAP(min_dist, seed) / 聚类算法与分辨率网格 / 评估标签列，全部统一。
2. **先解耦输入路线再谈算法优劣**：PCA 与 scVI 的输入路线天然不同（SCT 正则化表达 vs raw counts），
   不补一条「同路线 PCA」对照，你测到的是**预处理差异**，不是算法差异。
3. **差异必须过稳定性关**：单 seed + 单分辨率的领先不算领先；要给 bootstrap 差值 CI 与方向稳定率。

---

## Step 0：先确认问题形态（不懂就问，别猜）

| 用户说法 | 实为 | 做法 |
|---|---|---|
| 「用 scVI 做 embedding，和 PCA 的 UMAP 比，哪个分群更干净」 | 方法对比 + 定级 | 走本 skill 全流程 |
| 「帮我跑个 scVI」 | 单方法执行 | 只是跑 scVI，不做对比结论 |
| 「随你怎么做」+ 已有数据 | 授权 | 端到端做完并交付证据表 |

⚠️ 若对象里 `annotation` 列来源不明（谁标的、按什么标的），**先问清或标注为代理标签** ——
后面所有 ARI/kNN 纯度都以它为基准。

---

## Step 1：严格同参的对比设计

### 1.1 统一基因集与参数
- 两法吃**同一套 HVG**（如 SCT 的 3000 HVG 取交集）
- 统一 `neighbors(k=30)` → `UMAP(min_dist=0.3, seed=42)` → `Louvain(res 0.3/0.5/0.8)`
- 聚类零新依赖写法：`networkx.algorithms.community.louvain_communities(G, resolution=r, seed=s)`
  （与 scanpy Louvain 同算法族；Leiden 需 leidenalg，环境常缺）

### 1.2 ⛔ 不要用对象自带的 UMAP 当对照
`obj@reductions$umap@misc` 通常是 **空 list**，无法证明它基于 `pca` 还是 `harmony` 算的。
**在 Python 端用同一套参数重算两版 UMAP**，这才是可比的。把自带 UMAP/坐标导出作参考可以，作对照不行。

### 1.3 至少跑这几条腿（缺一条结论就残）
| 腿 | 输入路线 | 作用 |
|---|---|---|
| A 主方法（如 PCA30-SCT） | SCT 正则化表达 | 现状基线 |
| B **同路线 PCA**（必跑！） | raw counts → normalize_total → log1p → scale → PCA | **解耦预处理与算法** |
| C 目标方法（scVI 无 batch_key） | raw counts (ZINB) | 纯算法对比 |
| D 目标方法（scVI + batch_key） | raw counts (ZINB) | 实际应用场景（含批次信息，不与 A/B 直接比算法） |
| E 批次校正参考（Harmony） | SCT + Harmony | 提供「批次收益有多大」的标尺 |

维度要对齐：PCA30 与 scVI `n_latent=10` 天然不同，**同时跑 `n_latent=30`** 排除维度混杂
（silhouette 等指标不可跨维度直接比）。

---

## Step 2：归因分解（决定结论对错的唯一一步）

```
总增益 = 预处理贡献 + 算法贡献
       = (A − B) + (B − C)
```
**MF_2000 实测**：`0.513 − 0.379 = +0.134`，其中 SCT 贡献 **+0.132**、算法贡献仅 **+0.001**
⇒ 结论从「PCA 更优」改判为「**算法层无优劣，优势来自预处理路线**」。
不跑 B 腿，这个错误会一路带进交付件。

---

## Step 3：指标集（单指标必误导）

| 指标 | 实现要点 | 陷阱 |
|---|---|---|
| kNN 邻域纯度 (k=15) | 每细胞邻居中同标签比例 | 最直观；受类别数与小 n 影响 |
| silhouette（原生 + UMAP 2D） | 两处分别算 | **≈0 或负 ≠ 方法失败**（连续谱/高维稀疏天然如此）；不可跨维度比 |
| ARI / NMI vs 注释 | 聚类↔注释一致性 | 簇数≠类别数时被结构性压低 ⇒ **必须同时报簇数** |
| Calinski-Harabasz / Davies-Bouldin | 原生空间 | 辅助，不与 silhouette 冲突解读 |
| 类分离指数 / 成对可分性矩阵 | 每类「到最近异类质心距离 ÷ 类内离散」 | 定位**具体哪两个亚型分不开** |
| 亚型拆散度 | 每亚型平均占据的簇比例 | 全部亚型都被拆到 ≥2 簇 ⇒ 标签与聚类**本质不对齐** |
| **批次混合度** | iLISI + kNN 同样本比例 + 样本×类别交叉表 | 缺它无法排除「靠批次效应分群」的假象 |

### 🔴 sklearn `confusion_matrix` 静默出错（无报错、结果假）
`confusion_matrix(y_true, y_pred)` 取**两个数组标签的并集**作行列标签 ——
y_true 是字符串亚型名、y_pred 是整数簇号时，得到 `(10+11)×(10+11)` 矩阵，**前 10 行全 0**
⇒ purity 中位数被算成 **0.000**（看着像真结果）。
- **正解**：`pd.crosstab(labels, clusters)`（行向语义明确）
- str×int 混用还会直接抛 `ValueError: Mix of label input types`
- **不受影响**：`adjusted_rand_score` / `normalized_mutual_info_score`（内部各自 LabelEncoder，标签集可不同）、`silhouette_score`

### 局部纯度图（最直观的一张图）
每细胞按邻居同标签比例着色（RdYlGn, vmin=0, vmax=1），并排画两版 UMAP。
标题写上均值 —— MF_2000 实测 PCA-UMAP 0.455 vs scVI-UMAP 0.339，肉眼可辨。

---

## Step 4：稳定性验证（不过关就不能称「稳定」）

1. **多随机种子 × 多分辨率**：≥4 seeds × ≥3 res（如 42/1/7/2024 × 0.3/0.5/0.8），看排序是否翻转
   - MF_2000：60 次重跑五种表示排序完全一致；跨种子 kNN 波动 <0.013
2. **样本级 bootstrap（不是细胞级！）**：按 sample 有放回重抽样 B≥40，逐轮重算指标，
   报**差值 95% CI + 方向稳定率**
   - 判据：CI 排除 0 **且**稳定率 ≥95% 才算稳定
   - MF_2000：ΔkNN(PCA30−scVI无批次)=+0.124 [0.109, 0.140] 稳定率 100%
   - ⚠️ 细胞级 bootstrap 会高估显著性（同一样本内细胞高度相关）

---

## Step 5：批次混杂证伪三件套

「B 方法分得更干净」最常见的反质疑是**它靠批次/个体效应在分群**。三件套一次证伪或坐实：

1. **样本×类别交叉表**：每样本含几个亚型？每亚型见于几个样本？纯单样本亚型占比？
   - MF_2000：每样本中位含 10 个亚型（min 3）、每亚型见于 40–46 样本、纯单样本亚型 0% ⇒ **不混杂**
2. **iLISI（按样本标签）**：理想值 = 样本数。MF_2000 实测 PCA30 4.38 / scVI 无批次 3.21 / scVI+样本 9.76 / Harmony 10.34
3. **kNN 同样本比例**：MF_2000 PCA30 0.378 vs scVI 无批次 0.516（scVI 保留了更多样本效应）

---

## Step 6：结论定级与措辞（交付的核心）

### 允许 / 禁止
| ✅ 可写 | ⛔ 禁止写 |
|---|---|
| 「本数据、同参默认流程下，A 路线在 kNN 纯度/ARI 上高于 B」 | 「A 算法优于 B 算法」 |
| 「差异稳定：B=40 bootstrap CI 排除 0，方向稳定率 100%」 | 无 CI 时写「显著更优」 |
| 「优势主要来自预处理路线（归因分解）」 | 把预处理优势当算法优势 |
| 「两者均未产生干净离散分群（silhouette ≤0、N/ΣN 亚型被拆 ≥2 簇）」 | 把 ARI 高直接解读为「生物学正确」 |
| 「不可外推到其他数据集/组织/规模」 | 普适性主张 |

### 必写的限制
- **「分群更干净」≠ 生物学正确**：肌纤维类型（MYH7/MYH2/MYH1）、上皮-间质等常是**连续谱系**，
  离散聚类指标只是一致性代理指标（[PMID:42019489] 肌核图谱支持连续程序）
- 单数据集 / 单组织 / **均衡抽样设计**（每类等量抽样会系统性抬高所有纯度类指标）
- 生成式模型（scVI）的优化目标**不含**聚类可分性（[PMID:30504886]）；线性方法在多类下游任务上与深度模型持平属预期（[PMID:41506911]）
- **批次校正（Harmony / scVI `batch_key`）的收益通常远大于降维算法选择** ⇒ 先定批次路线，再挑表示

### 按目标分档给建议（用户真正要的）
| 目标 | 推荐表示 |
|---|---|
| 保留已知注释结构、做亚型水平下游分析 | SCT-PCA 或 Harmony |
| 需跨样本/跨条件整合后聚类 | Harmony 或 scVI(`batch_key=`) —— 通常比无校正版干净得多 |
| 生成式建模（DE/整合） | scVI（但别拿它当聚类优化器用） |
| 判断连续过渡（纤维类型/轨迹） | 别用离散聚类，改 marker 梯度 / 轨迹 / 程序评分 |

### 交付物清单
`FINAL_CONCLUSION.md`（直接答案 + 归因 + 稳定性 + 限制 + 分档建议）
+ `table1_input_route_decomposition.csv`（算法 vs 预处理归因）
+ `table2_bootstrap_ci.csv`（差值 CI + 方向稳定率）
+ `table3_confounding_target_validity.csv`（批次混杂 + 目标效度）
+ `flip_criteria.md`（**什么结果出现时该回头重审**）
+ figs：各版 UMAP 并排 / 局部纯度 / 指标面板 / 训练收敛 / 稳健性

---

## Common Issues

| 现象 | 根因 | 修复 |
|---|---|---|
| purity 中位数算出 **0.000** | `sklearn.confusion_matrix` 取 y_true∪y_pred 标签并集 → (10+11)×(10+11)，前 10 行全 0 | 改用 `pd.crosstab(labels, clusters)` |
| `ValueError: Mix of label input types (string and number)` | 同上：混淆矩阵拒收 str×int 混用 | 两侧统一 `astype(str)`，或直接用 crosstab |
| 对象自带 UMAP 与自算 UMAP 对不上 | `@misc` 为空、不知基于哪个 reduction | 两版都用同一套参数**重算**，自带坐标只作参考 |
| silhouette 全为 ≈0 或负 → 误判「方法失败」 | 连续谱数据 + 高维稀疏天然如此 | 别用绝对阈值判成败；配合 kNN 纯度/ARI/簇数一起看，并写入限制 |
| ARI 低但看着分群不错 | 簇数 ≠ 类别数（如真值 10 类、聚类得 15 簇） | 同时报簇数 + 亚型拆散度，别只看 ARI |
| 跨脚本取数 `IndexError: single positional indexer is out-of-bounds` | 不同阶段脚本的表示集合不同（下游多了 `PCA_raw*`） | 取数用 `.mean()` / `.reindex` 容错，别用 `.iloc[0]` |
| scVI 训练慢/报错、torch 栈版本冲突 | torch/torchvision ABI 不匹配 | 见「环境与包」小节 |

## 环境与包（踩过的坑，按 FIX 记）
- **scvi-tools 装在哪**：以 **execute 内核实际解释器**的 `import` 实测为准 —— `check_env` 可能报
  「已安装」而内核 `import scvi` 仍 `ModuleNotFoundError`（两者查的不是同一套 site-packages）。
  实测内核解释器：`import sys; print(sys.executable)`，然后把包装到它那里。
- **`RuntimeError: operator torchvision::nms does not exist`**：torch 与 torchvision 版本错配
  （例：torch 2.11 + torchvision 0.27 崩，0.27 是配 torch 2.12 的）。
  诊断：**逐层单独 import** 定位（`import torchvision` / `import torchmetrics` / `import scvi` 分别试，
  torchmetrics→lightning→scvi 是同一条链）。
  修复：按官方配对表装匹配版本，如
  `pip install "torchvision==0.26.0" --index-url https://download.pytorch.org/whl/cu128`
  （torch 2.11 ↔ tv 0.26）。**不要卸载 torchvision 了事**——可能被别的包依赖（`pip show torchvision` 看 Required-by）。
  改完必须复核 `torch.__version__` / `torch.cuda.is_available()` 未被连带降级。
- **rail_review(pre) 误报缺包**：`required_packages` 只列**该步真实必需**的包；分析用的解释器有 ≠ 审查器能解析到。
  拿不准就不传该参数。

## 触发词举例（供索引匹配）
「哪个分群更干净」「scVI 和 PCA 对比」「embedding 对比」「降维方法对比」
「用 scVI 做个 embedding 和 PCA 的 UMAP 比一下」「换个降维会不会分得更好」
「UMAP 分群质量」「降维基准」

## 参考
- 📄 `references/dimred-method-comparison.md` — 6 脚本流水线结构、指标实现代码、
  MF_2000 全部实测数值、两轮 L2 辩论的定级与翻转判据
- 相邻 skill：`scrna-clustering`（聚类/注释主流程，含 resolution 扫描与 marker 鉴定）、
  `cross-species-annotation`、`trajectory-conclusion-validation`（连续谱/轨迹类结论的定稿验证）