# 模式 D — 缺口论证与发文定位 recipe

> 来源：2026-10-02 会话（科研 AI agent 领域定位报告）。触发背景：用户问「我们这个 MemOmics 要发文章
> 的话，出发点是什么？」→ 我按模式 B/C 出了一份三 Gap「真空白」定位 → **L2 完整辩论裁决
> `need_more_info`（置信度低，可证伪与可测仅 3/7）** → 裁判要求补做定向系统检索 →
> 检索 496 条命中后发现 **G2/G3 并非真空白**，三 Gap 全部改判 → 定位与投稿层级同步降档。

---

## 0. 一句话教训

**「缺口」是本次任务里唯一会被审稿人直接证伪的东西。** 其余部分（竞品卡、数字、引用）都只是劳动量，
只有空白判定是**风险点**。所以：先证伪空白，再写任何一句定位。

---

## 1. 第一步：术语存在性检查（5 分钟，防最大的一枪）

你打算提出的概念名，先搜它自己。

```python
# 例：概念名 = "evidence-gated scientific agent"
probes = ['"evidence-gated" AND agent',
          '"evidence gating"',
          '"evidence-grounded" AND ("scientific agent" OR "AI scientist")',
          '"conclusion-level" AND (agent OR "language model")']
```
本次结果：`evidence-gated` 已被 *Evidence-Gated Memory Writing for Personalized LLM Agents*
（ICIPAI 2026, `10.1109/icipai70034.2026.11605481`）使用，另有 `Weft`、`Post-Reward Agent
Architecture` 等多篇在用。**结论：术语不可声称首创，只能声称"用于 X 场景 + 耦合进闭环"。**

---

## 2. 第二步：缺口定向系统检索（六组检索式，实测模板）

**要点：用缺口自己的词汇，不要用领域词汇。** 领域词（"scientific agent"、"multi-omics"）召回的是
整个赛道；缺口词（"evidence-gated"、"claim verification"、"auditability"）才能召回到最近邻。

```python
GROUPS = {
 "G2a 证据门控/证据接地": ['"evidence-gated" AND agent',
                        '"evidence grounding" AND (agent OR "language model")',
                        '"grounded" AND ("scientific agent" OR "AI scientist")'],
 "G2b 结论可信度/主张核验": ['"claim verification" AND ("language model" OR agent)',
                         '"conclusion credibility"',
                         '"unsupported claim" AND ("language model" OR agent)'],
 "G2c 溯源/可审计": ['provenance AND ("scientific agent" OR "AI scientist" OR "language model agent")',
                   'auditability AND ("AI scientist" OR "scientific agent")',
                   '"audit trail" AND ("language model" OR agent) AND science'],
 "G2d 不确定性校准/自我批判": ['"uncertainty calibration" AND ("language model" OR agent)',
                          '"self-critique" OR "self-verification" AND ("scientific agent" OR "AI scientist")',
                          '"multi-agent debate" AND (verification OR factuality)'],
 "G2e 多组学 agent": ['"multi-omics" AND agent AND ("language model" OR LLM OR "AI agent")',
                   '("cross-omics" OR "multi-omic") AND ("language model" OR agent)'],
 "G2f 自进化/知识沉淀 agent": ['("self-evolving" OR "self-improving") AND ("scientific agent" OR "AI scientist")',
                          '("memory" OR "experience reuse" OR "knowledge accumulation") AND ("scientific agent")'],
}
```

**三源并发（本机全部可通，无需 key）：**

| 源 | 端点 | 备注 |
|---|---|---|
| Europe PMC | `https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=<q> AND (FIRST_PDATE:[2023-01-01 TO 2026-12-31])&format=json&pageSize=25&resultType=core` | 给 DOI/PMID/PMCID + 被引数 `citedByCount` |
| arXiv | `http://export.arxiv.org/api/query?search_query=all:"<q>"&max_results=20&sortBy=relevance` | 要新工作、预印本 |
| OpenAlex | `https://api.openalex.org/works?search=<q>&filter=from_publication_date:2023-01-01&per-page=25&mailto=<你的邮箱>` | 给 `cited_by_count` + venue，覆盖最广 |

- 每组 2–3 条式 → 六组共 ~15 条查询 × 3 源。**每条之间 `time.sleep(0.4)`**，别打太密。
- 命中量级参考：本次 496 条去重。若某组 0 命中，那是**信号**（该子问题真的没人做），要单独记下来。

---

## 3. 第三步：分层过滤（把 496 条压成 42 条真最近邻）

全量命中会被通用综述淹没（本次 top-cited 全是"多组学整合"综述，与 agent 无关）。两级标题正则：

```python
AG  = re.compile(r"\b(agent|agents|agentic|AI scientist|scientific agent|LLM agent)\b", re.I)
CRE = re.compile(r"(credibilit|trustworth|verif|provenance|audit|calibrat|factualit|hallucinat|"
                 r"evidence[- ]ground|evidence[- ]gat|reproduc|self[- ]correct|self[- ]critique|traceab)", re.I)

near   = [h for h in hits if AG.search(h["title"]) and CRE.search(h["title"])]      # 真最近邻
mo     = [h for h in hits if re.search(r"multi[- ]?omic|cross[- ]?omic", h["title"], re.I) and AG.search(h["title"])]
```
本次：`near` = **42 条**，`mo`（多组学×agent）= **5 条**。

**看结果的方式**：不要按被引数排序就下结论。要问三件事——
① 类别是否已存在（G1：多组学 agent 2023 年就有）？
② 你的术语是否已被用（G2）？
③ 组合是否已被做过（G3：证据门控+自改进已有）？

### 本次决定性最近邻（可作为"该领域已被占位"的参照系）

| 先例 | 年份 | 命中的缺口 |
|---|---|---|
| Evidence-Gated Memory Writing for Personalized LLM Agents `10.1109/icipai70034.2026.11605481` | 2026 | 术语 G2 |
| MetaClaw: an auditable AI agent for end-to-end…multi-omics analysis `10.64898/2026.07.21.739769` | 2026 | **G1+G2 同命中** |
| Audit-Closed AI Scientist Protocol `10.2139/ssrn.7338438` | 2026 | G2 |
| RegenHarness: Evidence-Gated Recursive Self-Improvement `arXiv:2609.27612` | 2026 | **G2+G3** |
| An AI Agent for Fully Automated Multi-omic Analyses | 2023 | G1（类别早已存在） |
| BIOGEN: evidence-grounded multi-agent…transcriptomic `10.3389/fbinf.2026.1846404` | 2026 | G1+G2（重合度最高） |
| Debating Truth: Debate-driven Claim Verification `10.1145/3774904.3792993` | 2026 | G2（辩论机制非首创） |
| Uncertainty Calibration for Tool-Using Language Agents `10.18653/v1/2024.findings-emnlp.978` | 2024 | G2 |
| Multi-agent…credibility-based scoring in fact-checking `10.1038/s41598-026-41862-z` | 2026 | G2 |
| Step-Level Self-Critique and Self-Training `10.1145/3726302.3729965` | 2025 | G3 |
| FUTURE-AI consensus guideline `10.1136/bmj-2024-081554`（633 引） | 2025 | 可信 AI 已是建制议题 |

---

## 4. 第四步：四级判定 + 措辞纪律

| 判定 | 措辞模板 |
|---|---|
| 真空白 | 「据本次检索（N 条去重命中，M 条标题同时含 agent×可信度词）未见…」 |
| 局部空白 | 「X 类工作已存在（举 2–3 篇），但**跨模态长链条的状态契约**未见报道」 |
| 未耦合 | 「各要素均有先例（举篇），未见**同时耦合进同一闭环**者」 |
| 已有同构 | 改写角度为评测贡献 / 复现研究 / 协议文；**不要硬撑** |

**禁用词表**（写进交付文档的措辞纪律段，让用户也能据此自查）：
真空白 · 首次提出 · 首个 · 尚无任何工作 · 一等公民化空白。

**替换为**：在 N 篇精读样本与 M 条系统检索命中中未见 / 据本次检索范围内未见 / 未见同时耦合者。

---

## 5. 第五步：四轴差异表（模板）

```markdown
| 系统 | ① 本家核心机制 | ② 对抗/审查 | ③ 沉淀/复用 | ④ 跨域/跨模态链长 | 判定 |
|---|:--:|:--:|:--:|:--:|---|
| <竞品 A> | ● | ○ | ○（仅抽象） | ○ | 差异在②③④ |
| <竞品 B> | ◐（仅观点） | ◐（仅观点） | ○ | ○ | 差异在"观点→可运行实现" |
| **本家** | ● | ● | ● | **◐→●（待实测）** | 四轴同时耦合 |
```

图例：`●` 完整实现 / `◐` 部分或仅观点 / `○` 未涉及。
**铁律**：本家任何一轴若只有设计没有实测，**必须标 ◐ 并写「待实测」**，同时进 Limitations。
本次靠此表发现四轴单看**全部**有先例 → 可辩护差异只剩「同时耦合 + 结论层指标协议」。

---

## 6. 第六步：定位报告交付组合（五件，缺一不可）

| # | 交付物 | 关键要求 |
|---|---|---|
| 1 | 定位正文 `.md` 母本 | **必须含「裁决章节」**：辩论七维打分 + 必做项 + 降档建议。只写在聊天里会在下一轮压缩后丢失 |
| 2 | 竞品卡 + `evidence.csv` + `references.bib` | 见模式 C；引用库含最近邻，供审稿人核对 |
| 3 | **检索附录** | 检索式（分源）+ 各组命中数 + **反例清单**。审稿人最想看、最容易被自己省掉 |
| 4 | 核心图 2–3 张 | 赛道体量/漏斗 · 定位矩阵（路由×缺口）· 能力 vs 可信度散点。图内文字全英文 |
| 5 | HTML 展示页 + DOCX | 见模式 B4 与 `docx-generation`；HTML 用 base64 内嵌图保持自包含 |

---

## 7. 第七步：降档判据（随证据走，不随愿望走）

```
无 pilot 实测 + 无指标信度(IRR) + 无增益曲线
        ↓
只能投 protocol / perspective / registered report 档
（本次：Nature Methods/NBT/NCS → Bioinformatics / Briefings in Bioinformatics）

升级条件必须写成可检验句：
「拿到跨组学 pilot 且指标双人 IRR≥0.7 且与现有 benchmark 收敛效度报告」
```

**诚实清单（必须进 Limitations）**：全文覆盖率、PDF 覆盖率、哪些结论无实测、
检索只覆盖了哪些源（未覆盖 Scopus/WoS/DBLP/OpenReview 要明说，避免把"我没搜到"写成"不存在"）。

---

## 8. 与门控辩论的关系

- 定位报告属**高影响产物** → 门控会要求 L2 完整辩论（场景通常判为 `writing`）。
- 辩论 topic/context **必须写清"问题类型 + 关键约束"**（本次：方法学定位论证 + 目标期刊层级 +
  诚实边界 + 不得编数据），否则场景判定会漂。
- **裁决出来要立刻落地**：裁判的 `next_actions` 里 `owner=ai` 且带 `blocks` 的项，
  会硬拦后续产物类工具。本次的顺序是：**先补检索（必做项 #1）→ 再生成差异表（#3）→ 最后才重出交付物**。
- 裁决结果与评分维度要**写回交付文档正文**，不能只留在对话里。