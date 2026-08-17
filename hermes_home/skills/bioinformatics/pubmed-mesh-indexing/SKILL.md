---
name: pubmed-mesh-indexing
description: 从 NCBI E-utilities 检索官方 MeSH 标签与 DeCS 编码。使用场景：为文献输出 MeSH 主要标签（语义索引 benchmark）、西班牙语文献输出 DeCS 编码（MESINESP 式多语言检索）、查询 MeSH 树号构建知识特征。触发词："MeSH" / "DeCS" / "语义索引" / "主要标签" / "mesh tags" / "MESINESP" / "DeCS 编码"。
metadata:
  hermes:
    category: Literature
---

# PubMed MeSH 索引 / DeCS 编码检索

## 何时使用
- 为论文输出官方 MeSH 主要标签（TaskA 式语义索引 benchmark）
- 为西语文献输出 DeCS 编码（MESINESP 式多语言检索 benchmark）
- 需要 MeSH 树号 / DeCS 编码构建知识库特征

## 核心事实
- **DeCS = MeSH 的西班牙语版本，编码与 MeSH 树号完全一致**。拿到 MeSH 树号即 DeCS 编码，无需另行查询。
- `query_ncbi(db="mesh")` 只返回 UID、无树号 → 必须走 esearch + efetch。
- NCBI mesh db 的 efetch **即使 retmode=xml 也返回纯文本（非 XML）**，树号在 `Tree Number(s):` 行，逗号分隔。

## 标准工作流（mesh db）
1. esearch 拿 UID：`esearch.fcgi?db=mesh&term=<Descriptor>[MeSH]&retmode=json`
2. efetch 拿树号：`efetch.fcgi?db=mesh&id=<UID>&retmode=xml` → 正则 `Tree Number\(s\):\s*(.+)` 解析
3. 已验证脚本：`scripts/mesh_tree_numbers.py`

## 关键坑（实测血泪教训）
### UID 格式陷阱
- 常规 MeSH 描述符 UID = `68` + D 码数字（如 D054198 → 68054198、D001706 → 68001706）
- **81 前缀 UID 是错配记录**（补充概念/其他记录），返回 Y 码（Y02.050、Y09.010.020）——Y 码不是标准 MeSH 树号，切勿使用
- 已知 D 码时直接 fetch 最稳（`68`+D码数字），跳过 esearch 歧义
### esearch 匹配歧义
- `uids[0]` 可能不是目标描述符（实测 "Blood Transfusion" 返回了 "Transfusion Reaction" D065227）
- 必须核对 efetch 返回的标题/树号是否符合预期，不符则换 uids[1] 或直接按已知 D 码 fetch
### 网络与限流
- 本环境 curl 对 NCBI 常超时返回空 → 用 Python requests + User-Agent + 指数退避重试（5s, 10s, 15s...）
- esearch 带 `[MeSH]` 限定在批量请求时可能整体被限流 → 退化为纯词条 + 请求间 sleep ~1s

## MeSH 主要标签 benchmark 的评判陷阱（TaskA 实证）
- **"主要标签"金标准通常包含人口学限定词**（Humans/Male/Female/Aged/Middle Aged/Adult/Infant/Pregnancy），这些在 PubMed 记录里多为 MajorTopicYN="N" → 严格按 MajorTopicYN=Y 过滤 recall 暴跌（实测 55.6%）
- **Publication Type 不是 MeSH 描述符**：Randomized Controlled Trial 等不要输出
- **不要 LLM 从摘要推断记录中没有的词**（如补 "Cohort Studies"、"Cardiovascular Diseases"）——precision 杀手
- 取舍策略：efetch 全部 `<DescriptorName>`（含 MajorTopicYN=N 的），再按"疾病主体 > 干预 > 机制 > 结局 > 人群"优先级选 5-10 个；若金标准含人口学词则必须保留

## 作答与评分约定（benchmarker 场景）
- 作答用 NCBI 实时数据，不凭模型记忆输出编码
- 评分报告格式（用户接受的格式）：逐篇/逐题对比表 + 总体 Precision/Recall/F1 + 失败根因分析
- 密封答案路径模式：`E:\benchmarker\exams\<试卷N>_<名称>\<试卷N>_<名称>_密封答案.json`
