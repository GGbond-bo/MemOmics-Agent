# 混合效应模型 + 交叉验证预测：三口径 + 年龄断层约束（2026-09-04）

> 用户问「能不能做 species×age 混合效应模型 + 交叉验证预测」时先读本文件。
> 核心教训：CV 有三个完全不同的含义，混为一谈会导致做出来不知道在证明什么。

## 交叉验证预测的三种口径（必须先定，再开工）

| 口径 | 做什么 | 证明什么 | 数据要求 | 关键判断 |
|---|---|---|---|---|
| ① 同物种 CV | 猴内 leave-one-out 预测年龄 | 年龄信号存在 | 单物种 per-individual | ⚠️ 无关「可替代性」，不能当专利证据 |
| ② 跨物种方向迁移 | 猴衰老方向（r 符号）→ 验人实际方向 | **可替代性（专利真正核心）** | 两侧效应方向即可 | ✅ 用现成 `m3_conservation_gene.csv`（16030 基因 r_human/r_monkey）即可，不必上 per-individual |
| ③ 跨物种年龄值迁移 | 猴训 age 回归器 → 人预测年龄 | 跨物种泛化 | 两侧 per-individual 矩阵 + ortholog 对齐 | 🔴 被年龄断层外推卡死，别硬卷 |

**推荐的落地顺序**：先做 ②（数据现成、直接回答专利命题），③ 留到有足够年龄覆盖时再做。

## 硬约束：食蟹猴年龄断层（做 ③ 前必查）

20 只猴真实连续年龄分布（2026-09 实测）：
`5(×4)、10/11/12、22/23(×6)、28/29/31(×6)` —— **中间 13–21 岁一只都没有**。

→ 做年龄回归 CV 时中间段是纯外推，预测必然差。这不是模型问题，是数据分布决定的。
不要在年龄值迁移上反复调参，先做方向迁移（②）。

## 混合效应模型需要 per-individual 矩阵，不是聚合 r 值

`species×age` 交互项的 LMM（lme4::lmer，pseudobulk per-individual 防伪重复）需要两侧 per-individual 数据：
- 猴侧：`E:/专利/file/monkey_tile_matrix_samples_x_tiles.rds`（20 猴 × 608万 tile 稀疏矩阵，**colnames 空**，靠 `monkey_tile_coords.csv` 行顺序对齐）
- 人侧：`E:/专利/P3_L2_data/l2_gene_individual_matrix.rds` + `E:/专利/P3_L1_data/file/human_GroupSE_byindividual.rds`

若手上只有每个物种一个「聚合 r 值」（如 m3_human_gene_r.csv / m3_monkey_gene_r.csv 的 r_mean），则只能做效应量相关性（v4b 的 Spearman ρ），**不能 fit 真正的混合效应**——先跟你确认人侧 per-individual 矩阵是否本地齐全。

## 相关文件速查

- `m3_conservation_gene.csv`：16030 基因，列 `macaque_gene_id,human_gene_id,symbol,r_human,r_monkey,n_tiles_h,n_tiles_m`（方向迁移 ② 的直接输入）
- `m3_human_gene_r.csv`（16105 基因）/ `m3_monkey_gene_r.csv`（38991 基因）：每基因聚合 r_mean
- `v4b_gene_substitutability_table.csv`：16031 基因的可替代性四分类标注（保守可替代 / 分歧 / 单侧特异 / 不显著）

## R/Python 语法坑（反复踩）

- Python：`exec(open('x.py', encoding='utf-8').read())`
- R：用 `source('x.R')`，**不是** `exec(open().read())`（那是 Python 语法，R 里会报错）