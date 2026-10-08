# 先例撞车强度分级（Precedent collision strength）— 模式 D 配套配方

> 来源：2026-10-02 MemOmics 发文定位会话。L2 裁决把「先例只有题名年份，无法按证据契约作撞车判断」
> 列为**第一硬阻断项**（`next_actions[0].owner = ai`），补齐后得出的结论**实质改变了定位**。
> 适用：任何「声称空白 / 声称首次提出某概念 / 声称与某工作不同」的场合。

---

## 0. 一句话判据

**撞车强度 = 同域程度 × 是否同行评议。**

只比对标题会同时犯两个相反的错：把预印本当正式占位（自我否定过度），
以及把正式发表的同域工作当"仅是相关"（自我肯定过度）。

---

## 1. 为什么必须记录载体类型

LLM 手写 / 聚合站抓来的先例清单通常只有 `title + year`，而这**不足以判定撞车**：

| 载体 | 学术分量 | 处理 |
|---|---|---|
| 正式期刊 / 会议论文集 | 建制化占位 | **必须逐字 diff**，剩余空间要落在它未覆盖的维度 |
| bioRxiv / medRxiv 预印本 | 未评议 | 撞车成立但**强度下调**；只能作"该方向已被多人同时探索"的旁证 |
| arXiv 预印本 | 未评议 | 同上；域外（如机器人域）再降一档 |
| Zenodo / ResearchGate / Kaggle / SSRN 自存档 | 非正式 | **不作为占位证据**，仅作术语出现过的旁证 |
| 学会共识指南（BMJ/Nature 指南类） | 强，但**层级不同** | 占的是治理/报告层，通常**不占**执行层/方法层 |

---

## 2. 本会话实测：术语占用 ≠ 概念在同行评议中确立

`evidence-gated` 一词的检索命中 11+ 条，其中：

- **仅 1 条**是正式载体（IEEE ICIPAI 会议短论文：*Evidence-Gated Memory Writing for
  Personalized LLM Agents*, `10.1109/icipai70034.2026.11605481`；另有 ResearchGate 自存档版
  `10.13140/rg.2.2.10244.69767`），且占的是**"个人化 agent 的记忆写入"**环节，不是科研分析长链条；
- 其余全部落在 `10.5281/zenodo.*` / `10.48550/arxiv.*` / `10.13140/rg.2.*` / Kaggle 自存档。

⇒ 两条**方向相反**的正确陈述：
- ✅「该术语已被使用，**不可声称提出该概念**」（保守，防审稿人第一枪）
- ✅「该术语在**同行评议的生信执行层**尚未确立」（未被建制化占位）

两者可以同时写进同一份定位报告，**不要只写其中一条**。

---

## 3. 本会话实测的六个关键先例（可直接引用的元数据）

| # | 先例 | 年 | 载体 | DOI / PMID | 同行评议 | 占位的概念 | 威胁 |
|---|---|---|---|---|---|---|---|
| 1 | Evidence-Gated Memory Writing for Personalized LLM Agents | 2026 | IEEE 会议论文集 (ICIPAI) | `10.1109/icipai70034.2026.11605481` | 会议短论文（弱） | "evidence-gated" 术语，限**记忆写入**环节 | 术语层高 / 场景层低 |
| 2 | BIOGEN: evidence-grounded multi-agent reasoning for transcriptomic interpretation (AMR) | 2026 | Front Bioinform | `10.3389/fbinf.2026.1846404` / PMID 42292667 | ✅ 强 | evidence-grounded + 多 agent + **单转录组** | **最高（同域真撞）** |
| 3 | MetaClaw: an auditable AI agent for end-to-end multi-omics analysis | 2026 | **bioRxiv** | `10.64898/2026.07.21.739769` | ❌ 预印本 | auditable × multi-omics 同时命中 | 中（未建制化） |
| 4 | RegenHarness: Evidence-Gated Recursive Self-Improvement | 2026 | **arXiv** | arXiv 2609.27612 | ❌ 预印本 | 证据门控 + 递归自改进（**机器人域**） | 低（域外+预印本） |
| 5 | FUTURE-AI: international consensus guideline for trustworthy AI in healthcare | 2025 | **BMJ** | `10.1136/bmj-2024-081554` / PMID 39909534 | ✅ 强 | 可信 AI 的**治理/报告层**共识 | 中高但**非同层** |
| 6 | The next paradigm in bioinformatics: multi-agent systems + foundational models | 2026 | Brief Bioinform | `10.1093/bib/bbag245` | ✅ 强 | 三支柱并列，**点名 sequential statistical testing 缺失但未操作化** | 高（叙事被占，**停留在应然**） |

**差额写法（可直接抄）**：同域最强撞车（#2）覆盖"证据接地 + 多 agent + 转录组解释"，
剩余空间必须落在它**没有**的维度上 —— 跨组学长链条（ATAC×RNA×空间）、**结论层**指标
（它评的是解释正确性，不是结论产出）、知识沉淀复用率。

---

## 4. 四步操作规程

1. **捞元数据**：用**缺口自己的词汇**（不是领域词汇）在 Europe PMC REST + arXiv API + OpenAlex
   各跑一遍，命中落盘 JSON（不要边搜边判断）。
2. **补 DOI/PMID + 载体**：标题命中后用 `search_papers` / Crossref 补
   `doi / pmid / journal / year`，并**从 `journal` 字段判定载体类型**（bioRxiv/arXiv/Zenodo/ResearchGate
   出现即预印本或自存档）。
3. **逐条打两列**：`同行评议` ✔/❌ 与 `撞车强度`（同域程度 × 是否评议）。
4. **出「先例逐字差异表」**：列为
   `先例 | 年 | 载体 | DOI/PMID | 同行评议 | 逐字占位的概念 | 对本文威胁 | 剩余空间`，
   并配一张「逐条 delta」表（维度 × 各先例是否有 × 本文剩余空间）。

---

## 5. ⛔ 三条禁令

- **不要用预印本撞车当正式占位证据**（会把自己否掉）；
- **也不要因为预印本多就宣布概念空白**（会挨审稿人第一枪）；
- **不要让「DOI 补齐」被误读成"置信度上调"** —— 本步解决的是**已知性**，不解决**可证伪性**。
  本会话补齐 DOI 后，裁决的 `可证伪与可测` 一项**仍是 3/7**，因为 IRR 与四轴消融两个缺口原封不动。
  **诚实清单必须照写**：三维指标无 Krippendorff α / ICC、四轴消融无实测 Δ 与 CI、
  目标刊是否设 registered report 栏目未确认、结论层 ground truth 来源未定（有自我验证循环风险）。

---

## 6. 与裁决流程的接口

L2 裁决的 `next_actions[]` 常见首条就是「锁定先例 DOI/PMID 与逐字定义」，带
`owner = ai`、`blocks = ["不得声称方法学空白或概念创新"]`。收到即照本文件执行；
`owner = user` 的行动（如独立盲编码者做 IRR）**不能由 AI 代做**，只能如实转达并等用户安排。