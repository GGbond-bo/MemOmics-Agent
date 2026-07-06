---
name: literature-param-extraction
description: 从文献 PDF 提取生信参数并写入知识库。触发场景：拿到真实数据做分析时、知识库缺少对应方法/参数时、需要验证参数来源时。
trigger:
  when:
    - 用户拿到真实数据要做生信分析
    - 知识库缺少对应物种/组织/方向的方法或参数
    - 需要验证某个参数的文献来源
    - 需要补充知识库的生物学/生信/统计知识
  not_when:
    - 用户没有说要分析真实数据
    - 知识库已有充足的方法和参数
    - 只是普通聊天，不涉及分析
---

# 文献参数提取 Skill

## 触发场景

### 什么时候用
1. **拿到真实数据做分析时** — 用户提供了 h5ad/h5/matrix 等数据文件，要做生信分析。这是最主要的触发场景。
2. **知识库缺少方法/参数时** — 搜索知识库后，发现对应物种/组织/方向/测序方法的方法不完整或缺失
3. **验证参数来源时** — 需要确认某个参数（如 resolution、min_cells、MT%阈值）是否有文献支持
4. **补充知识库时** — 知识库的生物学知识、生信方法、统计方法不够，需要从文献补充

### 什么时候不用
1. 用户没有说要分析真实数据（只是聊天、问概念）
2. 知识库已有充足的方法和参数（搜索后命中充分）
3. 用户明确说不需要文献支持
4. 只是做演示/测试，没有真实数据

### 重要原则：生物学知识一般都有
生物学知识（细胞类型、marker、组织结构、已知通路）在知识库里**通常已存在**，不需要每次都重新搜索。
真正需要文献支撑的是**生信分析参数**（QC阈值、归一化、降维、聚类resolution等）——这些参数因数据集而异，必须查文献确认。
所以：优先检查知识库已有的生物学知识 → 不足时才搜文献补充；生信参数则几乎每次都要查文献。

## 文献搜索策略

### 搜索流程
1. **先确定分析上下文**: species（物种）、tissue（组织）、direction（方向）、assay（测序方法: RNA/ATAC/spatial/bulk）
   - assay 必须根据用户**真实数据的测序方法**来确定，不能瞎猜
   - 如果用户有多组学数据（如 RNA+ATAC），每种 assay 都要单独搜生信文献
2. **调用 `search_papers_by_context`** 智能搜索（自动构造多查询，覆盖生物学+生信两个角度）:
   - 生物学文献: `{species} {tissue} {direction} biology`
   - 生信文献: `{species} {tissue} {direction} {assay_term}`
   - 扩展文献: `{species} {tissue} transcriptomics`（同方向太少时扩展）
3. **下载 PDF**: 调用 `download_pdf` 下载到 `work/papers/`
4. **提取参数**: 调用 `extract_params_from_pdf` 提取文本，再由 LLM 结构化
5. **写入知识库**: 参数写入 `02_质控参数`/`03_测序方法`；**生信文献的生物学结论写入 `01_生物学知识`**

### ★ 文献数量与类型要求（核心规则）

必须搜索两类文献，数量有明确下限：

#### 第一类：生物学文献（至少 3 篇）
- **条件**: 同物种 + 同组织 + 同方向
- **目的**: 理解该组织/方向的生物学背景、已知细胞类型、marker、关键通路
- **示例**: 人类骨骼肌衰老方向 → 搜 "human skeletal muscle aging biology"
- **说明**: 生物学知识一般知识库里都有，如果知识库已有充分的生物学知识，可以减少搜索量，但至少确认1-2篇
- **实在没有同方向的**: 可以放宽到同物种+同组织+其他方向，但要标注

#### 第二类：生信文献（至少 5 篇）
- **条件**: 同物种 + 同组织 + **与用户真实测序方法一致**
- **测序方法根据真实数据确定**:
  - RNA（scRNA-seq/snRNA-seq）→ 搜 "single cell RNA-seq"
  - ATAC（scATAC-seq）→ 搜 "ATAC-seq"
  - spatial（空间转录组）→ 搜 "spatial transcriptomics"
  - bulk（Bulk RNA-seq）→ 搜 "bulk RNA-seq"
  - **多组学都可以** — 如果用户数据是多组学（如 RNA+ATAC），每种 assay 都搜
- **优先级**:
  1. **最优先**: 同物种 + 同组织 + 同方向 + 同测序方法（如 人类+骨骼肌+衰老+scRNA-seq）
  2. **次优先**: 同物种 + 同组织 + **同测序方法** + 其他方向（如 人类+骨骼肌+scRNA-seq+发育/疾病）
  3. **兜底**: 同物种 + 同组织 + 其他组学方法（如 人类+骨骼肌+bulk RNA-seq）
- **实在没有**: 可以放宽，但要在知识库里标注 "该方向文献稀少，参数基于现有文献+数据质量推断"
- **数量下限**: 至少 5 篇，多多益善

#### 文献选择策略
- **相关性优先于引用数**: `search_papers_by_context` 已按相关性排序（同方向>同组织>通用），不要被高引经典文献带偏
  - 反例: "hallmarks of aging" 是高引经典，但不是骨骼肌衰老特异性文献，应排后面
- **近5年优先**: 生信方法迭代快，优先 2020 年后的文献
- **顶刊优先**: Nature/Science/Cell/Nat Med/Nat Commun/Cell Reports 优先
- **同方法多组学**: 如果找到同时做了 RNA+ATAC 的文献，一篇可同时支撑两种 assay

### ★ 生信文献结论入生物学知识库（重要）

生信文章不仅提取参数，其**生物学发现/结论**也要写入 `01_生物学知识/`:
- 新发现的细胞类型/亚型 → 写入 `01_生物学知识/cell_types.yaml`
- marker 基因 → 写入 `01_生物学知识/markers.yaml`
- 方向相关的关键基因/通路（如衰老的 SASP、p16、p21）→ 写入 `01_生物学知识/key_genes.yaml`
- 细胞组成变化（如衰老后免疫细胞浸润增加）→ 写入 `01_生物学知识/composition.yaml`

这样生物学知识库会随文献积累越来越丰富，后续分析可直接复用。

### 文献源
- PubMed (NCBI E-utilities) — 主要源，免费无需 key
- EuropePMC — 补充源（含 preprints、覆盖更广，相关性排序好）
- Semantic Scholar — 补充源（含引用数、开放PDF链接，429限流时自动跳过）

### 搜索关键词示例
```
物种: Homo sapiens / human / mouse / macaque / zebra fish
组织: skeletal muscle / brain / heart / liver / kidney
方向: aging / development / disease / regeneration / cancer
测序: single cell RNA-seq / snRNA-seq / ATAC-seq / spatial transcriptomics / bulk RNA-seq
```

### 搜索示例（人类骨骼肌衰老方向）
```
生物学文献 (>=3篇):
  - "human skeletal muscle aging biology"
  - "human skeletal muscle aging mechanism"

生信文献 (>=5篇, 按实际 assay):
  RNA:    "human skeletal muscle aging single cell RNA-seq"
          "human skeletal muscle single cell RNA-seq"  # 同方向不够时扩展
  ATAC:   "human skeletal muscle aging ATAC-seq"
          "human skeletal muscle ATAC-seq"
  spatial:"human skeletal muscle aging spatial transcriptomics"
  bulk:   "human skeletal muscle aging bulk RNA-seq"
          "human skeletal muscle bulk RNA-seq"  # 兜底
```

## 参数提取规则

### 从文献中提取什么
1. **QC 参数**: nFeature_RNA 范围、nCount_RNA 范围、percent_mt 阈值、doublet_rate
2. **归一化方法**: SCTransform / LogNormalize / sctransform v2
3. **降维参数**: PCA 维度数（通常 30-50）、UMAP n_neighbors、min_dist
4. **聚类参数**: resolution（关键！需收集多篇文献的值做对比）、algorithm（Leiden/Louvain）
5. **批次校正**: Harmony / Seurat integration / fastMNN / CCA
6. **DEG 方法**: DESeq2 pseudobulk / MAST / Wilcoxon
7. **注释方法**: SingleR / CellTypist / manual marker
8. **细胞通信**: CellChat / NicheNet
9. **轨迹分析**: Monocle3 / Slingshot / RNA velocity
10. **通路分析**: clusterProfiler / GSEA / fgsea

### 参数记录格式
每个参数必须标注:
- **value**: 参数值
- **source**: 文献来源（作者 + 年份 + 期刊 + DOI）
- **confidence**: high（多篇文献一致）/ medium（单篇文献）/ low（推断）
- **usage_rate**: 该参数在文献中的使用率（如 "8/10 篇文献使用 resolution 0.8"）

### 知识库写入位置
```
knowledge_base/
  {species}/          # Homo_sapiens / Mus_musculus / ...
    {tissue}/         # skeletal_muscle / brain / ...
      {direction}/    # aging / development / ...
        01_生物学知识/   # 细胞类型、marker、基因集、生物学发现
        02_质控参数/     # QC 阈值（nFeature、MT%、doublet rate）
        03_测序方法/
          RNA/          # scRNA-seq 方法（归一化、降维、聚类、DEG等）
          ATAC/         # scATAC-seq 方法
          spatial/      # 空间转录组方法
          bulk/         # Bulk RNA-seq 方法
        04_个性化/       # 方向特异的分析（如衰老的 SASP、去神经化等）
  statistics/           # 统计方法（不放在物种下，与物种并列）
```

### RNA 方法分 R 和 Python
RNA 测序方法要区分实现语言:
- **R**: Seurat / SCTransform / Harmony / CellChat / Slingshot / hdWGCNA
- **Python**: scanpy / scvi-tools / CellBender / scVelo / CellTypist

## MemOmics 核心规则

### 规则 1: 拿到真实数据必须搜索文献
拿到真实数据后，如果知识库搜索结果不充分，必须调用 `search_papers_by_context` 搜索文献，不能自己编参数。

### 规则 2: 所有参数必须有来源
写入知识库的每个参数必须标注 `source`（文献来源）和 `confidence`（置信度），不能写无来源的参数。

### 规则 3: 参数使用率统计
提取参数时，统计该参数在多篇文献中的使用率，帮助判断是否为通用做法:
```yaml
clustering:
  resolution:
    value: 0.8
    usage_rate: "8/10 篇文献使用 0.6-0.8"
    alternatives:
      - value: 0.6
        usage: "5/10 篇"
      - value: 1.0
        usage: "2/10 篇（细胞数多时）"
    source: "Kim et al. 2023, Nat Commun; Liu et al. 2022, Nat Med"
    confidence: high
```

### 规则 4: 统计方法独立存放
统计方法（如 DESeq2 pseudobulk、Fisher exact test、Wilcoxon rank-sum）放在 `knowledge_base/statistics/` 下，不放在物种目录下，因为统计方法是通用的。

### 规则 5: 知识库不足时的三级策略
1. **第一级**: 搜索知识库 → 如果命中充分，直接用
2. **第二级**: 知识库不足 → 调用文献搜索 → 下载 PDF → 提取参数 → 写入知识库 → 再用
3. **第三级**: 文献也找不到 → 按 skill 预设参数 + 自身数据质量决定 → 辩论后选择

## 工具链

1. `search_papers_by_context(species, tissue, direction, assay)` → 搜索文献
2. `download_pdf(url_or_pmid)` → 下载 PDF
3. `extract_params_from_pdf(pdf_path)` → 提取 PDF 文本
4. LLM 结构化提取 → JSON 参数
5. `write_to_kb.py` → 写入知识库 YAML
6. `search_knowledge(species, tissue, direction, assay)` → 验证写入成功


---

## 🗣️ 辩论机制（debate_analysis）

本 skill 在执行后，如果涉及**参数选择、方法决策、结果判断**等不确定环节，**必须**调用  工具进行多角色辩论。

### 辩论规则
- **正方 3 角色**（各自独立，互相看不到）：生物学 agent / 统计学 agent / 生信 agent
- **反方 4 角色**（各自独立，互相看不到，也看不到正方）：生物学 agent / 统计学 agent / 生信 agent / 历史经验 agent
- **裁判**：看到所有 7 方论点后给出裁决 + 置信度（高/中/低）
- **上下文隔离**：每个角色是独立的 LLM API 调用，messages 只包含自己的 prompt

### 触发场景
- 参数选择有多个合理选项时（如分辨率 0.4 vs 0.6 vs 0.8）
- 结果可能受方法选择影响时（如不同注释方法给出不同结果）
- 生物结论需要验证可靠性时
- QC 阈值不确定时（如 MT% 阈值 10% vs 15% vs 20%）

### 不触发场景
- 参数有明确知识库推荐且无争议时
- 纯计算步骤（如保存文件、读取数据）
