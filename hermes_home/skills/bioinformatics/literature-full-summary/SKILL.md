---
category: Literature
name: literature-full-summary
description: 文献全文思路提炼（给人看的方向）：逐篇提取思路/背景/物种/组织/问题/解决方法/方法/结论/验证 9 项结构化摘要，写入文献库 summaries/ 并可跨会话查看。与 literature-param-extraction 分工：本 skill 产出人类阅读的论文解读；参数/生物知识/生信知识（给 AI 调用）走 kb_extract_from_paper。
when_to_use: "[literature-full-summary] 文献全文思路提炼。触发场景：用户要求'总结/解读/提炼这篇文章的思路'、'这篇文章讲了什么'、文献库一键全文提炼。"
trigger:
  when:
    - 用户要求总结/解读某篇已导入文献库的论文
    - 用户要求"全文提炼/一键提炼"文献库里的文章
    - 用户想了解某篇文献的研究思路、背景、问题与结论
  not_when:
    - 只是提取生信参数/知识库条目（那走 kb_extract_from_paper / literature-param-extraction）
    - 普通聊天不涉及文献
  rules:
    - "9 项摘要必须逐项给出，缺项写'未提及'，禁止编造"
    - "物种/组织必须与原文一致（human/mouse/rat...；skeletal_muscle/liver...）"
    - "摘要写入 hermes_home/papers/summaries/<文件名>.md 并标记 summary_done"
    - "执行时直接调用 summarize_paper 工具（工具内已实现本 9 项模板与落盘）；禁止反复 skill_view 后手动复述模板"
    - "skill_view 本 skill 最多一次；看到模板后立刻调用 summarize_paper"
---

# 文献全文思路提炼 Skill（给人看的方向）

## 九个必答问题（结构化摘要模板）

对每一篇文献，按以下 9 项逐项提炼（中文回答，每项 2-6 句，忠实原文，禁止编造）：

1. **思路 (idea)**：作者的核心想法/研究切入点是什么？一句话 + 展开
2. **背景 (background)**：研究领域现状与空白，为什么要做这个研究
3. **物种 (species)**：研究对象物种（human/mouse/rat/...），多物种分别列出
4. **组织 (tissue)**：研究组织/细胞类型（skeletal_muscle/liver/...）
5. **问题 (problem)**：本文要回答的具体科学问题
6. **怎么解决 (solution)**：作者如何设计实验/分析来回答（分组/干预/队列设计）
7. **方法 (methods)**：关键技术/算法/统计方法（高通量测序类型、软件、阈值）
8. **结论 (conclusion)**：主要发现与结论
9. **怎么验证 (validation)**：作者如何验证结论（独立队列/实验验证/交叉方法）

## 两个方向的分工（重要）

- **本 skill（给人看）**：上面 9 项 = 论文解读，供用户阅读，存入 `hermes_home/papers/summaries/`
- **kb_extract_from_paper（给 AI 调用）**：结构化知识提取（批O 2026-08-16 升级）——
  - 生物学知识（结论/基因marker/细胞类型/通路/类器官培养条件/化合物化学信息）→ `01_生物学知识`
  - 生信知识（测序方法/分析流程/软件包含版本/关键参数/QC阈值/参考基因组/数据库）→ `03_测序方法`
  - 质控阈值 → `02_质控参数`
  - 人读版落盘 `hermes_home/papers/knowledge/<文件名>.md`，机读 JSON 存文献库索引（WebUI 文献详情 🧠知识 标签）

两个方向互相独立：一篇文章可以只有全文摘要、只有知识库条目、或两者都有。状态标记：`summary_done`（全文已提炼）与 `kb_done`/`knowledge_done`（已入库）互不干扰。

## 引用（批O 2026-08-16）

文献详情「📎 引用」标签提供 GB/T 7714（顺序编码制/著者-出版年制）、APA 7、NLM、MLA、
BibTeX、RIS 全套专业格式；缺卷/期/页码时点「🛠 补全元数据」从 Crossref 拉取。
「⬇ 导出引用」可整库导出 .bib/.ris/GB/T 7714 文本。

## 使用方式

- **执行 = 调用 `summarize_paper(file_or_title=...)`**（本 skill 的 9 项模板已内置在该工具里，含 OCR 兜底与落盘标记）。不要手工逐项撰写。
- 批量：`summarize_all_papers()` 只处理未提炼（summary_done=false）的文章。
- 本 skill 的作用是让 agent 理解"给人看的方向"的分工与 9 项定义；真正的执行全部走工具。
