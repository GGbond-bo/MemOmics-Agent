# 跨物种 snRNA-seq 海马体衰老可比性分析 — 完整方案

## 适用场景
两种物种（猴vs人）的海马体衰老 snRNA-seq 数据，比较衰老转录组的保守性和物种特异性，验证动物模型的可替代性。专硕应用类，专利导向。

## Session来源
- 物种: 猕猴 (Macaca mulatta) vs 人 (Homo sapiens)
- 组织: 海马体 (Hippocampus)
- 方向: 衰老 (Aging)
- 用户类型: 专硕（应用类动物研究，需专利）
- 数据: 用户自有猴snRNA + 下载的人snRNA (公开数据)

## Phase 概览

| Phase | 名称 | 核心问题 | 主要工具 | 专利切入点 |
|-------|------|---------|----------|-----------|
| 1 | 数据对齐与跨物种整合 | 数据可比吗？ | Seurat v5, SCTransform v2, Harmony v1.2 | — |
| 2 | 细胞组成保守性 | 细胞比例变化一致吗？ | MiloR v2.0 | 细胞类型替代性指数(CTRI) |
| 3 | 衰老DEG保守性 | 基因变化路径一致吗？ | DESeq2 v1.44, clusterProfiler v4.12 | 保守性衰老基因面板 |
| 4 | 细胞通讯与调控网络 | 信号通路机制一致吗？ | CellChat v2.1, pySCENIC v0.12.1 | 信号通路替代性评分 |
| 5 | 跨物种衰老预测模型 | 能用猴数据预测人吗？ | XGBoost v2.1, Harmony, SHAP | 跨物种衰老预测模型 |

## 多维可替代性评分系统 S₁-S₅（核心专利）

```markdown
S_total = w₁·S₁ + w₂·S₂ + w₃·S₃ + w₄·S₄ + w₅·S₅

S₁ = 细胞类型比例变化一致性评分
    = Pearson r(Δprop_monkey, Δprop_human)
    计算方式：对每种细胞类型，计算衰老前后的比例变化(Δprop)，然后Pearson相关
    range: -1 to 1, w₁=0.15

S₂ = 共享DEG比例评分
    = |共享DEG ∩ 同方向变化| / |共享DEG ∪ 物种特异性DEG|
    range: 0-1, w₂=0.25

S₃ = 通路Jaccard相似性评分
    = |GO_pathway(monkey) ∩ GO_pathway(human)| / |GO_pathway(monkey) ∪ GO_pathway(human)|
    range: 0-1, w₃=0.20

S₄ = 细胞通讯保守性评分
    = 共享显著信号通路数 / 所有显著信号通路数
    range: 0-1, w₄=0.15

S₅ = 跨物种预测准确率评分
    = AUC(monkey_model → human_data)
    range: 0.5-1.0, w₅=0.25

综合评定等级：
A (可替代): S_total ≥ 0.75
B (部分可替代): 0.50 ≤ S_total < 0.75
C (有限可替代): 0.25 ≤ S_total < 0.50
D (不可替代): S_total < 0.25
```

## 三个可申请的专利方向

### 方向一：跨物种衰老可替代性评估系统（最推荐，发明专利-方法/系统类）
- 保护对象：多维加权评分方法本身（S₁-S₅公式+等级判定）
- 权利要求特征：含数据获取→联合聚类对齐→S₁-S₅计算→加权综合→等级输出
- 新颖性：无现有专利，He 2024仅做简单DEG比对，未提出多维度加权评分

### 方向二：跨物种衰老预测模型（发明专利-算法模型类）
- 保护对象：Harmony域适应+XGBoost的特定训练预测流程
- 创新点：目前无人用snRNA-seq做猴→人的跨物种域适应衰老预测

### 方向三：海马体衰老保守性特征基因集（发明专利；或先按技术秘密保护）
- 保护对象：筛选出的Top-100或Top-200共享衰老基因的组合物
- 用途：评估猴模型替代性的分子检测panel

## 公开数据资源（外部独立验证用）

### 已找到的人海马体衰老snRNA-seq数据集
| GEO ID | 标题 | 供体数 | 特点 | 用途 |
|--------|------|--------|------|------|
| GSE278576 / GSE299139 | Epigenetic and 3D genome reprogramming during aging of human hippocampus | 40 | 全寿命周期，snRNA-seq+snATAC-seq+甲基化+3D基因组，多组学 | **主验证集** |
| GSE268609 | Human hippocampal neurogenesis in adulthood, aging and AD | 78 | 神经发生焦点 | 补充验证 |
| GSE199243 | Glia diversity in human hippocampus across lifespan and in AD | 13 | 胶质细胞焦点 | 补充验证 |
| GSE185553 / GSE185277 | Human hippocampus across lifespan | 5 | 全寿命周期 | 补充验证 |
| GSE325391 | Immature neurons in human hippocampus aging and AD | 27 | 未成熟神经元焦点 | 补充验证 |

### 已有猕猴数据资源
| GEO ID | 标题 | 特点 |
|--------|------|------|
| GSE307184 | Single-cell multi-region profiling of macaque brain across lifespan | 5.3M细胞，11脑区，55只猕猴，5月-21岁 |

### 已找到的类似跨物种研究文献
| 文献 | 物种 | 组织 | 方法 | 用于 |
|------|------|------|------|------|
| He 2024 PLoS One | 鼠→人 | 海马小胶质细胞 | scRNA-seq, Seurat聚类+DEG比较 | 差异化论证（最接近现有技术） |
| Franjic 2022 Neuron | 人/猴/猪 | 海马+内嗅皮层 | snRNA-seq, Seurat聚类+跨物种比较 | 框架复用（非衰老方向） |
| Wang 2022 Cell Res | 猴(全生命周期)+人 | 海马 | snRNA-seq, ~30万核, 跨物种衰老验证 | 直接方法参考（未做量化评分） |
| Xiong 2025 Mol Biol Evol | 树鼩/人/鼠 | 海马 | snRNA-seq, 跨物种比较 | 方法参考（树鼩非猴） |
| Ma 2022 Science | 人/黑猩猩/猴/狨猴 | 前额叶皮层 | snRNA-seq+snATAC-seq, 跨灵长类 | 方法论（PFC非海马） |

## 无实验样本的验证策略（纯计算验证）

当用户无人脑实验样本时，使用三层纯计算验证体系：

### 层1：内部交叉验证
- 物种A数据internal: 随机分k折，交叉验证评分系统稳定性
- 物种A训练衰老基因集 → 物种B验证该基因集是否同样显著变化
- 使用leave-one-sample-out验证

### 层2：外部独立验证（关键）
- 使用上述GEO公开的人海马体数据集
- 评分系统S₁-S₅在独立数据上重新计算
- 验证标准：外部数据集S_total ≥ 主分析S_total × 0.85
- **注意**: 不同数据集的QC参数、平台差异会影响可比性，需在debate_analysis中讨论

### 层3：跨物种预测验证（核心创新验证）
- 训练：猴数据 → XGBoost二分类（young vs old）
- 预测：模型 → 人数据 → 看能否区分人young/old
- 评估标准：
  - AUC ≥ 同物种AUC×0.8 → 判定该细胞类型可替代
  - 引入SHAP解释：比对猴和人类衰老模型中Top-20特征基因的一致性
  - 反向验证：人模型→预测猴数据
- **这是唯一不需要人体实验就能证明"猴能否替代人"的验证方法**

## 专硕应用场景要点
- 不追求"衰老机制发现"，而是解决"猴子能不能替代人做实验"这个实际问题
- 方法学专利比机制发现专利更适合专硕定位
- 应用价值：制药公司/动物实验机构评估猴子模型时可直接使用
- 分析过程不需要额外经费买动物/做湿实验
- 纯计算生物学验证即可满足毕业要求

## 文献引用清单（本次session收集）
1. Franjic et al. 2022, Neuron. PMID: 34798047 — 人/猴/猪海马snRNA-seq跨物种比较
2. Wang et al. 2022, Cell Res. PMID: 35750757 — 猕猴全生命周期海马snRNA-seq
3. Wang et al. 2025, Genome Med. PMID: 40296047 — NHP全脑多区域衰老
4. Xiong et al. 2025, Mol Biol Evol. PMID: 40036868 — 树鼩海马衰老跨物种比较
5. He et al. 2024, PLoS One. PMID: 39591421 — 鼠→人小胶质细胞可替代性分析
6. Ma et al. 2022, Science. PMID: 36007006 — 跨灵长类PFC单细胞比较
7. Sun et al. 2025, Neuron. PMID: 39788089 — 脑衰老与年轻化综述
