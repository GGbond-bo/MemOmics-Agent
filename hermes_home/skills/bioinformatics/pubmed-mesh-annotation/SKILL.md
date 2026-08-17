---
name: pubmed-mesh-annotation
description: "MeSH 语义索引/文献 MeSH 标签标注：给定文献 title+abstract（或 PMID），从 PubMed 官方索引输出 MeSH 主要标签。适用于语义索引 benchmark（如 试卷1_语义索引TaskA）、文献打标、知识库构建的 MeSH 词表获取。"
when_to_use: "用户要求给文献输出 MeSH 标签 / MeSH 主要主题词 / 语义索引标注 / 给论文打 MeSH 词时加载。核心知识：query_ncbi esummary 不含 MeSH，必须用 efetch MEDLINE 格式提取 MH 行，* 前缀 = Major Topic。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux]
metadata:
  hermes:
    tags: [mesh, pubmed, ncbi, semantic-indexing, annotation, benchmark]
    difficulty: intermediate
    language: Python
    category: bioinformatics
---

# PubMed MeSH 语义索引标注

## 触发场景

- 语义索引 benchmark 任务（"给定文献 title + abstract，输出 MeSH 主要标签"）
- 给文献/论文打 MeSH 词（文献综述、知识库构建、系统综述检索词）
- 需要 PubMed 官方 MeSH 索引做交叉验证时

## 🔴 铁律 0: 考试/benchmark 密封答案不可读

benchmark 目录下通常有 `*_密封答案.json`（sealed answer）。**这是考试，不是参考资料。绝不 read_file 密封答案文件。** 只读 `*_考试题.json`，按题目要求自行求解。偷看答案 = 考试作弊，会污染 benchmark 评分。

## 标准流程（5 步）

### Step 1: 读考试题，提取 PMID 列表

```json
{"pmid": "23479819", "title": "...", "abstractText": "..."}
```

### Step 2: 确认 PMID 存在（可选）

```python
query_ncbi(db="pubmed", query="23479819")  # esummary：title/journal/pubdate
```

⚠️ **esummary 不含 MeSH 字段**。只用来确认文献存在/年份，拿不到 MeSH 标签。

### Step 3: efetch MEDLINE 格式抓官方 MeSH（核心步骤）

```bash
curl -s -k "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=${PMID}&rettype=medline&retmode=text" | grep -E "^(MH|OT) "
```

- `-k` 绕过 schannel 证书问题（Windows 上必需）
- `MH  - ` 行 = MeSH 词表，**`*` 前缀 = Major Topic（主要主题词）**
- 子标题如 `Sleep Apnea, Obstructive/therapy`、`Vibrio/enzymology/*metabolism`

批量抓取（for 循环，一次全部抓完再整理）：
```bash
for pmid in 23479819 23483174 23483175; do
  echo "===== PMID $pmid ====="
  curl -s -k "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=${pmid}&rettype=medline&retmode=text" | grep -E "^(MH|OT) "
done
```

### Step 4: 选词策略（5-10 个）

1. **优先取 `*` Major Topics**（去掉 `*` 前缀）——这是 PubMed 索引员标注的"主要主题"
2. 不足 5 个时，**补全同篇 MH 词**（非星标词、相关子标题词），凑到 5-10 区间
3. 输出为**英文 MeSH 术语**，保留子标题（如 `Sleep Apnea, Obstructive/therapy`）
4. 每篇 5-10 个，独立成条目

示例（PMID 23479819，官方 MH 7 行全部为星标/核心词）：
```
"mesh_major_topics": ["Luminescence", "Vibrio", "Luciferases", "Flavin Mononucleotide", "Fluorescence", "Kinetics", "Time Factors"]
```

### Step 5: 保存答案 JSON + 交叉验证

答案存 `results/{session_dir}/answers_*.json`，结构：
```json
{"exam": "...", "answers": [{"pmid": "...", "title": "...", "mesh_major_topics": [...]}]}
```

验证脚本：`scripts/verify_mesh_answers.py <answers.json>`（重新 efetch 官方 MH，逐条比对答案标签是否真实存在于官方索引）。

## 交叉验证要点

- 比对时**去掉 `*` 前缀**再比较（官方 MH 带星号，答案不带）
- 子标题归一化：`t.split("/")[0]` 取 MeSH 主词比较
- 验证通过后向用户报告 PASS + 逐条命中表

## Pitfalls

| 坑 | 说明 |
|----|------|
| 密封答案 | `*_密封答案.json` 是考试答案，绝不读取 |
| esummary 无 MeSH | query_ncbi esummary 只给标题/期刊/年份，MeSH 必须 efetch MEDLINE |
| curl SSL | Windows 上 eutils https 需 `-k`（schannel 证书问题） |
| 星号前缀 | 官方 MH 行 `*Luminescence` 的 `*` 是 Major Topic 标记，输出答案时去掉 |
| MSYS 临时路径 | 验证脚本别写 `$(cygpath -u "$TEMP")`（= MSYS `/tmp`），原生 Python 解析成 `E:\tmp` 打不开。写真实 Windows 路径 `C:\Users\<user>\AppData\Local\Temp`（见 windows-bioinformatics-batch-processing 铁规 16.5） |

## 参考文件

- `scripts/verify_mesh_answers.py` — 答案交叉验证脚本（可复用，传入 answers JSON 路径）
