---
name: ai-paper-structured-extraction
description: "AI / agent / 方法类论文的深度结构化提取 → 固定小节的中文结构化摘要（每篇独立分节）。铁律：所有数字必须逐条来自原文，原文没写的写「原文未报告」，禁止编造；主动审计并标注原文自相矛盾处（正文 vs 图注 vs 小节标题 vs 表格）。触发：'深度结构化提取论文关键信息'、'输出中文结构化摘要'、'提取 XX 论文的关键信息'、'把这篇 AI 论文拆成结构化摘要'。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  memomics:
    tags: [paper-extraction, structured-summary, ai-agent-papers, anti-fabrication]
    difficulty: intermediate
    category: research
---

## AI/agent 论文深度结构化提取

把一篇（或几篇）论文的**原始文本**（`.txt` / 提取出的正文，非 PDF）读透，产出**固定 10 小节**的中文结构化摘要，每篇独立分节，最后可加一张对比速览表。

### 触发条件
- 用户说「深度结构化提取论文关键信息」「输出中文结构化摘要」「把这篇论文拆成结构化摘要」
- 用户给出论文标题/DOI/arXiv 号，要求**逐项**提取（元信息、思路、方法、benchmark、数字、局限）
- 用户强调「禁止编造 / 所有数字必须来自原文 / 请先读原文确认准确标题」
- 对象多为 **AI / agent / 方法 / 系统类**论文（不是生物实验论文——生物实验论文走 `literature-full-summary` 9 项）

### 与相邻 skill 的分工（别搞混）
- **literature-full-summary**：生物文献 9 项思路提炼，**执行=调用 `summarize_paper` 工具**，落盘到文献库 `summaries/`。
- **professional-paper-interpretation**：编辑视角叙事逻辑解读（人看的方向，Mermaid 框架图 + 写作策略）。
- **本 skill**：**忠实抽取型**——不做叙事美化，只做「可溯源的事实结构化」。交付常是独立 `.md`（放 `results/<session>/data/` 或用户桌面），不写文献库。

### 输入是 PDF 时：先落地全文，再按本 skill 读（2026-10-24 新增）

本 skill 的输入默认是 `.txt`；用户直接丢 PDF 时**先提取成文本**，不要硬啃 PDF：

```bash
OUT="results/<sid>/data/<paper>"; mkdir -p "$OUT"
.venv/Scripts/python.exe memomics_home/skills/bioinformatics/paper-summary/scripts/run.py \
  extract --tier1 --pdf "<pdf路径>" --out "$OUT"
```

产出 `fulltext.txt` / `metadata.json` / `figures/`（实测 31 页 bioRxiv 预印本 → 99,245 字符 + 3 图，约 2 秒；依赖 pymupdf，`import fitz` 的 deprecation warning 可忽略）。

**长论文（>20 页 / bioRxiv 预印本）三件事**：

1. **先建章节地图，再读**：
   `grep -n -E "^[0-9]+\.?[0-9]*\s*[A-Z][a-zA-Z]+|^Abstract|^Introduction|^Results|^Discussion|^References" fulltext.txt`；附录另用 `grep -n "^A\.[0-9]"`。
   ⚠️ **单次 grep 会误命中**：实测把第 5 节误报成 `422:Methods`（真正结果节从 393 行起）、把正文引用的 "Table 1" 当成文末结果表（真正数值表在 1648 行）。→ 必须 `read_file` 落在该行附近核对内容，**别据一次 grep 定结构或找表**。bioRxiv 页脚的版权/DOI 行会反复插入、占掉大量行号，别当正文。
2. **分块读，400–450 行一块**（`read_file` 单次 ~100K 字符会截断）。顺序：摘要/引言 → 框架与方法 → 结果 → Discussion → **附录 Extended Methods** → 最后单独取表数值。
3. **参数只在附录**：迭代预算、重试上限、每步上限、包版本、评分 rubric 正文通常一个字不提（实例见下）。

### 数字双来源核对（表 ↔ 正文叙述）

结构化数字常**分两处**，只读一处必错：

- **主结果表**（多在文末 Supplementary）+ **正文叙述的幅度/p 值** → 分别读、核对一致后再写进摘要；口径写清（micro vs macro、相对哪个基线）。
- p 值 / n / 样本量**逐字引用**，不四舍五入、不概括。
- CellVoyager 完整实例（表值 + 正文 + 三案例评分 + 附录参数）：`references/pdf-preprint-extraction-recipe.md`

### 读取流程（必须先读原文）
1. **先列文件、确认存在**，再逐段读。
   - 用 `read_file(path, offset, limit)` 分块读；两篇独立 → **并行读**（同一回合发多个 read_file）。
   - ⚠️ 终端里**不要**在双引号内塞 Windows 反斜杠路径（`ls "E:\a\b"` → bash `unexpected EOF`）。要么用正斜杠 `/e/...`，要么直接用 `read_file`。
2. **标题必须从原文首页确认**：用户给 arXiv 号/DOI 时，先读第一页核对**准确标题**（用户常只给编号，不许猜标题）。
3. 通读**全部**正文 + Methods + 附录（数字常藏在 Appendix / Figure caption 里）。
4. **图注里的数字要点名来源**：正文没文字化、只在图上标注的数值，写清楚「Fig. N(a) 标注的数值序列为 …」，不要写成正文结论。

### 十节模板（每篇论文 10 节）
1. **元信息**：标题原文 / 期刊·卷·年·页 或 arXiv 号+版本+日期 / DOI / 投稿·接收·在线日期 / 第一作者（标注共同一作）/ 完整作者列表 / 通讯作者（含邮箱）/ 机构 / 系统名 / 代码仓库 / 数据可用性 / 资助
2. **一句话定位**：一句话说清系统是什么 + 做什么
3. **研究思路（核心设计哲学与架构）**：核心哲学 → 架构 → 为什么这样设计 → 关键分工/可扩展性 → 实现要点（框架、模型、超参）
4. **解决什么问题（痛点）**：领域 gap 逐条列
5. **工作量与内容**：工具/模块**数量**、动作空间、模型**名称与版本**、训练/自改进**轮次与步数**、数据**规模**（写「原文未报告」若不写）
6. **怎么测试**：评测方式、对比基线、人类/LLM 评估规模（n=?）、消融，明确「原文未报告人类评估」之类
7. **benchmark 细节**：来源基准、**任务构成表**（族 × 子主题 × 数量）、衡量指标定义、测试集划分
8. **关键数字**：逐条列出，**每条可溯源**（哪张图/哪一节）
9. **局限**：分「作者自述局限」与「原文自相矛盾/口径不一致处」两栏
10. **可复用信息**：对做同类系统的借鉴意义（agent 架构、奖励设计、可审计性、诚实边界声明等）

### 铁律：禁止编造（本 skill 的立身之本）
- 任何**数字/百分比/模型名/版本号**必须逐条来自原文；查不到就写「**原文未报告**」，**绝不用常识补全或估算**。
- 区分「原文明确陈述」与「从图里读出的值」——后者标注「按图标注读取」。
- 不要发明 benchmark 名、不要发明作者机构、不要把相似工作（ChemCrow↔Coscientist）混为一谈。
- Data/Code availability 若原文没有独立章节，明说「原文未设独立 Data availability 章节」。

### 自相矛盾审计（用户常明确要求，必做）
主动**交叉比对**，发现不一致就在「局限」节单列，并**标注位置**（哪一节 / 哪个图注）：
- **小节标题 vs 正文/图注**：如本次 ScienceBuddy 小节标题写 "Two-Cycle"，正文与 Fig.8 图注却是 "three cycles" → 硬矛盾，点名。
- **正文数字 vs 图注数字**：如正文说某轮从 34.4% 起，但图注数值序列里根本没有 34.4%。
- **计数口径**：如摘要说「18 个工具」，Methods 逐条枚举却有 19 个；图注分 5 类而正文文字只分 3 类。
- **可比较性陷阱**：不同实验口径的百分比不能并读（如「固定 harness 的纯模型增益」vs「全过程增益」），要说明口径不同（这属"易误读"，非硬矛盾，分开写）。
- 记录习惯：矛盾条 = 「矛盾点 + 出现位置 + 可能原因/推测」，推测要标明是推测。

### Pitfalls
- 只读正文不读 Methods/附录 → 漏掉超参、任务计数、数据划分等关键数字。**必须读完再写**。
- 用户给了 arXiv 号就以为标题已知 → 必须回原文首页核对（本次确认标题是 *ScienceBuddy: Recursive-in-Recursive Self-Improvement for Interactive Scientific Agents*，与"自我改进科研 agent"的印象一致但全名需照抄）。
- 把「图表里能看到但正文没写」的数字当正文结论 → 标注来源图号。
- 交付只发在对话里 → 用户常要落成 `.md` 文件（放 `results/<session>/data/`），写文件后再校验字节数/头部。
- 两篇以上时必须**每篇独立分节**（用户明确要求），不要合并成一篇写。
- **用户点名了结构就按用户的结构答**：用户问「背景 / 思路 / 实验内容（步骤+结果）/ 结论」→ 就答这四块；上面的 10 节模板是**兜底不是枷锁**，硬套会被视为答非所问（2026-10-24 CellVoyager 实测）。
- **流程/架构类论文在「思路」节配 `mermaid flowchart TD`**：节点名**照抄原文 Algorithm / pipeline 的步骤名**（如 PLAN→REFLECT→CODE→EXECUTE→FIXCODE→VLM 解读→REPLAN→REPORT），参数内嵌节点文本（`≤8 步`、`修 bug 3 次`）；图**不替代文字**，每步原理与参数仍要完整展开。
- **交付双轨**：对话里给**自成一体的完整解读**（用户只看对话，禁止只回「已落盘，路径在 X」）+ 同一份 `.md` 落盘供转发；交付物放 `results/<sid>/results/`，原始提取物（fulltext/figures/metadata）放 `results/<sid>/data/<paper>/`，并在回复里如实列出两条路径。
- **阶段小结写在回复正文里**：长解读要跨多轮调工具时，每轮正文开头先写 2–4 句「为什么 / 怎么做 / 结果 / 下一步」；只写在 thinking 通道用户看不到（实测被系统连纠两次）。

### 参考
- `references/worked-examples-chemcrow-sciencebuddy.md`：本次两篇（ChemCrow / ScienceBuddy）的实际 10 节输出骨架，可作模板复用。
- `references/pdf-preprint-extraction-recipe.md`：**PDF 长预印本提取配方** —— 落地命令、章节地图与误命中实例（`422:Methods` / `Table 1` 首条误命中）、分块读行号、数字双来源核对（CellVoyager 全量数值：CellBench 50 篇/483 分析、65.89/68.74 vs 基线 49.89/55.25、80% 假设值得深入、p=0.001 / r=0.047）、附录参数清单、四块输出骨架、交付目录分工。