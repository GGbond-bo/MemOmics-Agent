# Denervation 基因集语义污染 — 实测案例（2026-08-14）

## 现象
五效应矩阵热图（Fig1_five_effects_matrix）里 **Denervation 打分在 Aging/ExYoung/ExOld/ExT2D 四个轴、全部 10 个亚群都是正效应**（d +0.3 ~ +1.4）。用户质疑："不至于衰老，10 个亚群都升高去神经吧？"

## 诊断工具 = 6 组原始打分热图（不做效应）
用户要求"出一个 6 个组的打分，不做效应，就是六个组的打分"。做法：
- 样本级聚合（samplename × annotation_L3 均值，479 行）→ 6 组（Y_Pre/Y_Post/O_Pre/O_Post/OD_Pre/OD_Post）× 10 亚群 = 60 列矩阵
- 行 = 22 打分（按功能轴分组：Metabolic 蓝 #4575B4 / Fiber Identity 黄 #F4B942 / Senescence 红 #D64545），列 = 6组×10亚群（60 列），行内 z-score
- 组色带（顶部）：Y_Pre #74ADD1 / Y_Post #2C7BB6（浅蓝→深蓝），O_Pre #FDAE61 / O_Post #F46D43（浅橙→深橙），OD_Pre #FC8D59 / OD_Post #D73027（浅红→深红）——Pre 浅 / Post 深
- 配色：RdBu（#2166AC→白→#B2182B）z-score ±2.2 截断
- 出 PNG(300dpi) + PDF + SVG，文件 `Fig6_6groups_raw_scores.*`

## 实测数据（Denervation 原始 AUC 均值，非 z-score）
| 组 | mean | range |
|----|------|-------|
| Y_Pre | 0.0232 | [0.0169, 0.0358] |
| Y_Post | 0.0285 | [0.0195, 0.0472] |
| O_Pre | 0.0329 | [0.0221, 0.0663] |
| **O_Post** | **0.0650** | [0.0492, 0.1134] ← 几乎翻倍 |
| OD_Pre | 0.0310 | [0.0224, 0.0531] |
| OD_Post | 0.0603 | [0.0463, 0.1014] |

**关键**：不是"所有亚群本来就高"（年轻组才 0.023），而是**运动后暴增**（O_Post 翻倍）。ExOld 效应 = O_Post − O_Pre = +0.032 → 全亚群一致正效应。

## 根因 = 基因集语义污染（再生程序误捕）
Denervation 基因集 11 基因：CHRNA1, CHRNG, CHRND, MYOG, RUNX1, SCN5A, KCNMB1, NCAM1, MYH8, NGFR, GAP43。
其中 **MYOG / RUNX1 / NCAM1 / MYH8 同时是肌肉再生核心标志物**（与 RegMyon 再生肌核基因集重叠）。
运动诱导肌肉重塑 → 卫星细胞激活、肌核再生上调 → 这些"再生基因"被 Denervation 集捕获 → 打分虚高。

## 结论与修正
- 运动组 Denervation 打分升高 = **假信号（实为再生程序）**，不能讲"运动加重去神经支配"
- Aging 轴全亚群正效应里也掺了再生/慢肌化成分，需谨慎
- 发表修正：① 剔除与 RegMyon 重叠的 4 基因（MYOG/RUNX1/NCAM1/MYH8）重算；② 或正文注明局限

## 通用原则（可复用）
**任何打分出现"全亚群 × 多效应轴"一致方向的反直觉模式时，先怀疑基因集语义污染而非生物学真信号。**
诊断三步：
1. 出 6 组原始 AUC 均值（不做效应、不做 z-score）——区分"基线本来就高" vs "某组暴增"
2. 查基因集构成：与已有程序重叠（RegMyon/Atrophy/Sarcomeric）、方向相反基因（SCN4A 去神经下调 vs SCN5A 上调）、非特异性管家基因
3. 用文献验证 marker 语义（NCAM1 去神经经典 marker，但也是再生标志——一个基因可以属于多个生物学程序，基因集打分无法区分）

## 六组原始打分热图通用配方（诊断型，非发表主图）
- 用途：回答"这个打分为什么高/低"、"各组绝对水平如何"（效应热图只给差值，丢失绝对水平）
- 行 z-score 保留"相对升降"信息；但**读单一行时用原始均值表**（z-score 会抹掉绝对尺度差异）
- 亚群顺序：RSS / Specialized MF / Pure Type I / Pure Type IIA / Pure Type IIX / LRP1B+(I) / OTUD1+(I) / OTUD1+(II) / RP_high(I) / RP_high(II)（项目固定顺序）
- 打分顺序：Metabolic(11) → Identity(4) → Senescence(7)，与效应矩阵一致
