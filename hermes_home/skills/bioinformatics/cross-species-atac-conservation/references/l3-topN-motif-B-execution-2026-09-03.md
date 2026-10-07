# L3-B 跨物种 motif 富集执行（Top500 按 r 口径，2026-09-03 实测）

## 触发场景
L3 需要 motif 富集输入。**A 口径（显著 tiles）在猴侧不可行**：猴 q<0.1 显著 tile = 0 个（20 样本 + FDR 严格，530 万次检验必然 0），人侧也只剩 22/28 个功效不足。**用户拍板 B：按连续年龄 Pearson r 排序取 Top500 Up/Down**（与 L3 v2 连续年龄逻辑一致）。

## 输入（坐标已是真实碱基坐标，勿再换算）
| 文件 | 行数 | 坐标格式 |
|---|---|---|
| `E:/专利/human_ageDA_all.csv` | 5,555,247 | `chr1,793001,793500`（hg38 真坐标） |
| `E:/专利/monkey_ageDA_all.csv` | 5,296,656 | `NC_088375.1,20001,20500`（T2T-MFA8 真坐标） |

⚠️ **坐标状态核实**：本会话实测当前文件 start/end 是**真实碱基坐标**（2026-09-03 早些时候已修 tile 编号→真坐标，`chr1,793001,793500`）。**禁止看到 Common Issues 的 tile 编号条目就再换算一次**——换算只适用于未修复的导出。核实法：真坐标 start 在 Mb 量级（如 793001）；tile 编号是小整数（如 1587）。跑前 `head -2` 看格式。

## Step 1 — 提取 Top500（Python，秒级）
```python
df = pd.read_csv(path, usecols=["chr","start","end","r"])
df.nlargest(500, "r").to_csv(up_csv, index=False)    # r 最大 = 年龄↑可及性↑
df.nsmallest(500, "r").to_csv(down_csv, index=False) # r 最小 = 年龄↑可及性↓
```
实测 r 范围：human up500 ∈[0.587,0.743], down500 ∈[-0.771,-0.609]；monkey up500 ∈[0.718,0.893], down500 ∈[-0.878,-0.741]（猴效应更强）。产物 `l3_topN_{human,monkey}_{up,down}500.csv`。

## Step 2 — motif 富集（R 4.5.3 + E:/R-libs）
脚本 `scripts/l3_topN_motif.R`（本会话产物）：
- JASPAR2020 CORE `species=9606`（633 motifs），`matchMotifs(out="scores")`
- 背景：每侧用各自 Up500 染色体分布随机抽 2000 tile（GC 匹配，Phase6/p3_l1 同法）
- rank：`fc = fg_mean/bg_mean`，`tf_map <- sapply(motifs, m@name)` 映射 TF 名
- 猴侧：`nc2chr` 映射 + OOB 过滤（`end <= seqlengths(rheMac10)`）— 实测 500→446（Up）/477（Down），滤 ~5-11%

⛔ **坑：`could not find function "assay"`**——独立 motif 脚本只 load JASPAR2020/motifmatchr 时 `SummarizedExperiment` 不会被传递加载（p3_l1_motif.R 能跑是因为它还 load 了 ArchR，间接拉了 SE）。**修复：脚本显式 `library(SummarizedExperiment)`**。

## Step 3 — 跨物种 Jaccard
脚本 `scripts/l3_topN_compare.R`：top N 按 fc、tf 名去 `::` 后缀 → `up_up / dn_dn / up_dn / dn_up` × topN∈{10,20,30,50} → `l3_topN_jaccard.csv`。

## 实测结果（权威）
| topN | 人Up vs 猴Up | 人Down vs 猴Down | 交叉 |
|---|---|---|---|
| 10 | 0.056 | 0.000 | 0.053-0.056 |
| 20 | 0.121 | 0.026 | 0.026-0.057 |
| **30** | **0.213** | **0.034** | 0.071-0.118 |
| 50 | 0.155 | 0.053 | 0.064-0.141 |

- 人Up500 top：HOXC8/ELK1/FOSL2::JUND/FOSL1::JUN/MAFK/ATF7/VENTX/ELK3/HOXA9（AP-1 家族 + HOX）
- 人Down500 top：CTCF/EMX1/RFX2/DLX5/NFIC（CTCF/同源盒/RFX）
- 猴Up500 top：ZFP57/EMX1/XBP1/ATF6/JUNB/HOXA9/HOXB2/HOXC4/HOXD3（UPR + HOX）
- 猴Down500 top：HOXA9/ZBED1/JUNB/E2F4/TP63
- **共享 top30**：HOXA9, FOSB, JUNB, GATA3, MAFK, ATF7, HOXA1, CREB3, CREB3L4, FOSL1

## 解读铁律（辩论 need_more_info / low 裁决）
- **上调方向跨物种 TF 富集保守性 > 下调**（top30 0.213 vs 0.034）→ 与 L2⑤ / M3"上调保守、下调分歧"模式一致，互相印证。
- Top500 motif 富集是**预测层证据**——专利只能写"跨物种衰老上调程序 TF 富集部分保守（Jaccard 0.21）"，**禁止写"证实 TF 结合保守"**；直接证据（ChIP-seq / footprint / co-accessibility）仍缺失，答辩要主动说明。
- 猴侧 XBP1/ATF6（UPR）可能受组织应激/死后间隔混杂，勿过度解读为衰老特异。

## 下一步接 CRECS
`p4_crecs_scores.py` 旧 L3 代理值（Old 0.020 / Young 0.070）→ **换本次真实 Jaccard top30 up_up=0.213**（上调）与 dn_dn=0.034（下调）作为 L3_score，重算 A/B/C/D 分类。