# 🧬 人类骨骼肌衰老 scRNA-seq 完整分析方案
**数据**: D:/我的下载/Migule_lai_24 _new.h5ad (324,434 cells, 已注释)
**物种**: Homo sapiens | **组织**: 骨骼肌 | **方向**: 衰老 (young vs old)
**创建日期**: 2026-07-10

---

## 【研究背景】

肌少症（sarcopenia）是衰老导致骨骼肌质量与功能进行性下降的综合征，影响全球约15%的老年人。近年来单细胞/单核转录组学（sc/snRNA-seq）为解析骨骼肌衰老的细胞异质性提供了前所未有的分辨率。Kedlian et al. (2024, *Nature Aging*) 构建了人类肋间肌衰老图谱（90,902 cells + 92,259 nuclei），揭示了肌卫星细胞核糖体生物发生下降、神经肌肉接头核扩张、快肌纤维代偿性上调等关键机制。Gong et al. (2026, *Aging Cell*) 从股外侧肌发现衰老导致肌纤维从"年轻"状态向"老年"状态转变，伴随RUNX1+混合纤维亚型的显著涌现。

## 【文献依据】

| # | 文献 | PMID | 关键发现 |
|:--|:-----|:-----|:---------|
| 1 | Kedlian et al. 2024, *Nature Aging* | 38622407 | Human skeletal muscle aging atlas |
| 2 | Gong et al. 2026, *Aging Cell* | 41979358 | snRNA-seq muscle fiber heterogeneity |
| 3 | Shen et al. 2024, *Frontiers in Immunology* | 39026669 | Sarcopenia immune microenvironment |
| 4 | Kim et al. 2023, *Nature Communications* | 36658112 | snRNA-seq aging muscle |
| 5 | Dos Santos et al. 2025, *Cell Reports* | 40632651 | MAF TF in denervation atrophy |
| 6 | scAgeCom (2023), *Nature Aging* | 37169972 | Aging cell-cell communication atlas |

## 【分析路线 — 8个阶段，14个Skill】

### Phase 0: 数据准备与探索
| 步骤 | Skill | 产出 |
|:-----|:------|:-----|
| 0.1 scan_data | — | 数据元信息 |
| 0.2 check_env | — | 依赖检查 |
| 0.3 验证注释 | `annotate_celltype_scRNA` | 注释与KB一致性 |

### Phase 1: 差异表达分析
| 步骤 | Skill | 产出 |
|:-----|:------|:-----|
| 1.1 Pseudobulk DESeq2 | `deg-analysis` | 每细胞类型 DEG |
| 1.2 Wilcoxon/MAST | `deg-analysis` | 单细胞级验证 |
| 1.3 功能富集 | `functional-enrichment-from-degs` | GSEA/ORA |

### Phase 2: 细胞通讯分析
| 步骤 | Skill | 产出 |
|:-----|:------|:-----|
| 2.1-2.4 | `cellchat-v2` | L-R互作, 多条件比较 |

### Phase 3: 轨迹/拟时序分析
| 步骤 | Skill | 产出 |
|:-----|:------|:-----|
| 3.1-3.2 | `sctour-trajectory-inference` | 潜在时间+向量场 |
| 3.3-3.4 | `scrna-trajectory-inference` | 去神经化+混合纤维 |

### Phase 4: 基因调控网络
| 步骤 | Skill | 产出 |
|:-----|:------|:-----|
| 4.1-4.3 | `grn-pyscenic` | Regulon + AUCell |
| 4.4 | `upstream-regulator-analysis` | ChIP-Atlas TF排名 |

### Phase 5: 共表达网络
| 步骤 | Skill | 产出 |
|:-----|:------|:-----|
| 5.1-5.3 | `coexpression-network` | WGCNA模块 |

### Phase 6: 生物标志物
| 步骤 | Skill | 产出 |
|:-----|:------|:-----|
| 6.1-6.2 | `lasso-biomarker-panel` | LASSO panel + AUC |

### Phase 7: 可视化与报告
| 步骤 | Skill | 产出 |
|:-----|:------|:-----|
| 7.1 | `cns-visualization` | 发表级组图 |
| 7.2 | `bioinformatics-html-report` | 完整交互报告 |

## 【图表策略】
- Fig1: UMAP + 细胞类型总览
- Fig2-3: DEG火山图 + GSEA
- Fig4: CellChat和弦图
- Fig5-6: scTour向量场 + 去神经化分析
- Fig7: pySCENIC regulon
- Fig8: WGCNA模块
- Fig9: LASSO ROC
- Fig10: 综合Summary

## 【验证建议】
1. 多方法DEG交叉验证 (DESeq2/Wilcoxon/MAST)
2. 知识库结果一致性对比
3. 关键参数多值尝试+辩论
4. 去神经化/混合纤维标记物专项验证
5. 外部文献(Kedlian 2024/Gong 2026)对照

