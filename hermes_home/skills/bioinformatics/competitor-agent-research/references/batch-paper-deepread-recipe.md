# 模式 C — 批量全文精读出竞品卡（recipe）

适用：用户给一个**论文清单（manifest）+ 全文文本文件**，要求「精读 N 篇全文，产出结构化竞品卡（中文）」。
与模式 A（单竞品深挖）、模式 B（赛道全景）并列的第三种交付形态。

## 1. Manifest 与全文的位置

平台会话目录：`E:/MemOmics-Agent/results/<session_id>/`

- 清单：`data/cards_source.json` — 是 **list[dict]**，每个 dict 含
  `n`（论文编号，用户按 n 指定子集）/ `title` / `venue` / `year` / `doi` / `pmcid` / `kw` / `abstract` / `methods` / `results` / `text_file`。
- 全文：`data/text/PMC<pmcid>.txt` — **注意：这些文件 `wc -l` 只有 5 行，但 `wc -c` 常是 30KB–580KB**（摘要/metadata 段落被压成长行）。
  → **判断大小用 `wc -c`，绝不能用 `wc -l`**（否则会误判成「5 行小文件」而低估）。

先读 manifest，按用户给的 `n` 列表筛出目标，打印每个的 `title/venue/year/doi/pmcid/text_file`，
再据此定位全文文件。**不要自己去猜文件名**。

## 2. 精读技术：关键词锚点切片，不要整篇读

一篇 100KB+ 全文一次读会撑爆上下文，且撞 tool-call 上限。用 Python 持久内核按**锚点**取窗口：

```python
t = load("PMC13345910")            # open(base+pm+".txt", encoding="utf-8").read()
# 一次打印所有锚点的命中位置（判断哪些存在、避免 -1 反复猜）
for term in ["architecture","benchmark","Discussion","limitation","agent","GPT","accuracy"]:
    print(repr(term), "->", t.find(term))
# 命中后在命中点前后取窗口
i = t.find("Overview of Co-Scientist architecture"); print(t[i:i+6000])
```

必备锚点分组（按优先级）：
- **架构**：`architecture` / `Orchestration` / agent 角色名（Design/Reflection/Ranking/…）/ `multi-agent` / `layer`
- **输入输出**：`input` / `output` / `interface` / `query`
- **底层模型**：模型厂商名（Gemini/GPT-4o/Claude/Llama/DeepSeek）
- **benchmark / 数字**：`benchmark` / `accuracy` / `mAP` / `Elo` / `pass@` / 具体数字串（`81%`）
- **验证**：`validat` / `in vitro` / `wet lab` / `expert evaluation` / `case study`
- **局限**：`Discussion` / `limitation` / `Conclusion` / `future` / `challenge`
- **证据原句**：定位后**原样复制一句**存为 `evidence_quote`（用户要能 grep 回原文）。

**每篇一回合内批量打印多个锚点**，而不是一篇一次工具调用——10 篇长文很容易耗尽迭代预算。

## 3. 竞品卡 schema（交付字段，缺则填「原文未报告」）

```
n, name, title, venue, year, doi, pmcid,
team,                    # 团队/机构 + 通讯作者
category,                # 综述与观点 / 假设生成 / 领域专用agent / …
goal,                    # 一句话目标
architecture,            # 详细：agent 角色名、编排拓扑、层次、关键机制（self-play/锦标赛/知识图谱/MCP/Skills…）
inputs, outputs,
models,                  # 底层 LLM（未固定则说明；综述类填「未披露」）
benchmark,               # 名称 + 规模 + 全部关键数字（含对照组）
validation,              # 真实验证（湿实验/专家盲评/benchmark 自动化/无）
key_claim,               # 一句核心主张
novelty,                 # 方法学新意
limitations,             # 作者自陈 + 可推断，分开写
evidence_quote,          # 原文原句（可 grep 回证）
memomics_implication,    # 对 MemOmics 的启示（如何对标/自证）
```

输出为 JSON：`{"cards": [ … ]}`。**同时在正文里输出一段可解析的 JSON 代码块**（用户会程序化解析）。
用户要求中文，但 `evidence_quote` 保留**原文英文原句**。

## 4. 三条硬规矩（承袭 SKILL.md B3，扩展到字段级）

- **数字/字段一律来自原文**，标 DOI/PMCID；查不到写「原文未报告」，**绝不编造**（schema 缺字段尤其容易踩）。
- 作者**自陈局限**与被你**推断的局限**分开写，别混为一谈。
- 交付被截断时：**给部分 JSON + 明确缺口清单**（哪几篇只读到摘要、哪几个字段缺），而不是交空或交幻觉。

## 5. 预算陷阱

- 10 篇长文全文精读 = 大量工具调用，**极易撞迭代上限**（本次实测在 9/10 篇处被截断）。
- 对策：manifest 一次读完；每篇**一回合**用锚点窗口拿齐所需段落；优先把「摘要+架构+benchmark+局限」四段拿全，
  再补细节；预留余量做最终交付。宁可 9 篇都完整，也不要 10 篇都半截。

## 6. 已读箭头（本类已覆盖的竞品，避免重复调研）

n=26 SDL 综述（Chem Rev 2024）/ n=27 Co-Scientist（Nature 2026, Gemini 多 agent）/
n=29 MetaChat（Sci Adv 2025, AIM 光子设计）/ n=31 AAI 精准农业（Front Plant Sci 2025）/
n=33 agentic coordination 数字健康+农业（Patterns 2026, MCP 治理）/ n=34 合成微生物基因组 agentic（Front Bioinform 2026）/
n=35 ProteinMCP（Protein Sci 2026, Claude Code + 38 MCP + Skills）/
n=41 PHIA 可穿戴健康（Nat Commun 2026）/ n=45 World Avatar 分布式 SDL（Nat Commun 2024, 动态知识图谱）