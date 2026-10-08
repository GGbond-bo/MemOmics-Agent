# 深读卡小批（N=5）· 2026-10-08 · 生信/化学 AI agent「综述 + 系统」混合批

同一文件的姊妹批（iDesignGPT / SDL 综述 / Co-Scientist / MetaChat / AAI+FL）见
`deep-card-small-batch-and-verification-gates.md`（若缺失，则以本文件为准的配方照做）。

## 1. 批次清单（n = 19–23，4 篇综述/观点 + 1 篇真实系统）

| n | PMCID | 题目（简） | 刊/年 | DOI | 类型 | 一句话架构 |
|---|-------|-----------|-------|-----|------|-----------|
| 19 | PMC11739813 | Review of LLMs & autonomous agents in **chemistry** | Chem Sci 2025 | 10.1039/d4sc03921a | 综述 | CoALA 式：智能体 = 中央程序 + agent modules（memory/planning/reasoning/profiling）+ perception + tools；决策三步 proposal→evaluation→selection |
| 20 | PMC12602188 | Rise & potential of LLM agents in **bioinformatics/biomedicine** | BIB 2025 | 10.1093/bib/bbaf601 | 综述 | 四组件（planning/perception/action/memory）+ 四技术（RAG/工具/多模态/持续学习）+ 三协作模式（单/多[集中·去中心·层级]/人机） |
| 21 | PMC13017847 | LLM agents for **biological intelligence**（genomics→biomedicine） | BIB 2026 | 10.1093/bib/bbag110 | 述评 | LLMAgent4Bio：四最小组件（task spec / external tools / iterative control loop / LLM backbone）+ PLAN–ACT–OBSERVE–REFLECT + 三层分类法（任务→架构→领域接地） |
| 22 | PMC12516949 | **BioRAGent**：tool-augmented RAG + 多 agent | BIB 2025 | 10.1093/bib/bbaf539 | **真实系统** | Guide（查询优化）/ Retriever（检索）/ Reviewer（校验）+ 11 个 API 提取器工具；GPT-4o 基座；总体平均 **0.92** |
| 23 | PMC13189163 | The next paradigm in bioinformatics | BIB 2026 | 10.1093/bib/bbag245 | 观点 | 三支柱（通用基础模型 + 多智能体 + 自动化验证）+ PARM（Planning/Action/Reflection/Memory）；SMA 药物重定位蓝图 |

## 2. 5 条已校验 evidence_quote（全部 `q in t` == True，落盘后程序复核通过）

- **19**：`The agent consists of trainable decision-making components such as the LLM itself, policy, memory, and reasoning scheme.`
- **20**：`The architecture of an LLM agent includes four core components: planning, perception, action, and memory.`
- **21**：`Task specification : the biological goal provided by the user or inferred by the agent. External tools : established computational software, databases, and simulators. Iterative control loop : planning, tool invocation, monitoring, and self-correction. LLM backbone : responsible for reasoning, decomposition, and interpretation.`
- **22**：`BioRAGent employs three specialized agents: Guide (query optimization), Retriever (data retrieval), and Reviewer (answer validation) to access authoritative biomedical databases and to generate accurate responses.`
- **23**：`The typical architecture integrates four fundamental components: (i) a planning module that decomposes a complex goal into subtasks; (ii) tool use interfaces to query databases, execute bioinformatics pipelines, or control experimental automations; (iii) short- and long-term memory, often implemented through retrieval-augmented generation (RAG), to maintain context and documentary grounding`

⚠️ 逐字坑（本批实测）：PMC 抽出的全文里，公式/疑似冒号前**会带一个空格**——`Iterative control loop : planning…`
（`loop` 与 `:` 之间有空格）。凭印象写成 `loop: planning` 会 MISS。**引文一律复制粘贴原文片段，不要手打。**

## 3. 落卡前单脚本机械门（本批内联配方）

一个 `execute_python` 里同时断言四件事，全过再 `json.dump`：

```python
assert c["evidence_quote"] in txt[n]          # 逐字可 grep
assert len(c["architecture"]) >= 600          # 架构下限
assert len(c["limitations"])  >= 60           # 局限下限
assert len(c) == 10                           # 字段齐全
```

小批（N≤5）时**内联断言比调用 `scripts/verify_evidence_quotes.py` 更省一次工具调用**；
批次大或需跨文件校验时才走脚本。

## 4. 综述/观点类字段的固定填法（本批 4/5 篇适用，照抄）

- `benchmark` → 「未做量化评测（综述类）。文中转述所评述工作自报的基准数字（非本文自测）：…」——**转述的他人数字必须标「引用之案例」，不得写成本文成绩**。
- `validation` → 「文献综述，无新增实验或量化评测；汇总并对照已有系统…」。
- `models` → 「综述不绑定单一模型，横向比较 …：<盘点对象罗列>」；⛔ **绝不把盘点对象的模型当成本篇的模型**。
- `inputs`/`outputs` → 写「综述语料为…」/「综述层面产出…；就智能体而言…」，**先答综述自身、再答所归纳系统**。

## 5. 新增经验（超出 C11 本轮才学到）

1. **先读基准样卡校准**：平台已有合格深读卡样本（本次 `data/deep_cards_deleg_15d8b24b.json`）→ 开工先读，校准字段句式与 `architecture` 密度。样本实测 **636–1069 字**，本批写到 **1023–1587 字**（「400–800 字」是下限不是上限）。
2. **输出长度现实**：5 张卡 = 落盘 **32544 B**；同一份 JSON 贴进回复正文 → **中途撞输出长度上限被截断**。⇒ 落盘是主通道，正文续写是预期的、不是故障。
3. **回读校验才算完成**：「不要只回传内容」= 落盘 + `os.path.getsize` + `json.load` 回读 + 报路径与字节数。
4. **单行全文读法（本批全 5 篇均近乎单行，`\n`≈5）**：用 `open().read()` + `print(t[a:b])` 按**字符区间**读，窗口 ~16–22k 字符；`read_file` 的 offset/limit 在单行文本上失效（见 SKILL「工具陷阱」）。