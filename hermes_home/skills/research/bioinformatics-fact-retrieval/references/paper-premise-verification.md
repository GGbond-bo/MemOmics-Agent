# 用户前提核验：把「是不是就是 X？」核到原文（2026-10-04 实测，Biomni）

## 触发场景

用户**带着一个来自别处的心智模型**来求确认，表面是 yes/no，实质是「请核原文」：

- 「那我好奇，**2500 篇论文整理出来的东西，是不是就是它的 skill 呢？**我用过 biomni，
  它就是典型的触发对应的 skill，然后调用里面的工具，然后完成任务。是不是？」
- 同类句式：「XX 是不是就是 YY？」「我用过它，它就是先 A 再 B，对吧？」「它是不是靠提示词？」

⚠️ 这类问句比普通提问**更危险**：用户自己用过那个工具 ⇒ 他有强直觉，我若顺着点头就把错
概念固化进后续讨论。**纠正必须给他能自己复核的原文**，否则等于用我的权威压他的经验。

## 铁律（顺序不可颠倒）

1. ⛔ **不顺着用户假设点头**。先核原文，再表态；结论可以是"不完全是 / 恰恰相反"。
2. **先定位前提所依赖的具体数字与术语**，逐个在全文里做命中探针 ——
   **命中次数本身就是证据**。本例：`skill` 在 88 页全文里**只 1 次**，且落在 Discussion 的
   "coding **skills**"（编程技能），⇒ 它压根不是架构概念。
   ```bash
   python scripts/pdf_probe.py "E:/文献/AI/agent/literature/Biomni.pdf" \
     --out results/<sid>/data/Biomni_fulltext.txt \
     --kw "2,500" "knowledge base" "skill" "retrieval" "action space" --w 1200
   ```
   实测命中：`2,500` = 1 · `knowledge base` = 1（还在参考文献区，非概念）· `skill(s)` = 1 ·
   `retriev*` = 27 · `action space` = 9。
3. **引用逐字原句 + 标明出处段落**（Abstract / 图注 / Methods 小节），不自造转述。
4. **给「用户词汇 → 论文实际概念」映射表**，并用一句话收束；若用户在评估我们自己的平台
   （他多半想迁移经验），补一张**与本平台设计对照表**。
5. **论文内部口径不一致要主动自报**，不要替它抹平。

## 本例证据链（可直接照抄的原文锚点）

| 出处 | 逐字原文（关键片段） |
|---|---|
| Abstract | "...a generalist agentic architecture that integrates LLM reasoning with retrieval-augmented planning and code-based execution, enabling it to dynamically compose and carry out complex biomedical workflows – **entirely without relying on predefined templates or rigid task flows**." |
| Figure 1a 图注 | "Actions necessary to conduct biomedical research were **extracted from 2,500 recent bioRxiv publications across 25 biomedical subfields** using an AI-driven discovery agent. Extracted actions were rigorously validated and curated by human experts, resulting in the integration of **105 biomedical software tools, 150 specialized biological tools** (including wet-lab protocols, AI-driven predictive models, and domain-specific know-how), and **59 comprehensive biomedical databases**." |
| Methods · *Action Discovery from Literature* | "100 recent publications from the year 2024 at biorxiv Were collected ... a specialized prompt guided an LLM through each chunk to explicitly identify and extract **three categories of actionable insights: tasks, software, and databases**." |
| Methods · *Implementing the Biomni Environment* | "narrowed down to approximately **1,900 commonly recurring tasks**. These tasks were further **manually reviewed to eliminate redundancy and exclude tasks that are trivial or easily implementable through simple code** ... Human scientists then collaborated with software engineering agents ... Every tool underwent rigorous validation, requiring a clearly defined test case that it successfully passed. This stringent process culminated in a curated collection of **150 specialized tools**." |
| Methods · *Biomni-A1* | "built upon the **CodeAct** framework ... the agent first uses a **retrieval system** ... a **prompt-based retriever**，powered by a separate LLM, where the agent dynamically selects the most relevant functions, datasets, and software libraries from available resources. During execution, the LLM **generates code, executes it** in a coding environment (Python, R, or Bash), and returns the resulting observations to inform subsequent reasoning." |
| Discussion | "in the action discovery agent, our decision to prioritize the most recent literature makes the agent appear timely, but **risks overlooking foundational concepts and techniques that have faded from current discourse**" |

## 本案结论形状（被接受的四段式）

1. **开门见山否定**：「不完全是——你描述的是『触发 skill』，而 Biomni 恰恰是**反着设计**的。」
2. **2500 篇被榨出来的不是 skill，是"能力清单"** —— AI 抽当 tasks/software/databases →
   人工去冗、剔除"简单代码就能做"的 → 落成 **Biomni-E1 环境 = 150 专用工具 + 105 软件 + 59 数据库（314 个资源）**（配 markdown 表）。
3. **运行时确有"检索→调用"**（用户感觉到的"触发"= `prompt-based retriever`），
   但**被检索出的单位是单个工具/数据库，不是打包好的流程**；配一张 CodeAct 循环 Mermaid
   （计划 → 检索器挑资源 → LLM 写代码 → 容器执行 → observation 回灌 → 收敛/迭代）。
4. **对照表收束**（用户很可能在对比我们自己的平台）：

| | Biomni | MemOmics（我们） |
|---|---|---|
| 沉淀单位 | 单个工具/数据库（能力） | skill（流程 + 参数规范 + 审查标准） |
| 工作流 | 每次现场用代码拼 | 预先封装，触发后按步骤跑 |
| 优势 | 泛化强、没见过的问题也能拼 | 稳定、可复现、参数有出处 |
| 代价 | 每次重新发明流程，一致性靠模型 | 覆盖不到的场景就没有 skill |

一句话收束："**Biomni 把论文榨成工具箱，把『怎么用』交给 LLM 每次现想；我们把经验榨成菜谱。**"

## 口径不一致（必须自报，不许替它圆）

正文/图 1 图注说 **2,500 篇 bioRxiv（25 个亚领域）**；Methods 写的是初始迭代
**"2024 年 100 篇"**。两者不矛盾（小样本起步逐步扩量），但表述口径不同 ⇒
交付里用一行 italic 提醒，别假装只有一个数字。

## 可复用清单

- 全文必须**落盘成 txt 再 grep**（88 页 / 166,776 字符；pymupdf 直接抽），
  只在内存里 grep 会反复重抽浪费轮次。
- 探针关键词**取用户前提里出现的那几个词/数字**（本例：`2,500`、`skill`、`knowledge base`），
  外加论文自己的核心架构词（`action space`、`retrieval`）作为对照。
- 引用层级别忘标：本案全部引文都到了**全文层**（读过正文明文），交付时可放心引数字。