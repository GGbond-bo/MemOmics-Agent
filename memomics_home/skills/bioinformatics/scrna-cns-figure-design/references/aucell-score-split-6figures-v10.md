# AUCell 打分拆分交付 v10（6 图架构）— 2026-08-16 用户拍板

数据：`E:/骨骼肌锻炼/MF_AUCell_meta.csv`（508,661 细胞，22 打分列带 `_AUC` 后缀，
6 type：Y_Pre/Y_Post/O_Pre/O_Post/OD_Pre/OD_Post，10 亚群 annotation_L3）
聚合：`results/*/agg_sample_v2.csv`（480 行 = 48 样本 × 10 亚群）
效应：`results/*/effect5_d_v2.csv`（1100 行，列 score/sub/effect/d/p/q）

## 6 图清单（全部 PNG+PDF+SVG 300dpi）

| 文件 | 行 | 列 | 值 |
|---|---|---|---|
| FigA1_program_6groups | 18 程序 | 6 type 面板 × 10 亚群 | 行内 z-score ±2 |
| FigA2_program_5effects | 18 程序 | 5 效应面板 × 10 亚群 | Cohen's d ±3 + `*` FDR<0.05 |
| FigA3_program_subcluster | 18 程序 | 10 亚群 | 行内 z-score ±2 |
| FigB1_identity_6groups | 4 身份 | 6 type × 10 亚群 | z-score |
| FigB2_identity_5effects | 4 身份 | 5 效应 × 10 亚群 | Cohen's d |
| FigB3_identity_subcluster | 4 身份 | 10 亚群 | z-score |

## 打分清单

- **18 程序**（按 5 功能轴）：Metabolic(7)=scoreOxPhos/Glycolysis/FattyAcidMetabolism/AMPK_PGC1a/Adipogenesis/scoreInsulin/mTORC1；Structural(1)=scoreSarcomeric；Regeneration(3)=scoreRegMyon/Denervation/Autophagy；Stress-Inflam(5)=scoreSenMayo/scoreStress/scoreTNFA/scoreInflammatory/scoreROS；Atrophy-Fibrosis(2)=scoreAtrophy/Fibrosis
- **4 身份**：scoreI/scoreII/scoreIIa/scoreIIx（验证注释用，不进主热图）
- ⚠️ 2026-08-16 版保留 mTORC1（此前讨论过删，用户 18 程序列表含它，以用户列表为准）

## 关键参数（继承 v7/v8 已验收样式）

- `CELL=1.0` 格子填满（**无白色间隙**）；行分组间隙 0.2；`PANEL_GAP=1.8`
- 亚群标签底部 45° `y=-0.15, ha=right, va=top`；type/效应标题顶部（带完整公式）
- 行标签左侧**完整名**（禁缩写）；左侧功能分组色带
- `subplots_adjust` 手动布局——**绝不用 tight_layout**（与 add_axes 颜色条不兼容 → PNG 空白）
- 数据层 z-score 用 numpy：`(X.values - mean(axis=1,keepdims=True))/std(axis=1,ddof=0,keepdims=True)`（避免 pandas apply/MultiIndex 广播坑）

## 实现级坑

1. **GROUP_COLORS 必须有 "Identity" 键**：`draw_group_stripes` 对身份打分分组时
   `GROUP_COLORS['Identity']` KeyError——色字典加 `"Identity": "#6A6A6A"`。
2. **`_AUC` 后缀**：pivot 前 `df['score'] = df['score'].str.replace('_AUC$','',regex=True)`；
   groupby 聚合后 `sub_agg.columns = score_names` 去掉后缀再转置。
3. **Panel 数据切片**：`V[:, ei*n_sub:(ei+1)*n_sub]` + 行 `score_names.index(name)`——
   reindex 到固定 (effect, sub) 列序后再 values。
4. **z-score 不要卡真实分数范围**：用户明确否掉"真实 AUCell 分数 0-0.2 映射"
   （"你把值卡死在0.2,其他的怎么办呢？还是z-score吧"）——低值大片被压成同色。
5. **跑完必须交付**：改参数 → 同一轮跑脚本出图 → 确认时间戳刷新 → 报告产物路径。
   用户会核对文件时间戳（"没有更新啊"），只描述不执行 = 无效。
