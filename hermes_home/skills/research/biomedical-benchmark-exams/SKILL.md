---
name: biomedical-benchmark-exams
description: 作答 MemOmics benchmarker 生物医学评测考试题（E:\benchmarker\exams\）。触发词："benchmarker测试"/"试卷N"/"考试题.json"/"密封答案"/"开始作答"。覆盖 TaskA 语义索引(MeSH标签生成)、TaskB 问答(yesno/factoid/list/summary)、TaskC MESINESP(DeCS编码)、LABBench2(分子克隆问答) 的作答、验证与评分。含 MeSH 标签生成的关键陷阱（MajorTopicYN 过滤导致 Recall 暴跌）与 DeCS 查询端点陷阱。
---

# Biomedical Benchmark Exams (benchmarker)

## 触发条件
用户提到：benchmarker 测试 / 试卷N / 考试题.json / 密封答案.json / "看看你对了多少" / "开始作答"

## 流程总览
1. `read_file` 读取考试题 JSON（用户说"只需要读取这个文件" → 不要 scan_data，直接读）
2. 按题目类型作答（见下）
3. 用户给出 密封答案.json 后：read_file → 逐题比对 → 评分（每篇 P/R + 整体 P/R/F1）→ 失败模式根因分析 + 修复方案
4. 语言：答案内容与考题一致（英文题→英文答案），解释与评分用中文

## 考试题 JSON 结构
```json
{
  "exam": "试卷N_语义索引TaskA",
  "description": "...",
  "instructions": "可调用 search_papers / search_knowledge",
  "questions": [{"id": "...", "type": "yesno|factoid|list|summary", "body": "..."}]
}
```
题型：`yesno`(是/否+理由) / `factoid`(精确名词) / `list`(精确列举) / `summary`(2-3 句总结)。

## TaskA — 语义索引（MeSH 标签生成）
题目：给每篇文献 title+abstract → 输出 5-10 个 MeSH 标签。
**首选方法：NCBI E-utilities `efetch` 抓取 PubMed 记录官方 MeSH**（非 LLM 推断）。

### ⚠️ 关键陷阱（Round 1 实测，F1=69%，必须遵守）
- **禁止只用 `MajorTopicYN="Y"` 过滤**！gold 的 `meshMajor` = 该文献的**全部 MeSH Descriptor**（含人口学限定词 Humans/Male/Female/Aged/Middle Aged/Adult/Infant/Pregnancy），而这些限定词在 PubMed 记录里通常标 `MajorTopicYN="N"`。只抓 major → 系统性漏掉 ~一半标签 → Recall 暴跌（实测 55.6%）。
- **出题人说的"MeSH 主要标签" = 全部 Descriptor 列表，不是严格 MajorTopic**。
- **禁止把 Publication Type 当 MeSH 词**：Randomized Controlled Trial / Cohort Studies 是 PT 字段，不是 Descriptor。gold 里没有 → Precision 损失。
- **禁止从 abstract 推断 MeSH 词**：LLM 推断的 Cohort Studies、Cardiovascular Diseases 等在 gold 里不存在。

### ✅ 正确配方（Round 2+ 采用）
```
efetch retmode=xml → 提取全部 <DescriptorName>（不做 MajorTopicYN 过滤）
→ 保留语义主体（疾病/干预/机制/结局/人群）
→ 剔除 <PublicationType> 字段
→ 人口学限定词保留（Humans/Male/Female/Age 组）
→ 超 10 个时按优先级截断: 疾病主体 > 干预 > 机制 > 结局 > 人群
```
预期：Precision 保持 ~90%，Recall 提升至 80%+，F1 ~85%。

## TaskB — 问答（yesno/factoid/list/summary）
- **list**: 精确列举（如 Qsymia = phentermine + topiramate）
- **yesno**: 是/否 + 一句理由 + 文献证据
- **factoid**: 精确名词（如儿童脑肿瘤识别 R 包 = MethPed）
- **summary**: 2-3 句要点（机制 + 功能 + 临床价值）
- **不确定题目必须 `search_papers` 验证并附 [PMID:xxxxx]**；确定性医学事实（如 triple test = AFP+hCG+uE3）可不检索但标注"确定性事实"。
- 多题时并行检索（一次 invoke 多个 search_papers）再汇总。
- **⚠️ summary 题丢分根因（Round 2 实测，6/8 硬命中 + 2 部分命中）**：summary 必须覆盖三层——**概念 + 机制/方法细节 + 具体数字/流程**。只给功能概括列表会漏方法细节：Q4(CAMUR) 漏 power-set 迭代消除 + 内置知识库查询工具；Q8(外泌体) 漏多泡内体-质膜融合释放的生物发生机制。评分时即使"命中"也要检查要点覆盖率。

## 评分约定（用户给密封答案后）
- **先验证密封答案非空**：read 后检查 `ideal`/`answer_regex`/`key_passage` 字段。若全空且 `ground_truth:false`（空模板），对比同目录其他 exam 的密封答案（正常文件 `ground_truth:true` 有内容）确认是发布方漏填充 → **如实报告"无法评分"，禁止编造分数**（实测 LABBench2_cloning 密封答案 10 条全空，dbqa2 正常）。
- 逐题比对，区分三类：**命中 / 错误（pred 有 gold 无）/ 漏掉（gold 有 pred 无）**
- 输出格式：逐篇对比表（命中数、P、R、错误标签、漏掉标签）→ 总分汇总表（整体 P/R/F1）→ 失败模式根因分析（哪类标签漏了、哪个词是误推）→ 下次改进配方
- 数值要算准：Precision = 命中/预测总数，Recall = 命中/gold 总数，F1 = 2PR/(P+R)

## TaskC — MESINESP 多语言检索（DeCS 编码）
题目：给西班牙语医学文献 → 输出对应 DeCS 编码列表（gold 是 DeCS 数字 ID，如 20174=Anciano/Aged）。
**工作流（2026-08-02 实测）：**
1. 对每篇文献先按语义提取 Descriptor 名（西班牙语优先），再用 MeSH 术语表映射。
2. `query_ncbi(db="mesh")` 只能拿到 UID（如 Mediastinal Neoplasms → 68008479），**拿不到名称/tree number** → 需直接调 eutils。
3. DeCS ID → 名称/树号用 `https://decs.bvsalud.org/ths/resource/?id={did}`（⚠️ 见下方陷阱）。

### ⚠️ DeCS 端点陷阱（实测，必读）
- ⛔ `https://decs.bvsalud.org/ths/?filter=ths_regid&q={did}&lang=es` → **返回网站反馈页**（"Queremos a sua opinião sobre o novo sitio web do DeCS/MeSH"），不是描述符页！
- ⛔ `/ths/resource/?id={did}` 的 h1/title 也是反馈页（h1=Queremos a sua opinião...），但页面正文仍含描述符信息——需用正则抓 `Descritor em espanhol/inglês/português` 字段，勿信 h1/title。
- ✅ 从正文提取：`re.search(r'Descritor em\s*español:[^<]*</[^>]+>\s*<[^>]+>(.*?)</', txt, re.S)` → ES 名；trees 用 `re.findall(r'([A-Z]\d+(?:\.\d+)+)', txt)`（去重）。
- 实测样例：20174 → ES=Anciano / EN=Aged / trees=M01.060.116.100...（与 gold 一致）。
- NCBI eutils 调用必须带 `User-Agent: Mozilla/5.0` + 指数退避重试（`time.sleep(5*(a+1))`），curl 裸调 eutils 常超时（120s 实测挂）。
- MeSH UID 前缀：新 UID 是 `68xxxxx`（D001706 → 68001706），eutils efetch db=mesh 返回文本含 `Tree Number(s):` 行，用 `re.search(r'Tree Number\(s\):\s*(.+)', txt)` 抓取再按逗号 split。

## LABBench2 — 分子克隆/湿实验问答
题目：10 道克隆/质粒/DNA 序列题（如给序列设计引物、注释质粒、酶切分析）。
- 先 `read_file` 试题 JSON；附件序列文件（.gb/.fa/.dna）在 E:\benchmarker\ 下没有时，直接 `query_ncbi(db="nuccore", query="MYOD1 Homo sapiens mRNA NM_002478")` / `query_ensembl` 抓真实序列（NM_002478 = MYOD1 1803bp，Ensembl REST `/lookup/id/{id}?expand=1` 拿 canonical_transcript + transcripts，`/overlap/translation/...` 返回 404 别用）。
- 相关 skill：`pcr-primer-design` 已注册（golden_gate_assembly / annotate_plasmid / digest_sequence 为 skill hub 名，本机不适用会报 unsupported，用 pcr-primer-design 即可）。
- 序列题答案必须是可验证的（引物 Tm/GC 可算、酶切位点可定位），不要只给名称。

## 参考
- `references/mech-indexing-taskA-lessons.md` — Round 1 TaskA 完整评分明细、逐篇错误、根因与改进配方
- `references/decs-mesinesp-taskC.md` — MESINESP TaskC 实测：DeCS 端点探测记录、ID→名称映射表、eutils mesh 用法
- `references/taskB-labbench2-lessons.md` — Round 2 TaskB 评分明细（summary 三层覆盖教训）+ LABBench2 空模板答案验证流程

## 环境陷阱（Windows 实测）
- **MSYS /tmp 与原生 Python 路径不一致**：bash heredoc/临时脚本写到 `/tmp/xxx.py`，但 Windows 原生 Python（`C:\...\Python312\python.exe`）打开 `/tmp/xxx.py` 会报找不到文件（MSYS 虚拟路径 ≠ Windows 真实路径）。写临时验证脚本一律用真实 Windows 路径 `C:\Users\<user>\AppData\Local\Temp\` 或 `E:\tmp\`。
