# 深度卡 schema + 综述类论文字段填法（模式 C9）

来源：2026-10-06 会话——读 5 篇「科研 AI agent」论文全文（PMC txt），把既有薄卡升级为深度卡（中文），
交付格式「只输出我要的 JSON 字段」。本文件是该次交付的 schema、判据、校验片段与事实底稿。

---

## 1. 深度卡字段集（固定）

```json
{
  "n=9": {
    "architecture": "<400–800 字中文，分层逐层写机制>",
    "inputs":       "<模态与形状>",
    "outputs":      "<产出物与其校验动作>",
    "models":       "<逐个点名 + 版本号；综述类写'不适用'+盘点对象>",
    "benchmark":    "<逐字数字 + 数据集规模与口径；无则写'无量化评测'>",
    "validation":   "<证据等级阶梯；无则写'无实验验证'+方法>",
    "key_claim":    "<系统 + 在哪 + 超过谁/达到什么>",
    "novelty":      "<结构性新意>",
    "limitations":  "<作者自陈：… 我读出：…>",
    "evidence_quote": "<≤200 字符连续逐字原文>"
  }
}
```

外层 key 沿用原清单的编号写法（`"n=9"`），便于回写既有 `cards.json`。

### architecture 的分层模板（写机制，不写形容词）

`架构层数与名称` → `每层节点/agent 清单 + 各自动词化的职责` → `各 agent 用的工具与库（带版本/规模）`
→ `共享状态或记忆机制` → `编排方式（DAG / 主从 / 自反思环 / 黑板）` → `人在回路落在哪`

不合格写法：把 README 的功能点排列成一段话。合格判据：读完能复述出**数据怎么流动、谁对谁负责**。

---

## 2. 综述 / 观点 / perspective 类论文的固定填法（本次 n=11 / n=12 / n=33）

这是最容易填错的一类：**它本身没有系统、没有输入输出、没有基准**，但它盘点了别人的系统。

| 字段 | 写法 | 常见错误 |
|---|---|---|
| `inputs` / `outputs` | 「不适用（观点/综述文）：分析对象为同行评审文献、政策文件与已记载的系统部署」并点明讨论素材 | 硬编一个"用户提问"当输入 |
| `models` | 「不适用（综述/观点）。原文未披露所用 LLM 版本；盘点对象含 The AI Scientist、Agent Laboratory、ToolUniverse、BRAD…」 | ⛔ 把**盘点对象**的模型（GPT-4o / Claude 3.5 Sonnet）写成**这篇论文**的模型 |
| `benchmark` | 「无量化评测（观点文，无实验基准）」；若文中引用了**他人**的数字，写「引用之案例量化：…」（如 The Virtual Lab 92 nanobodies、>90% 表达可溶） | 把他人的成绩写成"本文成绩" |
| `validation` | 「无实验验证：属论证型观点文，靠文献引用（36 篇+）与既有系统举例支撑」+ 交代其方法（检索窗口 / 来源库 / 纳入标准 / 参考架构为概念示意非实测） | 留空 |

> 判据：答「不适用」是合格的，但**必须说明为什么不适用**；留空不合格。

---

## 3. 落卡前的两条机械校验（脚本，别用肉眼）

### 3.1 evidence_quote 逐字可 grep（≤200 字符）

```python
import os
d = r"<...>\data\text"
checks = {
    "n9":  ("PMC12999473.txt", "a central LLM-powered host with memory coordinates the process, specialized agent servers handle phenotype and genotype analysis, normalization and knowledge retrieval"),
    # ...
}
for k, (f, q) in checks.items():
    t = open(os.path.join(d, f), encoding="utf-8").read()
    assert len(q) <= 200, (k, len(q))
    print(k, len(q), "FOUND" if q in t else "MISSING")
```

铁律：**跨句省略、拼接两句、凭记忆重述，必然 MISS**。只留一段**连续逐字**原文。
挑句子时避开上标噪声——PMC 正文里 `(MCP) 8 , DeepRare uses…` 的 `8` 会让含它的片段 grep 失败，
所以引用要**从噪声之后起头**（本次 n=9 的 quote 即从 `DeepRare uses a three-tier architecture:` 起）。
成品校验器：`scripts/verify_evidence_quotes.py`（空白归一化 + 退出码 1 拦交付）。

### 3.2 表格里的 LaTeX 宏先压掉再读

PMC fullTextXML 的表格单元格常嵌整段 LaTeX，直接 `print` 会把真值淹没：

```python
seg = re.sub(r"\\documentclass.*?\\end\{document\}", "[MATH]", seg, flags=re.S)
```

只改善可读性，不改判定；✓/✗ 与数值仍需从表注/正文补齐。

---

## 4. 批量读长行 txt 的节奏（本次 5 篇实测）

- 读前 `wc -c` 看**字节**（不是 `wc -l`）：`30KB / 47KB / 57KB / 90KB / 100KB` 全是 `wc -l = 5` 的长行文本。
- 一篇 100KB 的论文 ≈ 6 段 `print(t[a:b])`（每段 15–20k 字符）；`execute_python` stdout 约 10000 字符上限，
  **单次打印不要超过 ~10000**，否则被截。
- 定位章节：`re.finditer` 找 `Stage 1` / `Table 4` / `Opportunities` / `Methods` 等锚点的 `m.start()`，
  只读判断所需区段；**参考文献段（常占尾部 20–40%）整段跳过**。
- 缺段核对：相邻两次 `t[a:b]` 的后一条首字符应等于前一条末字符的续接，读着"跳"了就补读交界区。

---

## 5. 本轮 5 张深度卡的事实底稿（速查，数字均逐字核过）

| n | 论文 / venue | 类别 | 一句话定位 | 关键数字 |
|---|---|---|---|---|
| 9 | DeepRare — Nature 2026 (10.1038/s41586-025-10097-9) | 领域专用 agent | MCP 式三层（中央宿主+6 agent 服务器+外部源）罕见病诊断，主从 + 自反思环 + 引用链接验证 | HPO-wise Recall@1 57.18%（次佳 33.39%）；多模态 69.1% vs Exomiser 55.9%；专家推理链一致率 95.4%；Recall@1 64.4% vs 医师 54.6% |
| 10 | GeneGenie — Brief Bioinform 2026 (10.1093/bib/bbag430) | 数据分析/QA agent | 确定性五节点 LangGraph DAG + 强类型 BioState + 本地 hg38 双模 BLAST | GeneTuring 16×100=1600；Gemini 2.5 Pro 图模式 1158(72.375%) vs 最佳裸答 253(15.85%)；蛋白编码基因模块中位 8% |
| 11 | MCP-native hierarchical AI scientist — Front AI 2026 (10.3389/frai.2026.1820375) | 基础设施与框架（观点） | 协议层 + 组织层"共同必要"，信息契约式层级 + 四组织原语 + 三扩容路径 | 无量化评测 |
| 12 | Streamline agentic bioinformatics — Brief Bioinform 2025 (10.1093/bib/bbaf505) | 综述 | 双轴分类法（wet/dry × single/multi）+ 能力对比矩阵 + 端到端自动化实验室愿景 | 无量化评测 |
| 33 | Agentic AI as coordination paradigm — Patterns 2026 (10.1016/j.patter.2026.101496) | 观点 | 治理感知 agentic 协调；三个"治理拒绝"设计边界 + MCP 参考机制 + 两参考架构 | 无量化评测 |

（5 条 `evidence_quote` 均已在原文中 `q in t` 校验通过，≤200 字符。）

---

## 6. 交付形状（本次获认可）

```
已读：n=9,10,11,12,33 / 未读：无（五篇全文均已分页读完）
<JSON>
<执行摘要：≤5 条——读法 / 覆盖 / 数字口径 / 校验结果 / 无阻塞>
```

用户明说「只输出我要的 JSON 字段」时：**摘要压到 ≤5 条**，⛔ 不要写成报告；
要省字数就压摘要与 benchmark 的冗余，⛔ 不压 architecture 的机制细节。