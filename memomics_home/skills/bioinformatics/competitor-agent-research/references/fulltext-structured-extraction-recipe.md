# 全文结构化提取 → 中文结构化摘要（轻量交付物）

> 与「模式 C 深度卡」的区别：**深度卡是 10 字段 JSON（机器消费）**；本文是**给人读的多章节中文结构化摘要**。
> 触发形态：`深度结构化提取论文《X》的全部关键信息，输出中文结构化摘要`（常是子代理被派去做的一步，源文件在
> `results/<sid>/data/lit_text/<Paper>.txt`）。
> 首次沉淀：2026-10-11（Biomni，8 页正文 + 88 页补充材料，纯文本 ~170 KB / 4411 行）。

---

## 1. 交付物形状（固定 10 节，可裁剪但不要缺「数字溯源/局限」）

1. **元信息** — 标题 / 作者数与机构数 / 通讯作者 / 期刊 / 年份 / DOI / 代码&数据可用性 / **许可**
2. **一句话定位**
3. **研究思路** — 核心设计哲学 + 组件拆分 + 与已有工作的差异点
4. **解决什么问题（现有局限）** — 作者怎么论证「为什么需要这个」
5. **工作量与内容** — 规模数字（团队、数据规模、工具/软件/数据库数、模型基座、参考文献数）
6. **怎么测试（评测设计）** — 基准 + 对照基线名单 + 人类评审 + 消融 + 案例研究
7. **Benchmark 与数据集（逐个）** — 每个基准的来源/题量/指标/采样口径
8. **关键结果数字** — 指标 + 数值 + 对照基线（数字密度最高的一节）
9. **局限与作者自述边界** — 引用 Discussion 的 limitations 原文口径
10. **可提取的更多信息** — 可复用技术组件 / 开源地址 / 后续方向 / 对比对象 / 关键参考文献

末尾附一节 **「数据一致性提示（供上游注意）」** ——见 §3。

---

## 2. 读法：`lit_text/*.txt` 是**交织行号**格式（本机实测）

该目录下的 PDF 提取文本与 PMC 的「近乎单行长文本」**不同**：

- 正文**每行内容后面跟一行裸整数**（PDF 原版面的行号），即「内容行 / 序号行」交替出现；
- 行尾是 **CRLF**；一份 88 页论文 ≈ 4411 行、其中约一半是序号行。

⇒ **可靠读法（照抄）**：
1. `wc -c` / `wc -l` 先量体量。
2. **先用 `terminal` 的 `grep -n -E` 建「章节地图」**，再按行号 `read_file(offset=, limit=)` 分段读。
   一次 grep 同时定位所有锚点，省掉盲读：
   ```bash
   grep -n -i -E "Abstract|Introduction|Results|Discussion|Methods|Limitation|Data availability|Code availability|References|Supplementary|benchmark|ablation|license" paper.txt
   ```
   （Nature 系双栏排版的行号会打断关键词，**小节标题行本身仍完整**，用标题定位最稳。）
3. 按地图给出的行号区间 `read_file` 分段（每次 ~200 行），跳过裸整数行。
4. 补充材料（Supplementary Notes/Figures/Tables）在同一文件后半段，**别只读正文**——消融数字、prompt 全文、
   rubric 常在这里（本例：retriever 消融、逐任务增益、System prompt 全文都在补充材料）。

⚠️ 该格式下**纯文本内容检索命中不稳**（试过 `search_files` 对同一文件返回 0，而 `grep -n` 正常）——
**以 `grep -n` 为准**，别因为检索返回空就以为「原文没有这段」。

🟡 **格式不统一，先量再读（2026-10-11 第二实例补）**：**同一 `lit_text/` 目录下并非所有文件都是「交织行号」**——
本会话两篇是**干净多行文本**（DeepRare 3046 行 / 124,899 B；ChemGraph 1027 行 / 59,920 B），
`read_file(offset=, limit=)` **直接可用**，无需任何重排。⇒ 开工第一动作固定为：
`wc -l` + `wc -c` 判形态 → 试读头 20 行确认是否夹裸整数行 → 再决定「直接分段读」还是「按行号地图跳读」。
**两种形态下 `terminal` + `grep -n -E` 建章节地图都是最省调用的一步**（一次拿 Methods/Discussion/Limitations/Web 应用的行号，再定点切）。

---

## 3. 三条纪律（本模式的核心，等同 C2 的「给人读」版）

- **每个数字都要能指回原句**：结果/基准/规模数字一律从原文提取，不靠记忆、不四舍五入、不换口径。
- **原文没写的，明写「原文未报告」**，不要留空也不要猜。本例高频缺失项：**期刊 / DOI / 年份 / 许可**——
  提取文本开头只有标题+作者，从未出现 DOI/期刊名；预印本形态就用「原文未报告（形态为预印本，参考文献最新为 2025）」表述。
  **不要**因为文件名叫 `Biomni.txt` 就给它编一个 arXiv ID 或 DOI。
- 🔴 **主动标注原文自相矛盾**（最有价值的增量）：同一篇论文内部数字打架时，**两处都照录并显式标出**，
  而不是私下挑一个。上游/审稿人会认这个。本例抓到三处：

  | 项目 | 一处说 | 另一处说 | 位置 |
  |---|---|---|---|
  | 分子克隆基准题数 | 正文 + 图注 **10 个** | Methods **20 道开放题** | 正文 Results vs Methods「Wetlab Benchmark Development」|
  | 可穿戴温度文件数 | 案例正文 **458 个 Excel** | Methods **485 个**温度文件 | 正文 vs Methods「Wearable analysis case study」|
  | 动作发现文献总量 | 摘要/引言「tens of thousands of publications」 | 正文/图注 **25 类 × 100 篇 = 2,500** | Abstract vs Figure 1 图注 |
  | 🔴 **正文 vs 图注**（DeepRare） | 正文 Results **Recall@1 78%** | **Fig.2 图注 70.0% top-1** | 正文 vs 图注 |
  | **数据集计数**（DeepRare） | 摘要/评测设置 **nine datasets** | 后文多处 **eight datasets** | Abstract vs Results 正文 |
  | 🆕 **基座模型版本**（BioMaster） | Methods 写 **GPT-4** | 评测章节写「统一用 **GPT-4o**」 | **Methods vs Evaluation** |

  ⚠️ **「正文 vs 图注」是最隐蔽的一类**（2026-10-11 DeepRare 实例新增）：正文 Results 与图注各给一个数，
  两者都在同一 PDF 里、都「来自原文」，凭印象取一个就错。⇒ **同一指标凡在摘要/正文/图注都出现过，逐处对照**；
  报告的是「原文写了什么」，不是「我认为哪个对」。

  判据：**「同一个量在两处被给了两个数」比「某个数看着不对」更硬**——前者是可复现的原文事实，后者是主观。

  🆕 **第二入口 = 「同一事实、非同一数值」两处说法不同（2026-10-11 第三实例：Co-Scientist + BioMaster 同批）**：
  本例 BioMaster 的 **Methods 写基座为 GPT-4**、**评测章节写「统一用 GPT-4o」** —— 此类高频发生在
  **Methods 描述 ↔ Evaluation 描述**之间（两节常由不同作者在不同时间写，最易互相打架）。
  ⇒ 处理同前（两处逐字并列、各带节名）；并加一条禁令：⛔ **不替原文圆场** —— 不写「应为笔误 / 本意是 GPT-4o」
  这类调和句。替它选一个 = 把这条最硬的发现抹平，而用户/审稿人正是靠这一段判断提取的可信度。
  ⇒ 结论：矛盾既可能在**同一量的两处**、也可能在**同一事实的两节** ⇒
  **摘要 / 正文 / 图注 / Methods / Evaluation 五处都要过**，⛔ 别只在正文扫。

---

## 4. 何时用本模式 vs 深度卡

| 场景 | 交付 |
|---|---|
| 用户要「读得懂的全貌 + 数字 + 局限」（人读） | **本模式**（10 节中文摘要） |
| 用户要落进 `cards.json`、被下游脚本/报告消费 | 模式 C 深度卡（10 字段 JSON） |
| 用户要「只输出我要的 JSON 字段」 | 模式 C9/C11 |

两者可叠加：先按本模式把全文读透，数字自然齐了，落深度卡时 `benchmark` 字段直接取用同一批原句。

---

## 5. 本例产出的落点

- 交付文件：`results/<sid>/Biomni_结构化摘要.md`（UTF-8，10 节 + 一致性提示节）。
- 与 `references/biomni-knowledge-bank.md` 分工：**本文给「怎么读+纪律」**，知识库给 Biomni 的事实底稿。
- 🆕 **第二实例（2026-10-11，两篇 agentic 系统论文同批）**：DeepRare（Nature 2026，罕见病诊断，新竞品）+ ChemGraph（Commun. Chem. 2025）。
  逐字数字、架构分层、局限、开源/许可底稿见 `references/deeprare-knowledge-bank-and-prose-summary-schema.md`
  （含 ChemGraph 补充数字；ChemGraph 此前只在 `deep-card-schema-and-agentic-agents-2026.md` 出现过名字）。
  本轮交付为「每篇独立分节」的 Markdown 散文摘要 + 末尾「任务小结」，用户未提异议 ⇒ 该交付形状可复用。
- 🆕 **第三实例（2026-10-11，同会话第三批 · 两篇同批扇出）**：Co-Scientist（Google DeepMind，Nature 2026）+
  BioMaster（HKUST-GZ，Bioinformatics 2025）—— 两篇的事实底稿见 `references/co-scientist-knowledge-bank.md` /
  `references/biomaster-knowledge-bank.md`（★ 新矛盾类型「同一事实两处说法不同」即出自本批，见 §3）。
  🔴 **本批暴露的交付纪律（比新矛盾类型更重要）**：本批**两篇都只在回执正文里交付、没有落盘** ⇒ 内容只剩
  `cache/delegation/subagent-summary-2-*.txt` 缓存件可查；而同批 Task 1 **落了盘**
  （`results/<sid>/Biomni_结构化摘要.md` 18.7 KB / 181 行）**是三者里唯一可直接引用、可跨轮复用的产物**。
  ⇒ 派发这类任务时 **brief 里一律写绝对输出路径 + 要求 `os.path.getsize` 回读确认**；回执到达后
  **先 `ls` 该路径**（⛔ 「对话交付」不算完成，同 `delegation-orchestration` 的产出必须落盘条与 `templates/delegation-brief.md`）。