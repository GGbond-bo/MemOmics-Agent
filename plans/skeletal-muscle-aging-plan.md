# 🧬 人类骨骼肌衰老 scRNA-seq 全分析方案

> **数据**: Migule_lai_24 _new.h5ad | 324,434 cells | 人类骨骼肌 | 年轻 vs 老年
> **日期**: 2026-07-10

---

## 一、研究背景

骨骼肌衰老（sarcopenia）是老年人群失能的核心原因。单细胞转录组学在骨骼肌衰老研究中取得重要进展。

**关键文献**:
- Kim et al. (2026) 综述从 bulk 到单细胞的骨骼肌干细胞衰老转录组学研究（PMID: 41876858）
- Perez et al. (2022) 通过单核转录组鉴定骨骼肌衰老细胞特异性标志物（PMID: 36516485）
- Ma et al. (2024) 发现 FGF7 信号介导卫星细胞与 FAPs 的新型交互（PMID: 38751367）
- Walter et al. (2024) 跨小鼠寿命的骨骼肌再生转录组学发现衰老改变干细胞状态（PMID: 39578558）
- De Micheli et al. (2020) 人类骨骼肌参考单细胞转录组图谱（PMID: 32624006）

---

## 二、分析路线（8 阶段，绑定真实 Skill）

### Phase 1 | 数据概览与 QC 过滤
**Skill**: `scrna-qc` | **优先级**: 🔴 高
1. scan_data 扫描数据
2. skill_view scrna-qc + search_knowledge(骨骼肌QC参数)
3. nFeature 200-6000, MT% < 15%, DoubletFinder
4. CellBender 环境RNA去除（如有原始h5）

### Phase 2 | 聚类与注释验证
**Skill**: `scrna-clustering` + `create_harmony_embeddings_scRNA` | **优先级**: 🔴 高
1. SCTransform v2 → PCA 50PC → Harmony
2. UMAP 30 dims → Leiden (res=0.5)
3. SingleR + FindAllMarkers 注释验证

### Phase 3 | 差异表达分析（年轻 vs 老年）
**Skill**: `deg-analysis` | **优先级**: 🔴 高
1. Pseudobulk DESeq2 + Wilcoxon + MAST 三方法
2. 各细胞类型分别比较
3. 三方法交集 → 高置信 DEG

### Phase 4 | 功能富集分析
**Skill**: `functional-enrichment-from-degs` | **优先级**: 🔴 高
1. GO/KEGG/Reactome ORA
2. GSEA 排名分析
3. 各细胞类型特异性通路

### Phase 5 | 轨迹推断（scTour）
**Skill**: `sctour-trajectory-inference` | **优先级**: 🔴 高
1. VAE 潜在时间推断（无监督）
2. 向量场 + 分化轨迹
3. 年龄梯度锚点分析

### Phase 6 | 细胞通讯分析
**Skill**: `cellchat-v2` | **优先级**: 🟡 中
1. CellChat v2 配体-受体分析
2. 年轻 vs 老年差异信号通路
3. MuSC-FAP 交互（FGF7 等）

### Phase 7 | 基因调控网络与衰老评分
**Skills**: `grn-pyscenic` + `senescence-detection` + `upstream-regulator-analysis` | **优先级**: 🟡 中
1. pySCENIC regulon（GPU RTX 5070 Ti）
2. SASP 评分 + p16/p21 表达
3. 上游调控因子推断

### Phase 8 | 可视化与综合报告
**Skills**: `cns-visualization` + `bioinformatics-html-report` | **优先级**: 🟢 低
1. Nature/Cell 级别 UMAP/DotPlot/Heatmap
2. 交互式 HTML 报告

---

## 三、待办清单

| ID | 任务 | Skill绑定 | 优先级 |
|----|------|-----------|--------|
| M01 | 数据概览与QC过滤 | scrna-qc | 🔴 高 |
| M02 | 聚类与注释验证 | scrna-clustering, create_harmony_embeddings_scRNA | 🔴 高 |
| M03 | 差异表达分析（年轻 vs 老年） | deg-analysis | 🔴 高 |
| M04 | 功能富集分析 | functional-enrichment-from-degs | 🔴 高 |
| M05 | 轨迹推断（scTour） | sctour-trajectory-inference | 🔴 高 |
| M06 | 细胞通讯分析 | cellchat-v2 | 🟡 中 |
| M07 | 基因调控网络（SCENIC） | grn-pyscenic | 🟡 中 |
| M08 | 衰老评分与SASP | senescence-detection | 🟡 中 |
| M09 | 上游调控因子分析 | upstream-regulator-analysis | 🟡 中 |
| M10 | CNS发表级可视化 | cns-visualization | 🟢 低 |
| M11 | HTML综合报告 | bioinformatics-html-report | 🟢 低 |

---

## 四、参考文献

1. Kim S, et al. *Cell Res*. 2026. PMID: 41876858
2. Perez K, et al. *Aging*. 2022. PMID: 36516485
3. De Micheli AJ, et al. *Skeletal Muscle*. 2020. PMID: 32624006
4. Ma L, et al. *J Cachexia Sarcopenia Muscle*. 2024. PMID: 38751367
5. Walter LD, et al. *Nat Aging*. 2024. PMID: 39578558
6. Guo H, et al. *Arch Gerontol Geriatr*. 2024. PMID: 38852373
7. Wang Q, et al. *QJM*. 2025. PMID: 40343466
