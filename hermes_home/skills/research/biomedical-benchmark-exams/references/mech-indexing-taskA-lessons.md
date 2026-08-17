# TaskA MeSH 索引 — Round 1 实测评分与改进配方（试卷1）

## 结果（2026-08-02，试卷1_语义索引TaskA）
- 预测 44 标签 / 命中 40 / 错误 4 / gold 总 72 标签
- **整体 Precision 90.9% / Recall 55.6% / F1 69.0%**
- Precision 高的原因：答案全部来自 PubMed 官方 efetch（MajorTopicYN=Y 严格过滤）
- Recall 低的原因：人口学限定词系统性被过滤掉 + 抓取字段策略错误

## 逐篇明细
| 文献 (PMID) | 预测/命中 | Precision | Recall | 错误标签 | 漏掉（举例） |
|---|---|---|---|---|---|
| 23479819 (bioluminescence) | 7/7 | 100% | 100% | 无 | 无（完美） |
| 23483174 (OSA 睡眠中心) | 9/9 | 100% | 52.9% | 无 | Aged/Female/Humans/Male/Middle Aged/Hospitals, University/Medicine/Severity of Illness Index |
| 23483175 (母乳喂养肥胖) | 9/10 | 90% | 45% | Randomized Controlled Trial（是 PT 非 MeSH） | Adult/Female/Humans/Male/Infant/Infant Newborn/Pregnancy/Young Adult/Hospitals, Maternity/Intervention Studies/Time Factors |
| 23483176 (戒烟心血管) | 8/9 | 88.9% | 53.3% | Cohort Studies（LLM 推断） | Adult/Aged/Female/Humans/Male/Middle Aged/Prevalence |
| 23483177 (PCI 出血) | 7/8 | 87.5% | 53.8% | Cardiovascular Diseases（LLM 推断） | Aged/Aged 80 and over/Female/Humans/Male/Middle Aged |

## 根因分析（三类失败模式）
1. **人口学/年龄限定词系统性漏掉**（最大 Recall 杀手）：gold 的 meshMajor 含 Humans/Male/Female/Aged/Middle Aged/Adult/Infant/Pregnancy 等 30+ 个（占 72 个总标签近一半）。这些词在 PubMed 记录里通常 `MajorTopicYN="N"`，被 MajorTopicYN="Y" 过滤全部丢掉。
2. **Publication Type 误当 MeSH**：`Randomized Controlled Trial` 是 PublicationType 字段，不是 DescriptorName。
3. **LLM 从 abstract 推断词不在 gold**：`Cohort Studies`、`Cardiovascular Diseases`(文献5) 推断词 gold 中没有。

## 改进配方（已写入 SKILL.md，Round 2+ 采用）
```
efetch retmode=xml → 提取全部 <DescriptorName>（不做 MajorTopicYN 过滤）
→ 保留语义主体（疾病/干预/机制/结局/人群）
→ 剔除 <PublicationType> 字段
→ 人口学限定词保留（Humans/Male/Female/Age 组）
→ 超 10 个时按优先级截断: 疾病主体 > 干预 > 机制 > 结局 > 人群
```

## 补充经验
- 出题人的"MeSH 主要标签" = 全部 MeSH Descriptor 列表，**非严格 MajorTopic 语义**
- efetch 批量抓取建议用 Python urllib/requests（带重试），一次会话抓完所有 PMID 再解析
- 评分数值口径：Precision = 命中/预测总数；Recall = 命中/gold 总数；F1 = 2PR/(P+R)
