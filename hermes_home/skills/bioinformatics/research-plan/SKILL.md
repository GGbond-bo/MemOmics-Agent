---
name: research-plan
category: bioinformatics
description: 根据研究问题自动生成Mermaid技术路线图+对照表，支持scRNA/ATAC/空间/bulk/多组学/跨物种比较/专利导向
trigger:
  when:
    - 用户问"怎么分析"、"用什么方法"、"实验方案"、"技术路线"、"研究思路"
    - 用户说"研究方案"、"实验设计"、"方案设计"、"设计实验"、"研究计划"
    - 用户说"research plan"、"research proposal"
    - 专硕/应用类研究，需要专利切入点的方案设计
  rules:
    - 生成方案前从历史消息提取研究问题、数据类型、物种、样本信息
    - 不要给通用模板，方案必须基于用户实际数据或明确的研究方向
---

## 🧩 Skill — research-plan

### 📝 简介
根据用户的研究问题、数据类型和样本信息，自动确定适用的分析模块，输出 **Mermaid 树状技术路线图** + **每步目的·工具·预期产出对照表**。不限于 scRNA-seq — 空间转录组、ATAC-seq、bulk RNA-seq、多组学、跨物种比较、甚至纯思路问题，都能用同一格式给出方案。

---

### ⚙️ 功能详情

#### 1. 输入
| 字段 | 必需 | 说明 |
|------|------|------|
| 研究问题 | ✅ | 具体的研究问题或思路方向；若用户只描述思路未给数据，仍可设计"推荐分析路线" |
| 数据类型 | 可选 | scRNA-seq / scATAC-seq / 空间转录组 / bulk RNA-seq / CUT&Tag / 多组学 / 跨物种比较 / 无数据（思路咨询） |
| 物种 | 可选 | 人/小鼠/大鼠/斑马鱼/拟南芥/猴/跨物种比较 |
| 样本信息 | 可选 | 分组/批次/时间点/处理条件 |
| 比较方案 | 可选 | 如 "Treated vs Control"、"Old vs Young"、"猴 vs 人" |
| 个性化需求 | 可选 | 如 "要做免疫浸润分析"、"需要专利切入点"、"专硕应用类" |

#### 2. 步骤 1 — 数据类型判定 → 模块映射表

**首先**确认数据类型。若用户未给数据 → 按"思路咨询"模式给出推荐路线 + 数据产生建议。若给了数据类型 → 从下表选取：

##### 📦 scRNA-seq 模块
| 模块 | 触发条件 | 关键工具 |
|------|----------|----------|
| QC 与去污染 | 始终 | CellBender, DropletUtils, scDblFinder |
| 基础分析（聚类+注释） | 始终 | Seurat/Scanpy (SCT, PCA, UMAP, Leiden) |
| 批次整合 | >=2 批次 | Harmony/scVI/Scanorama + LISI/ASW/kBET |
| 差异表达 | 有比较方案 | presto, MAST, Wilcoxon, DESeq2 |
| 功能富集 | 有 DEG 结果 | clusterProfiler (GO/KEGG), GSEA |
| 轨迹推断 | 有时间序列/发育 | Monocle3, Slingshot, scVelo |
| 细胞通讯 | 多细胞类型 | CellChat, NicheNet |
| 调控网络 | 需要转录因子分析 | pySCENIC, GRNBoost2 |

##### 📦 scATAC-seq 模块
| 模块 | 触发条件 | 关键工具 |
|------|----------|----------|
| QC + 片段分布 | 始终 | Signac, ATACseqQC |
| Peak calling + 注释 | 始终 | MACS2, HOMER, ChIPseeker |
| 降维+聚类 | 始终 | Signac (LSI, UMAP) |
| TF motif 富集 | 始终 | chromVAR, JASPAR |
| 差异可及性 | 有比较方案 | Signac, edgeR |
| 足迹分析 | 需 TF 结合证据 | HINT-ATAC, TOBIAS |
| RNA+ATAC 联合 | 有配对 scRNA | Signac (gene activity), ArchR |

##### 📦 空间转录组模块
| 模块 | 触发条件 | 关键工具 |
|------|----------|----------|
| 空间 QC + 预处理 | 始终 | Seurat/Squidpy/Giotto |
| 空间特征可视化 | 始终 | SpatialFeaturePlot, spatialDE |
| 空间域/区域识别 | 始终 | BayesSpace, SpaGCN, StLearn |
| 空间可变基因 | 始终 | SPARK-X, spatialDE, trendsceek |
| 细胞类型反卷积 | 有 scRNA 参考 | RCTD, SPOTlight, cell2location |
| 空间通讯 | 有配体-受体 | COMMOT, SpatialDM |

##### 📦 bulk RNA-seq 模块
| 模块 | 触发条件 | 关键工具 |
|------|----------|----------|
| 质控 + 比对 | 始终 | FastQC, STAR, Salmon |
| 差异表达 | 有比较方案 | DESeq2, edgeR, limma |
| 功能富集 | 有 DEG 结果 | clusterProfiler, GSEA |
| 免疫浸润 | 需要微环境分析 | CIBERSORTx, TIMER, MCP-counter |
| WGCNA | 有性状数据 | WGCNA (共表达模块) |
| 药物靶点预测 | 有疾病组 | DrugBank, Connectivity Map |

##### 📦 多组学整合模块
| 组学组合 | 整合策略 | 关键工具 |
|----------|----------|----------|
| RNA + ATAC | gene activity bridge | Signac, ArchR |
| RNA + 蛋白(CITE-seq) | WNN | Seurat v5 WNN |
| RNA + 空间 | 反卷积 + 映射 | RCTD, cell2location |
| RNA + 甲基化 | 基因座关联 | MOFA, mixOmics |
| 跨物种比较 | 同源基因映射 + Domain Adaptation | Seurat CCA/Harmony, biomartr, OrthoFinder, XGBoost + SHAP |

##### 📦 跨物种比较专项模块（专硕应用类/专利导向）
| 模块 | 触发条件 | 关键工具 | 专利方向 |
|------|----------|----------|----------|
| 跨物种细胞类型对齐验证 | 两种物种的snRNA/scRNA数据 | Seurat FindTransferAnchors, SingleR | — |
| 细胞组成保守性分析 | 两物种均有young/old分组 | MiloR + Pearson相关性 | 细胞类型替代性指数(CTRI) |
| 跨物种DEG保守性 | 鉴定了各物种的衰老DEG | DESeq2 pseudobulk, Venn分析 | 保守性衰老基因面板 |
| 跨物种通讯比较 | 有细胞类型注释 | CellChat v2.1 compareInteractions | 信号通路替代性评分 |
| 跨物种衰老预测模型 | 物种A数据 → 预测物种B | XGBoost + Harmony Domain Adaptation + SHAP | 跨物种衰老预测模型专利 |

### 🧪 专利查新 — 方案含方法学创新点时必须执行

当方案涉及**方法学创新点**（评分系统、预测模型、基因集组合物等），先做5轮专利查新再推进分析：

**查新5轮覆盖**: (1) PubMed/Europe PMC (2) Semantic Scholar (3) Google Scholar中英文双通道 (4) 中国专利数据库关键词组合 (5) 全球专利数据库（Lens.org/Espacenet）

**查新后判断逻辑**:
| 查出什么 | 含义 | 行动 |
|---------|------|------|
| 相同技术方案已被授权 | ❌ 不可申请 | 报告用户换方向 |
| 有论文但无专利，概念部分重叠 | ⚠️ 需差异化 | 制作对比表突出差异 |
| 纯科学发现未包装为方法 | ❌ 不可直接专利 | 包装为方法/系统/模型 |
| 无任何命中 | ✅ 可申请 | 推进分析 |

**差异化对比表模板**（当存在最接近论文时，按以下格式制作）:
| 维度 | 现有文献（示例: He 2024 PLoS One） | 本方案 |
|------|-----------------------------------|--------|
| 物种对 | 鼠→人 | 猴→人（灵长类更接近） |
| 细胞类型 | 仅小胶质细胞 | 全海马细胞类型 |
| 方法深度 | 简单DEG比对 | 多维度加权评分系统S₁-S₅ |
| 量化输出 | 定性描述 | 量化评分+等级判定A/B/C/D |
| 预测模块 | 无 | 跨物种衰老预测模型 |

### 🧪 无实验样本的计算验证策略

当用户问"没有人脑实验样本怎么验证？"时启用。三层纯计算验证体系：

**层1: 内部交叉验证** — 物种A split young/old, CV测稳定性；物种A训练基因集→物种B验证

**层2: 外部独立验证（GEO公开数据）**
- 搜索GEO: `query = "{tissue} {species} aging single nucleus"`
- 常用人海马衰老数据集: GSE278576（40供体全寿命周期snRNA-seq+snATAC-seq）, GSE199243（13供体寿命周期胶质图谱）, GSE268609（78样本神经发生）, GSE185553（5供体寿命图谱）
- 评分系统在独立数据重新计算验证可重复性

**层3: 跨物种预测验证（核心）**
- 物种A训练XGBoost → 预测物种B数据 → 区分young/old
- 评估: AUC ≥ 同物种AUC×0.8 → 可替代
- 反向验证+SHAP解释一致性检验

**通过标准**: 层1 CV准确率>0.75 | 层2 评分S≥0.6 | 层3 AUC>0.75, SHAP一致性>0.6

### 🧪 多维可替代性评分系统 S₁-S₅ 公式

```markdown
S_total = w₁·S₁ + w₂·S₂ + w₃·S₃ + w₄·S₄ + w₅·S₅

S₁ = 细胞比例变化一致性 = Pearson r(Δprop_monkey, Δprop_human)   [w₁=0.15]
S₂ = 共享DEG比例 = |共享∩同向| / |共享∪特有|                      [w₂=0.25]
S₃ = 通路Jaccard = |pathway_monkey ∩ pathway_human| / |∪|         [w₃=0.20]
S₄ = 通讯保守性 = 共享显著通路 / 总显著通路数                       [w₄=0.15]
S₅ = 跨物种预测AUC = AUC(monkey_model → human_data)              [w₅=0.25]

等级: A (≥0.75) / B (0.50-0.75) / C (0.25-0.50) / D (<0.25)
```
权重可在Phase完成后由 debate_analysis 讨论调整。

**专硕应用类研究设计要点**:
- 研究方案必须以应用价值为导向：猴能否替代人做实验
- 必须有专利切入点：每个 Phase 至少对应一个可专利的技术方案
- 假说要回答实际问题，而非纯机制探索："能不能替代"比"机制是什么"更适合专硕
- Figure 策略必须包含"三一结构"：内容描述 + 具体数值预期 + 备选解读
- 每个创新点必须有技术方案细节（计算方法/公式/权利要求示例）

##### 📦 纯思路咨询（无数据）
| 场景 | 输出 |
|------|------|
| "我想研究X通路在Y疾病中的作用" | 推荐实验设计 + 可选组学技术 + 分析路线 + 预期发现 |
| "X 基因已知功能是什么，怎么研究它" | 文献已知功能总结 + 推荐下一步实验/分析 |
| "有什么生信方法可以解决X问题" | 方法综述 + 工具对比表 + 推荐路线 |
| "专硕要写专利，需要应用类动物研究方案" | 5-Phase方案 + 可专利点分析 + 应用价值突出 |

#### 3. 步骤 2 — 生成 Mermaid 树状图

**规则：**
> ⛔ 每节点 ≤15 中文字符 — 只写模块名
> ⛔ 最多 3 层 — 一级(阶段)、二级(关键步骤)、三级(产出)
> ✅ 使用 `flowchart TD` 格式
> ✅ 不同模块用不同颜色区分（`style` 语法）

#### 4. 步骤 3 — 生成对照表

每个模块必须说明：
| 模块 | 目的（一句话） | 工具 | 预期产出 |

#### 5. 使用说明
- **触发条件**：用户询问"怎么分析"、"用什么方法"、"实验方案"、"技术路线"、"研究思路"时自动触发
- **调用方式**：`skill_view("research-plan")` 先加载本 skill，再生成方案
- **⚠️ 必须先读上下文**：生成方案前从历史消息提取研究问题、数据类型、物种、样本信息
- **⚠️ 不要给通用模板**：方案必须基于用户实际数据，没有数据就做思路咨询

---

### 🔧 方案模板（通用格式，非固定内容）

每个方案必须包含 **两个互补部分**：

#### Part A: Mermaid 树状图
- 节点简洁（模块名 ± 产出名），≤15 字
- 层数 ≤3
- 用 `style` 区分模块颜色

#### Part B: 对照表
- 每个模块一行
- 4 列：模块 / 目的 / 工具 / 预期产出
- 目的用一句话说明"为什么做这一步"
- 预期产出具体到文件名级别（如 `volcano_plot.pdf`、`DEG_table.csv`）

---

### 🔗 与其他 Skill 的协作

- **research-plan → task_plan.md**：方案生成后直接写入 `results/{session_dir}/task_plan.md`，作为分析蓝图。每个模块对应一个 Phase。
- **research-plan → 分析 skill**：根据选定的模块自动触发对应的分析 skill（如 `scrna-clustering`、`deg-analysis`、`cellchat-v2`）
- **与 SOUL.md 铁律联动**：`rail_review(pre)` 检查实际执行是否符合方案，偏差 >1 步 → 警告
