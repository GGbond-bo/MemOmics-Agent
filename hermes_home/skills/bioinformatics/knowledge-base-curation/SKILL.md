---
category: General Utility
name: knowledge-base-curation
description: >
  端到端构建组织特异性多组学知识库。从文献搜索→生物知识提取→基因集构建→
  测序方法参数→多物种同步→YAML验证的完整流程。覆盖 scRNA-seq / ATAC-seq /
  spatial / bulk 四种测序方法。当知识库缺少某个物种/组织/方向的生物学知识、
  关键发现、基因集或分析参数时触发。
trigger:
  when:
    - 用户明确要求"收集文献补充知识库"或"补充XX知识库"
    - 知识库缺少某个物种/组织/方向的生物学知识（01_生物学知识/为空）
    - 知识库缺少某个物种/组织/方向的测序方法参数（03_测序方法/为空或不完整）
    - 需要为某个组织/方向构建完整的知识库，包括生物学+生信+多组学
  not_when:
    - 用户只是提问某个概念（日常问答）
    - 知识库已有充分覆盖（>3个YAML且涵盖生物学+测序方法）
    - 仅需从单篇PDF提取参数（用 literature-param-extraction）
  rules:
    - "YAML 文件必须通过 lint 检查（括号、引号、缩进）"
    - "所有参数必须有 source 标注"
    - "多物种同步时，marker 基因名按物种规范（人全大写，鼠首字母大写）"
    - "生信文献的生物学结论必须同时写入 01_生物学知识/"
---

# 知识库构建 Skill

## 概述

本 skill 定义了从零构建一个**物种+组织+方向**的三维知识库的完整流程。覆盖四种测序方法（RNA/scRNA-seq、ATAC-seq、空间转录组、Bulk RNA-seq）的生物学知识和分析参数。

## 工作流

### 阶段 1：评估现状

```
1. 检查目标目录结构
   knowledge_base/{species}/{tissue}/{direction}/
   ├── 01_生物学知识/    ← 细胞类型、marker、基因集、关键发现
   ├── 02_质控参数/      ← QC 阈值（可选）
   └── 03_测序方法/      ← 方法参数
       ├── RNA/
       ├── ATAC/
       ├── spatial/
       └── bulk/

2. 确定缺失项
   - 01_生物学知识/ 缺失 → 需要生物学知识构建
   - 03_测序方法/RNA/ 缺失 → 需要 scRNA-seq 方法
   - 03_测序方法/ATAC/ 缺失 → 需要 ATAC-seq 方法
   - 03_测序方法/spatial/ 缺失 → 需要空间转录组方法
   - 03_测序方法/Bulk/ 缺失 → 需要 Bulk RNA-seq 方法
```

### 阶段 2：文献搜索

并行搜索四种测序类型的文献。使用 `web_search`（如果 web_extract 不可用）：

```
批次1: scRNA-seq 文献
  {species} {tissue} {direction} single cell RNA-seq 2023 2024 2025
批次2: ATAC-seq 文献
  {species} {tissue} {direction} ATAC-seq chromatin epigenomics
批次3: 空间转录组文献
  {species} {tissue} {direction} spatial transcriptomics Visium MERFISH
批次4: Bulk RNA-seq 文献
  {species} {tissue} {direction} bulk RNA-seq transcriptome
批次5: 多组学文献（选做）
  {species} {tissue} {direction} multi-omics single cell
```

**筛选标准**：
- 优先近5年（2020+）文献
- 优先顶刊（Nature/Science/Cell 系列期刊）
- 每条搜索结果提取：标题、作者、期刊、年份、PMID、关键发现摘要

### 阶段 3：构建生物学知识

#### 3a. `biology_knowledge.yaml` — 细胞类型与 marker

```yaml
species: Homo sapiens
tissue: liver
direction: aging
cell_types:
  hepatocyte:
    aliases: [肝细胞, hepatocytes]
    markers: [ALB, CYP3A4, SERPINA1, TTR]
    description: 肝脏主要实质细胞
    subtypes:
      periportal_hepatocyte:
        markers: [CYP2F2, ASS1, ARG1, PCK1]
        description: 门静脉周(Zone 1)肝细胞
        aging_note: 衰老时线粒体功能下降
    aging_note: 多倍体比例上升，区域化破坏
```

**编写规则**：
- 列出该组织所有已知细胞类型（实质细胞 + 非实质细胞）
- 每种细胞给出 3-8 个公认 marker 基因
- 有亚型时列出亚型（如 Zone 1/2/3 肝细胞）
- 衰老时加入 `aging_note` 字段
- 标注 `source` 字段（文献引用）

#### 3b. `key_findings.yaml` — 关键发现

```yaml
findings:
  - finding: 衰老破坏肝细胞区域化(zonation)稳态
    evidence: |
      - snRNA-seq显示衰老肝脏中Zone 1和Zone 3基因表达边界模糊
      - 区域特异性代谢基因表达失调
    source: |
      - "Nikopoulou et al. 2023, Nature Aging (PMID: 37946043)"
    confidence: high
```

**编写规则**：
- 每条发现必须有 `evidence`（证据描述）和 `source`（文献引用）
- confidence 分级：high（多篇文献一致）/ medium（单篇）/ low（推断）
- 有争议的发现标注 `must_validate: True`

#### 3c. `gene_sets.yaml` — 基因集

```yaml
gene_sets:
  liver_aging_up:
    description: 衰老肝脏中上调的基因
    genes: [CDKN2A, CDKN1A, CLU, LCN2, CLEc7A, SAA1, ...]
    source: "Lin 2024 FASEB + Nikopoulou 2023 Nature Aging"
    confidence: high
```

**编写规则**：
- 每个基因集标注 `source` 和 `confidence`
- 包括：区域化 marker、衰老上调/下调、炎症免疫、SASP、线粒体、脂质代谢、ECM/纤维化、LSEC 衰老等
- 基因名按物种规范

### 阶段 4：构建测序方法文件

#### 4a. RNA 方法文件

```yaml
# liver_aging_key_findings.yaml — 每篇文献的详细发现
key_findings:
  - paper: "Lin et al. 2024, FASEB Journal (PMID: 38334462)"
    method: scRNA-seq (10x Genomics)
    species: "Mouse (C57BL/6)"
    sample_info: "Young vs Aged"
    key_results: |
      - LSEC假毛细血管化
      - HSC获得活化表型
      - 热量限制可逆转部分衰老变化
    cell_types_identified: [hepatocyte, LSEC, HSC, Kupffer cell, ...]
```

```yaml
# default_kb_method.yaml — 组织特异的分析流程参数
pipeline:
  qc:
    params:
      nFeature_RNA_min: 200
      nFeature_RNA_max: 6000
      percent_mt_max: 20  # 肝脏线粒体代谢旺盛，可放宽
  normalization:
    method: SCTransform v2
    conserve.memory: TRUE
  ...
```

#### 4b. ATAC 方法文件

```yaml
# liver_atac_key_findings.yaml
key_findings:
  - paper: "Nikopoulou et al. 2023, Nature Aging"
    method: "scATAC-seq (10x)"
    key_results: |
      - 衰老以区域依赖方式改变染色质可及性
      - Hnf4a, Foxa3, Hnf1 为关键 TF
    tf_motifs_aging:
      periportal: [Hnf4a, Foxa3, Hnf1, Cebp]
      pericentral: [Hnf4a, Foxa3, Hnf1, Srebp]
```

#### 4c. Spatial 方法文件

```yaml
# liver_spatial_key_findings.yaml
key_findings:
  - paper: "Nikopoulou et al. 2023, Nature Aging"
    method: "Visium (55um spots) + MERFISH"
    key_results: |
      - Zone 1: 线粒体功能下降
      - Zone 3: 脂滴累积
    zonal_markers:
      zone1: [CYP2F2, ASS1, ARG1, PCK1]
      zone3: [CYP2E1, GLUL, CYP1A2, AXIN2]
```

#### 4d. Bulk 方法文件

```yaml
# liver_bulk_key_findings.yaml
key_findings:
  - paper: "BMC Genomics 2015"
    method: "Bulk RNA-seq"
    key_results: |
      - 数千基因衰老差异表达
      - 炎症↑, 代谢↓, 昼夜节律↓
    liver_aging_markers_up: [LCN2, CLEc7A, SAA1, ...]
```

### 阶段 5：多物种同步

如果文献同时涉及人类和小鼠：

1. **先构建人类知识库**（更完整，文献更多）
2. **复制到小鼠目录**，转换基因名：
   - 人类：全大写（ALB, CYP3A4, CDKN2A）
   - 小鼠：首字母大写其余小写（Alb, Cyp3a11, Cdkn2a）
3. **生物学知识**：大部分共享，但 marker 基因名不同
4. **关键发现**：可完全共享
5. **基因集**：基因名需转换
6. **方法参数**：完全可共享

### 阶段 6：验证

```bash
# 1. YAML 语法检查
python -c "import yaml, glob; \
  for f in glob.glob('knowledge_base/{species}/{tissue}/{direction}/**/*.yaml', recursive=True): \
    yaml.safe_load(open(f))"

# 2. 搜索验证
search_knowledge(query="...", species=..., tissue=..., direction=...)
# 确保返回结果包含刚写入的文件
```

## 文件结构规范

```
knowledge_base/{species}/{tissue}/{direction}/
├── 01_生物学知识/
│   ├── biology_knowledge.yaml    ← 细胞类型 + marker + 亚型 + 衰老注释
│   ├── key_findings.yaml         ← 14+ 核心发现（文献索引）
│   └── gene_sets.yaml            ← 13+ 基因集（区域化/衰老/SASP/线粒体等）
├── 02_质控参数/                  ← 可选
│   └── scrna_qc.yaml
├── 03_测序方法/
│   ├── RNA/
│   │   ├── default_kb_method.yaml                ← 组织特有分析流程参数
│   │   └── {tissue}_aging_key_findings.yaml      ← scRNA-seq 文献详解
│   ├── ATAC/
│   │   └── {tissue}_atac_key_findings.yaml       ← 表观组文献
│   ├── spatial/
│   │   └── {tissue}_spatial_key_findings.yaml    ← 空间转录组文献
│   └── Bulk/
│       └── {tissue}_bulk_key_findings.yaml       ← Bulk RNA-seq 文献
└── index.yaml                    ← 知识库索引
```

## 五级目录路径约束（save_knowledge / kb_extract_from_paper 铁律）

知识库按 `{species}/{tissue}/{direction}/{kb_category}/{assay}` 五级目录落库，路径段有硬性校验（2026-08-15 实测）：

1. **species/tissue/direction 必须是单一值**：仅允许字母/数字/下划线/中文，≤64 字符
   - ❌ `human;mouse`（多物种综述常见）→ 校验拒绝 `路径段 'human;mouse' 非法`
   - ❌ `skeletal muscle, liver`、`aging/exercise`、`人；小鼠` → 同样拒绝
   - ✅ 多值字段拆分**取第一个合法段**：`human;mouse → human`、`aging/exercise → aging`
2. **kb_extract_from_paper 失败模式**（LLM 提炼自动入库工具）：
   - `ok:false` + written/rejected **都为空**且无 error 字段 → LLM 输出 JSON 数组元素不是 dict，被 `isinstance` 静默跳过 → 重试一次；仍失败则走手动兜底
   - rejected 报 `路径段 'human;mouse' 非法` → 多物种/多组织字段未清洗 → 工具已修复（2026-08-15 commit 53a0586e 增加 `_first_seg` 清洗）；旧版本/其他入库路径仍可能踩
   - 底层提炼模型输出格式不稳定（deepseek-v4-flash 偶发），**不要无限重试**
   - **快速诊断确认**（2026-08-15 实测）：grep `hermes_home/logs/agent.log` 与 `hermes_home/logs/errors.log` 中 `Tool kb_extract_from_paper` 记录——同日同文献多次相同输出（ok:false + 无 error + ~265 chars 短输出）即 LLM 解析问题，非文件/路径问题；`ok:true` 或含 error 字段才是其他故障。确认后立即切手动兜底，别再重试
3. **可靠兜底：手动 save_knowledge**（铁律 21 正规入库）：
   - 已确认 PDF 可读（如 summaries/ 已有摘要）时，直接基于摘要手动构造条目
   - **素材来源（2026-08-15 实测）**：`hermes_home/papers/summaries/<文件名>.md` 是 summarize_paper 的 9 项结构化摘要（思路/背景/问题/方法/结论等），可直接作为 save_knowledge content 的编写基础——本会话即据此为 1 篇综述产出 2 条有效条目（01_生物学知识 + 03_测序方法 各 1）
   - `save_knowledge(name, content, species=单一值, tissue=单一值, direction=单一值, kb_category, assay_type, evidence="DOI xxx | 标题 | PDF路径", verified="partially_verified", source="literature")`
   - **`assay_type` 必须小写**（`RNA`/`ATAC`/`spatial`/`bulk`）：传大写（如 `BULK`）会被系统规范化校验拒绝（2026-08-15 实测 `ok:false`），改小写重试即过——转录调控类知识用 `RNA` 与默认值一致
   - 逐字段验证 species/tissue/direction 均为合法单一段，写入后 `search_knowledge` 验证命中

## YAML 编写注意事项

### 常见错误
1. **括号问题**：`(PMID: 12345)` 在 YAML 中被解析为映射，必须用引号包起来
   - ❌ `source: Hepatology 2025 (PMID: 40622856)`
   - ✅ `source: "Hepatology 2025 (PMID: 40622856)"`
2. **冒号后空格**：`key: value` 的冒号后必须有空格
3. **多行字符串**：用 `|`（保留换行）或 `>`（折叠换行）
4. **列表缩进**：同一级别的 `- ` 必须对齐

### 引用格式
- 期刊论文：`"作者 et al. 年份, 期刊 (PMID: XXXXX)"`
- 有 PMID 的必须标注（方便溯源）
- 多篇引用用 `- ` 列表

## 相关技能
- `literature-param-extraction` — 从 PDF 提取生信参数（互补，焦点在 PDF 而非构建完整知识库）
- `create-bio-skill` — 创建生信分析 skill（不同领域，构建分析模板而非知识库）

## 参考文档
- `references/memomics-skill-gap-analysis-2026-07.md` — 286 skill × 5 用户角色覆盖度差距分析。含按角色/组学/优先级的三维评估，指导 skill 开发优先级决策。