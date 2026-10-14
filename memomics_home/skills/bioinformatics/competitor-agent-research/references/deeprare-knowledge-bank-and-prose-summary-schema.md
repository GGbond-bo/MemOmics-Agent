# DeepRare 竞品底稿 + 「散文式中文结构化摘要」交付变体

来源会话：2026-10-11，`data/lit_text/` 下两篇 agentic-AI 论文逐字精读（DeepRare / ChemGraph）。
用户要求：「深度结构化提取两篇论文的关键信息，输出中文结构化摘要（每篇独立分节）… 禁止编造：所有数字必须来自原文」。

---

## 一、交付变体：散文式中文结构化摘要（区别于 C 模式的 JSON 深度卡）

**触发词**：「深度结构化提取 N 篇论文的关键信息」/「输出中文结构化摘要」/「每篇独立分节」/「禁止编造，数字必须来自原文」。

**与 C 模式深度卡的区别**：
- 深度卡 = 每篇一张 **JSON 卡**（10 字段 snake_case），供程序合并；
- 本变体 = 每篇一节 **中文散文摘要**（Markdown，小标题分节），人读。**两者字段口径不同，别互相套。**

**固定分节（本次用户接受、可复用）**：
1. 元信息（标题/作者含共同一作与通讯/机构/期刊年份/DOI/代码与数据仓库）
2. 一句话定位
3. 研究思路（设计哲学、架构分层、与已有工作差异）
4. 解决什么问题
5. 工作量与内容（团队、工具数、覆盖对象数、工程实现）
6. 怎么测试（评测口径、专家评审人数与病例数、消融、对照）
7. Benchmark 与数据集（表：名称/规模/来源）
8. 关键结果数字（**逐条标注来自正文 vs 图**）
9. 局限与作者自述边界
10. 可提取的更多信息（**可复用组件 / 开源地址 / 许可**）

**交付格式硬规矩**：
- 每篇独立大节（`# 论文一：…` / `# 论文二：…`），节内小标题一致；
- 末尾给「任务小结」（完成内容 / 关键发现 / 是否落盘 / 遗留问题），用户认这个；
- 所有数字**逐条可回溯原文**；查不到写「原文未报告」，⛔ 不估、不补全；
- 元信息里**共同一作（equal contribution）与通讯作者要分清**；许可要抄原文（本次 DeepRare = CC BY-NC-ND 4.0，ChemGraph = CC BY 4.0）。

---

## 二、🔴 提取纪律：正文 vs 图注 vs 摘要 **三源交叉核对，冲突要显式标注**

本会话实测两处**同一论文内部数字不一致**：
- **DeepRare**：正文写 RareBench-MME `Recall@1 78%`，而 **Fig.2 图注**写 `70.0% top-1`（RAMEDIS 正文未单列、图注写 `72.6%`）。
- **数据集计数**：摘要/评测设置写「nine datasets」，后文多处又写「eight datasets」（HPO-wise 与消融排除了 Xinhua 隐私集）。

⇒ **规矩**：数字落笔前，凡同一指标在**摘要 / 正文 / 图注**都出现过，逐处对照；**不一致时两条都列出并注明出处**，⛔ 不要静默挑一个（用户是「所有数字必须来自原文」派，静默择一会被视为编造）。
判据一句话：**报告的是「原文写了什么」，不是「我认为哪个对」。**

---

## 三、读本地 `lit_text/`（PDF 抽出的全文 txt）的正确读法

- **先 `wc -l` + `wc -c` 判形态**：本会话两篇均为**多行文本**（DeepRare 3046 行 / 124,899 B；ChemGraph 1027 行 / 59,920 B）→ **`read_file(limit=, offset=)` 分段直接可用**。
  ⚠️ 与「工具陷阱」表里 PMC 单行 txt（`count("\n")≈5`，需 `fold -s -w 700`）**是两种形态**，别默认全是单行。
- **定位章节最省调用的办法是 `terminal` + grep 一次**（不走 read_file）：本会话用
  `grep -n -i -E "ablation|discussion|limitation|Web application|robustness|self-reflect|module" <f>.txt`
  一次拿到 Methods/Discussion/Limitations/Web 应用的行号，再 read_file 定点切。
- 图区会把大量散数（坐标轴刻度、图例名）铺成逐行数字，**读起来像噪声**——图注（`Fig. N |` 开头那段）才是可取证的文本，散在正文里的数值优先取正文句。

---

## 四、DeepRare 事实底稿（Nature 2026，罕见病诊断多 agent —— 新竞品，此前 LB 未覆盖）

- **身份**：*An agentic system for rare disease diagnosis with traceable reasoning*；DOI **10.1038/s41586-025-10097-9**；*Nature* Vol 651，2026-03-19（线上 02-18；收稿 2025-06-30 / 接收 2025-12-30）。
- **作者**：Weike Zhao / Chaoyi Wu / Yanjie Fan（**三人共同一作**）；通讯 **Ya Zhang、Yongguo Yu、Kun Sun、Weidi Xie**（上海交大 AI 学院 + 上海 AI Lab + 交大医学院附属新华医院 + 湘雅医学院附属儿童医院 + 哈佛医学院）。
- **代码/数据**：`github.com/MAGIC-AI4Med/DeepRare`；Web 应用 `https://deeprare.cn`；数据 RareBench(HF `chenxz/RareBench`)/MyGene2/DDD/MIMIC-IV + 自建存 NGDC（**PRJCA052720 / GVM001237,GVM001238 / OMIX013512 / GSA-Human HRA015470**，受控访问）。
- **许可**：CC BY-NC-ND 4.0。
- **架构（MCP 启发三层）**：① 中央主机 + memory bank（默认 **DeepSeek-V3**）；② **6 个 agent server**：phenotype extractor / disease normalizer / knowledge searcher / case searcher / phenotype analyser / genotype analyser；③ 异构外部数据源。整合 **>40 种专业工具**。
- **工作流两阶段**：信息收集（表型侧 HPO 标准化→检索→分析；基因侧 VCF 注释→排序→合成）＋ **自反思诊断**（候选为空则增大搜索深度 N 迭代）。后处理 **reference link verification** 剔无效 URL 抑制幻觉。
- **关键组件**：BioLORD 归一化（cosine≥0.8 阈值）；病例检索 = text-embedding-3-small 初筛 top-50 + **MedCPT-Cross-Encoder** 重排；表型工具 PhenoBrain / PubCaseFinder / zero-shot LLM；基因分析用 **Exomiser 14.1.0**（gnomAD/1000G/TOPMed/UK10K/ESP + PolyPhen-2/SIFT/MutationTaster + OMIM/HiPhive）。
- **规模**：**9 数据集 / 6,401 例 / 2,919 病 / 14 专科**（7 公开 + 2 自建）。
- **关键数字（正文逐字）**：
  - HPO 任务平均 **Recall@1 57.18%**、Recall@3 **65.25%**；次优 = 推理 LLM **Claude-3.7-Sonnet-thinking 33.39%**，高出 **23.79% / 18.65%**。
  - 多模态（HPO+基因）：Xinhua **69.1% vs Exomiser 55.9%**；Hunan **63.6% vs 58.0%**；加基因后 Xinhua **39.9%→69.1%**、Hunan **33.3%→63.6%**。
  - 数据集级（正文）：MME **78%/85%**；MyGene2 **74%/81%**；MIMIC-IV-Rare **29%/37%**；Xinhua(本地模型) **58%/71%**。
  - 专家对照（163 例）：DeepRare **R@5 78.5% / R@1 64.4%** vs 医师 **65.6% / 54.6%**。
  - 长尾(≤10 例)：R@1>0.8 占比 DeepRare **31.8%** vs DeepSeek-V3 23.5% / R1 26.6% / Baichuan-M1 **2.5%**。
  - 专科：内分泌 60% vs 32%；消化(729 例) 49% vs 34%；最高肾/泌尿 66%、最低肺/呼吸 31%。
  - 消融：GPT-4o **25.60%→54.67%(+28.56)**；DeepSeek-V3 **26.18%→56.94%(+29.95)**。
  - 推理链参考来源专家认可 **95.4%**（mean 0.954 / median 1.000）。
  - 失败模式(n=200)：Reasoning Weighing 41.0%(82) / Phenotypic Mimic 38.5%(77) / Etiologically Associated 15.5%(31) / Reasoning Factual 2.5%(5) / Evidence Linking 2.5%(5)。
- **评审设定**：8 名专家复核 240 例（一致 88%，Pearson **0.8689**）；10 名副高以上医师评 180 例推理链（每例 3 人）；5 名医师头对头 163 例；3 名专家归类 200 失败例。
- **作者自陈局限**：未纳入所有数据源；检索为聚合式未自适应；面向「已知患病未确诊」非专科初筛；患者交互模块缺验证集；幻觉 URL / 不相关引用是主要错误源。

---

## 五、ChemGraph 事实底稿（Commun. Chem. 2025 —— 补充既往 LB 的逐字数字）

- **身份**：*ChemGraph as an agentic framework for computational chemistry workflows*；DOI **10.1038/s42004-025-01776-9**；*Communications Chemistry* 2025（Article in Press）；作者 Thang D. Pham / Aditya Tanikanti / Murat Keçeli（**Argonne**：CPS Division + ALCF Division）。
- **代码/数据**：`github.com/argonne-lcf/ChemGraph`；Zenodo `records/17290519`。**许可 CC BY 4.0**。
- **架构**：**LangGraph v0.4.7** 图-状态执行 + **ReAct**；单 agent 版 + 多 agent 版（**planner → executor(s) → aggregator**）；工具封装 RDKit/ASE/PubChemPy，核心数据结构 **AtomsData**（ASE Atoms 包装）；**以 ASE calculator 为引擎**接 xTB / MACE / UMA / NWChem / ORCA。双模式输出（自然语言 / 结构化 JSON）。
- **规模**：集成 **6 个工具**；**13 个 benchmark 任务 / 360 次独立评测**；分子随机取自 PubChem。
- **关键数字（正文逐字）**：
  - 前 6 任务：Claude-3.5-haiku 与 GPT-4o-mini 每项 **>80%**；Qwen-2.5-14B 最低 **60%**。
  - 后 5 任务：haiku 与 mini 均 **>83%**；Qwen 最低 **77%**。
  - name2file：GPT-4o-mini **87%**，工具调用 **4.9 次（期望 4）**。
  - react2enthalpy/react2gibbs：Qwen **<20%**；mini **40%/49%**；haiku **67%/69%**；GPT-4o **>83%**。
  - 多 agent：mini **40%→87%**、haiku **67%→87%**（enthalpy）；mini **49%→87%**、haiku **69%→93%**（gibbs）；**GPT-4o 100%**。
  - LLM 额外开销 **通常 <1 分钟/实例**（不含模拟）。软件版本：ASE v3.25.0 / NWChem v7.2.3 / mace-torch v0.3.13 / fairchem-core v2.3.0 / RDKit v2024.3.5 / TBLite v0.4.0 / ORCA v6.0；模型 `gpt-4o-mini-2024-07-18` / `gpt-4o-2024-08-06` / `claude-3-5-haiku-20241022` / Qwen-2.5-14B；评测在 **ALCF Aurora 超算**。
- **作者自陈局限**：首版；非多 agent-GPT-4o 外均未完美；单 agent 复杂流程因上下文饱和退化；token 成本限制更复杂档测试；安全靠 Docker 约束；规划 HPC 作业提交为未来工作。

> 复用价值：两篇若再次出现（DeepRare 属新增；ChemGraph 既往 LB 只提过名字），直接取用上述逐字数字，省一轮 grep。