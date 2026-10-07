---
category: Literature
name: kb-evidence-extraction
description: >
  把文献库文献提炼成带证据链的知识库条目（kb-evidence-v1 标准）。生物学结论按 L0-L3
  可信度分级，每条带验证方式与原文位置；测序方法/实验方法/参数/流程类不做可信度分级，
  只需标注文章来源。入库走 save_knowledge 铁轨（evidence 必填，unverified 拒收）。
  触发：提炼文献进知识库 / 补充知识库 / 评估知识可信度 / 证据分级。
trigger:
  when:
    - 用户要求"把这篇/这些文献提炼进知识库"、"提取知识/参数进知识库"
    - 用户要求"构建/补充知识库（带证据链）"、"知识库搭建"
    - 需要评估知识库条目可信度（L0-L3）时
    - 一键全流程（翻译+提炼+证据链知识+双语锚定）
  not_when:
    - 用户只要论文解读/9 项摘要（那走 literature-full-summary / summarize_paper）
    - 只是提取生信参数清单浏览而不入库（那走 literature-param-extraction）
  rules:
    - "生物学结论必须逐条判 evidence_level（L0-L3），并给出 validation（验证方式+图号）与 locator（章节/位置）"
    - "写实判定：找不到验证描述只能给 L0/L1，禁止拔高级别"
    - "方法/参数/流程类不做可信度分级，但每条必须带来源（DOI/PMID）"
    - "入库必须过 save_knowledge 铁轨：evidence 必填，verified=unverified 拒收"
    - "执行走 kb_extract_from_paper 工具（schema 与分级已内置），禁止手工编造级别"
---

# 知识库证据链提炼 Skill（kb-evidence-v1）

## 干什么

把文献库里的文献提炼成**带证据链**的知识库条目，让知识库里每条生物学结论的可信度一眼可见、可溯源。

- 执行工具：`kb_extract_from_paper(file_or_title)`（单篇）/ WebUI 文献库「🧠 一键知识提取」（批量）/「⚡ 一键全流程」（翻译+提炼+知识+双语锚定四合一）
- 落盘：人读版 `hermes_home/papers/knowledge/<文件名>.md`；机读条目 `knowledge_base/五级目录/*.yaml`（顶层带 `evidence_chain` 字段）

## 证据链分级标准（核心，写实）

**只对生物学知识（结论/发现）分级。方法类（测序方法/实验方法/分析流程/软件包/参数/质控/数据库）不做可信度分级，只需标注文章来源（evidence 字段自动带 DOI+标题）。**

| 级别 | 含义 | 判定依据（写实，缺一不可） |
|------|------|---------------------------|
| **L0** 无来源 | 推测/常识性陈述，无文献支撑 | 原文没有给出处，或只是作者的推测性语句 |
| **L1** 有来源未验证 | 有文献来源，但原文**未做实验验证** | 综述转述、纯生信/组学分析发现（仅计算证据）、作者声称但未验证。一定程度可信 |
| **L2** 实验验证 | 原文做了**湿实验验证** | 原文明确描述了实验验证：免疫荧光(IF)/免疫组化(IHC)/Western blot/qPCR/ELISA/流式/细胞实验/动物模型/类器官 等。validation 字段必须写出验证方式+图号（如「免疫荧光（Fig.3B）」）。很可信 |
| **L3** 临床级 | 经**大量验证或临床实验/临床队列**验证 | 原文有临床实验/临床试验/患者队列验证（clinical trial / patient cohort / prospective…）。非常可信 |

### 判定纪律（防虚高，后端有硬性校验）

1. 声称 **L2** 但 validation 为空、且结论文本不含湿实验关键词 → 后端自动降级 **L1**
2. 声称 **L3** 但无临床/队列关键词 → 后端自动降级 **L2**
3. 同一结论合并多处证据时取**较低**级别，validation 合并写全部依据
4. 宁低勿高：级别是给下游 AI 做取舍的，虚高的级别比保守的级别危害大

## YAML 条目形状（知识库/图谱弹窗里直接可见）

```yaml
type: kb_entry
name: paper_bio_xxx
species: Homo_sapiens
tissue: skeletal_muscle
direction: aging
kb_category: 01_生物学知识
verified: partially_verified
evidence: "DOI 10.xxxx | 标题 | 路径"          # 来源溯源（铁轨必填）
evidence_chain:                                # 2026-10-07 新增顶层字段
  standard: kb-evidence-v1
  max_level: L2
  graded_conclusions: 5
  level_distribution: {L0: 0, L1: 2, L2: 3, L3: 0}
content: |
  ## 结论（证据链分级：L0 无来源 / L1 有来源未验证 / L2 实验验证 / L3 临床级）
  - **[L2]** 衰老骨骼肌中慢性炎症通路显著上调　（验证：免疫荧光（Fig.3B）｜ 位置：Results 第2段）
  - **[L1]** XX 基因可能是衰老驱动因子　（纯组学相关性发现，未做湿实验）
```

## 与其他三个文献 skill 的分工（合并要点，避免混淆）

| Skill | 方向 | 产物 |
|-------|------|------|
| literature-full-summary | 给人看 | 9 项摘要（思路/背景/问题/方法/结论/验证）→ papers/summaries/ |
| **本 skill** | 给 AI 用 + 可信度 | 结构化知识 + **L0-L3 证据链** → knowledge_base 五级目录 |
| literature-param-extraction | 参数聚焦 | 参数值 + source + confidence + usage_rate（本文献多篇对比时用） |
| knowledge-base-curation | 建库流程 | 从零构建 物种×组织×方向 知识库的端到端流程 |

- 本 skill 与 literature-param-extraction 互补：参数对比/使用率统计看后者；单篇快速入库 + 证据链看本 skill。
- 本 skill 入库的条目可直接被 knowledge-base-curation 的建库流程复用。
- 生信文献的生物学结论也要写 01_生物学知识（沿用 curation 铁律），且现在必须带证据链级别。

## 翻译与提速（配套能力）

- 翻译：`translate_paper`（段落级编号直译，中英严格 1:1，6 路并发 + 断点续译 + 幂等跳过；译完自动重建双语对照缓存）
- 双语对标：`build_bilingual` 句级锚定——WebUI 文献详情「⇄ 对照」里**点译文任意一句即框出原文 PDF 对应句**（实测命中率 100%）
- 提速：篇级并发 2 路（`MEMOMICS_LIT_PAPER_WORKERS` 可调）× 块级并发 6 路（`MEMOMICS_LIT_CHUNK_WORKERS`）；一键全流程管线 `process_paper_full` / `/api/literature/process-all`（幂等跳过已完成步骤）

## 查看证据链

1. **知识库 → 图谱视图**：双击条目节点 → 弹窗顶部「⛓ 证据链」徽章行（L3 金 / L2 绿 / L1 蓝 / L0 灰 + 本篇最高级）
2. **文献库 → 📄 详情 → 🧠 知识**：结论列表逐条带级别徽章 + 验证方式 + 原文位置
3. **检索**：`search_knowledge` 命中条目的 content 里就有 [Lx] 标记，AI 引用时直接知道可信度

## 铁律

- 入库必须过 `save_knowledge`（evidence 必填、unverified 拒收），不得绕过铁轨手写 YAML
- 多值物种/组织字段拆单一合法段（`human;mouse` → 取 `human`），assay_type 小写词汇表（RNA/ATAC/spatial/bulk）
- 批量任务失败不硬重试：先看 rejected 原因（路径段非法/LLM 格式问题）再决定
