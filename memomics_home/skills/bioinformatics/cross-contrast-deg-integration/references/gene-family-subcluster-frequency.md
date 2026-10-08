# 按基因家族出「亚群频次」汇总 —— 完整配方与 HSP 案例（2026-10-05）

## 何时用
用户已有多套算好的 DEG，跳过交集直接点名一个**基因家族/前缀**要频次表：
- 「帮我统计一下 HSP 开头的基因，在衰老、糖尿病、年轻运动、老年运动、老年糖尿病运动出现多个亚群共享的基因」
- 「比如 sheet1(衰老)，HSPA9 出现频率 5 次，等等。五个比较组都统计上变成五个 sheet」
- 「然后再统计逆转衰老、逆转糖尿病、锻炼共同的」

这是**描述性汇总**：不做检验、不重算 DEG。判据与措辞边界见 SKILL.md §七。

## 输入源表结构（本例，供复用）
`D:/肌肉锻炼/DEG_file/DEG_fdr05_coef025_5contrasts_formatted.xlsx`
- 5 个 sheet：`Aging` / `DM` / `Y_EX` / `O_EX` / `DM_EX`，**每表已筛过** FDR<0.05 且 |coef|>0.25
- 16 列：`gene, celltype, regulation, coef, se, z, p, fdr, direction, n_cells, nRUV_used, method, comparison, coef_D, p_D, fdr_D`
- **亚群列名是 `celltype`**（不是 subcluster）；10 个 MF 亚群：LRP1B+(I), OTUD1+(I), OTUD1+(II),
  Pure Type I, Pure Type IIA, Pure Type IIX, RP_high(I), RP_high(II), RSS, Specialized MF
- 各表行数：Aging 23,178 / DM 311 / Y_EX 115 / O_EX 1,846 / DM_EX 246
- `gene × celltype` 重复 = **0** → 频次直接等于亚群个数，无需去重

配套交集/逆转表在 `task4/results/`（自带 `*_subclusters` 分号分隔列，`split(";")` 计数即可）：
`table3a_reversal_aging_up_to_down.csv`(785)、`table3b_..._down_to_up.csv`(27)、
`table4a_reversal_DM_up_to_down.csv`(13)、`table4b_..._down_to_up.csv`(5)、
`table2_exercise_shared_genes_detail.csv`(9)、`table6_overlap_significance.csv`（期望值/fold/p）。

## 输出布局（17 sheet，可直接照搬）
```
00_总览                 每比较组：总行数 / 亚群数 / 家族行数 / 基因数 / 基因清单
Aging, DM, Y_EX, O_EX, DM_EX   ← ①五个比较组频率表（核心交付，用户点名要的「五个 sheet」）
06_跨比较组矩阵          基因 × 比较组 频次 + n_comparisons_sig
逆转衰老_Up2Down(n=785) / 逆转衰老_Down2Up(n=27) / 逆转糖尿病_Up2Down(n=13) / 逆转糖尿病_Down2Up(n=5)
锻炼共同_3组运动
09_三组共同HSP          in_逆转衰老 / in_逆转糖尿病 / in_锻炼共同 / n_sets
10_扩展口径敏感性        主口径 vs 扩展口径的基因数/行数/新增基因
11_逆转_扩展口径
12_口径敏感性结论        两口径下并集规模与三组共同交集是否改变
13_图注与方法口径        可直接粘贴的图注/方法段
```
图：`figures/HSP_subcluster_frequency_heatmap.{png,svg,pdf}`（基因 × 比较组热图，格内标数字，0 遮白/浅灰）

## 脚本要点
- `scripts/hsp_subcluster_stats.py` —— 主统计（5 组频率 + 跨组矩阵 + 逆转筛查 + 交集）
- `scripts/hsp_subcluster_frequency_figure.py` —— 频率热图（**轴标签纯英文**，否则 DejaVu Sans 刷 glyph 警告 + 方框）
- `scripts/hsp_extended_scope_sensitivity.py` —— 扩展口径敏感性 + 图注模板；
  追加 sheet 用 `ExcelWriter(mode="a", if_sheet_exists="replace")`，不改动已有 sheet

## 本例结果（供对照，勿重跑）
- 全局并集（`^HSP`）= **12** 基因
- **Aging**：11 基因 / 44 行 **全 Up**；频次 HSPB8(6) > HSPA9(5)=HSPA4(5)=HSPD1(5)=HSP90AA1(5)
  > HSPB1(4)=HSP90AB1(4)=HSPE1-MOB4(4) > HSPA1A(2)=HSPB2(2)=HSPE1(2)
- **O_EX**：4 基因（HSPB1 8 亚群↑、HSPB7 3↑、HSPA9 1↓、HSPD1 1↓）
- **DM_EX**：2 基因（HSPB1 3↑、HSP90AA1 1↑）；**DM / Y_EX 各 0 个**
- **逆转衰老 785**：仅 HSPA9、HSPD1（5 亚群 Aging↑ → 1 亚群 Ex_Old↓）
- 逆转衰老 27 / 逆转糖尿病 13+5 / 锻炼共同 9：**0 个 HSP**
- **逆转衰老 ∩ 逆转糖尿病 ∩ 锻炼共同 = 空集**（主口径与扩展口径下均如此）
- 扩展口径 `^HSP|^DNAJ[ABC]|^HSPH1`：Aging 11→**36**（新增 25 个 DNAJ）、O_EX 4→7、
  逆转衰老 785 新增 DNAJB12 / DNAJB2 / DNAJC3

## 辩论裁决要点（L1 · modify / 置信中）
1. 频次 = 显著亚群**计数**，不是效应量、不是检验结果，受细胞数/检出率/功效影响 → 必须写进图注
2. `^HSP` 是命名口径，**不等于完整 HSP 家族**（HSP40 = DNAJ 前缀未含）→ 要么跑扩口径敏感性，要么结论限定「本口径内」
3. Aging 全 Up 在排除全局偏移前不得作生物学结论（该表 Up 22,709 / Down 469、coef 中位 0.301 贴阈值）
4. HSPB1 跨 3 比较组显著 → 只可写「跨组频次最高」，不可写「核心 HSP」（缺效应量/独立验证）

## 平台坑
- 纯表格任务不出图 → `rail_review(post)` 以 `figure_count=0` 判不通过。
  解法与配套的 matplotlib CJK 方框坑 → `platform-execution-pitfalls` 的 `references/post-review-figure-gate.md`

## 相关 skill
- `functional-enrichment` / `enrichment-conclusion-validation` —— 拿到小列表后要不要跑 ORA、GSEA pre-ranked 口径
- `deg-analysis` —— 上游 DEG 怎么算（本文件不重算）
- `gene-set-overlap-analysis` —— 韦恩/交集图与交集显著性检验