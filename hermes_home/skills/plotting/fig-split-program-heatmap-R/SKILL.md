---
name: fig-split-program-heatmap-R
description: >-
  骨骼肌肌纤维 AUCell 程序打分矩阵热图（base graphics 零依赖 R 版）：18 程序 × 6 组 / 5 效应(Cohen's d) / 10 亚群三型版式，
  RdBu_r 双色带 + 行分组色条 + 亚群 45° 标签，一次出 FigA1/A2/A3 + FigB1/B2/B3 六图 × PNG/PDF/SVG/TIFF @300dpi。
  触发词："fig_split_v10 的 R 版" / "18 程序打分热图出 R 版" / "6组×亚群矩阵热图 R" / "五效应 Cohen's d 热图 R" / "RdBu_r 双色热图 base graphics"
metadata:
  hermes:
    category: user-skill
    tags: [user, plotting, heatmap, base-graphics, RdBu, aucell]
source: user
verified: 2026-09-15
---

## 使用场景

- 用户给了 Python matplotlib 手绘矩形版矩阵热图脚本（`fig_split_v10.py`），要求 **转成 R**（不换图型、不改版式、颜色必须对上）。
- 需要 **18 个通路/程序 AUCell 打分** 在三种维度上的矩阵热图：
  1. 6 个实验组（Y_Pre/Y_Post/O_Pre/O_Post/OD_Pre/OD_Post）
  2. 5 个效应轴（Aging / T2D / ExYoung / ExOld / ExT2D，Cohen's d + FDR 星号）
  3. 10 个亚群（不分 type，行内 z-score）
- 触发词示例："把这个出图脚本改成 R" / "用 R 出那 6 张程序打分热图" / "FigA2/FigA3 的 R 版"

## 输入要求

| 输入 | 格式 | 说明 |
|------|------|------|
| 细胞级打分表 | CSV（`MF_AUCell_meta.csv` 型） | 需含 `type`（6 组）、`annotation_L3`（10 亚群）、`samplename`，以及 `<程序名>_AUC` 列（无 `_AUC` 后缀时自动回退原名） |
| 五效应统计表 | CSV（`effect5_d_v2.csv` 型） | 列：`effect`(Aging/T2D/ExYoung/ExOld/ExT2D)、`sub`、`score`、`d`、`q` |
| 程序分组 | 脚本内 `PROGRAM` / `PROG_GROUPS` | 18 程序按功能轴分 5 组（见下），身份打分另 4 个单组 |

⚠️ 脚本头部三个路径常量（`OUT` / `META_CSV` / `EFF_CSV`）需按新项目改；输出目录务必用**独立子目录**（如 `figures/R_version/`），否则会覆盖同名 Python 版图。

## 输出

- 6 图 × 4 格式 = 24 文件：`FigA1/A2/A3_program_*` + `FigB1/B2/B3_identity_*` 的 `.png/.pdf/.svg/.tiff`
- 300 dpi；像素尺寸 4950×2520（FigA2 型）/ 2700×3600（FigA3 型）/ 2700×1800（FigA1 型）
- 配色：`RdBu_r` 11 锚点线性插值 256 级 LUT；`TwoSlopeNorm(-3,0,3)`（效应）/ `(-2,0,2)`（行 z-score）
- 行分组色条：Metabolic #2C7FB8｜Structural #7BA05B｜Regeneration #F4A261｜Stress-Inflam #D64550｜Atrophy-Fibrosis #8C5FA8｜Identity #6A6A6A
- 无白色格线（`CELL=1.0` 紧贴）、组间隙 0.2、面板间距 1.8、亚群标签 45° 贴底

## 验证状态

- **验证日期**：2026-09-15；数据来源：真实（`E:/骨骼肌锻炼/MF_AUCell_meta.csv` 508,661 细胞 × 58 列，R 4.5.3）
- 与 Python 原版逐项比对结果：

| 核验项 | 结果 |
|---|---|
| 矩阵口径 max\|Δ\| | Z6=1.0e-14 / ZS=1.4e-14 / d=5.1e-15 / q=5.6e-16 |
| 取色 RGB 单通道差 | 0（-2→2 全范围 13 抽样值全等） |
| 色块几何 | 列边界/pitch 逐项相同（49.0 px、138.0 px） |
| 像素尺寸 | 完全一致 |
| 残余差异 | 仅字体族（R=Arial，原版=DejaVu Sans，系统未装） |

- **修复记录**：
  1. `par(xaxs="i", yaxs="i")` 必须显式设 —— R 默认 `"r"` 会给坐标范围外扩 4%，导致所有色块被压缩约 7%、整版错位（实测列 pitch 138→128 px）。
  2. 色表索引必须写 `floor(b*256)+1` —— 写 `255` 会整体偏一档（±1~2/255）。
  3. 展平顺序：Python 是"亚群最快"，R `as.vector` 是列优先（第 1 维最快）→ 聚合矩阵必须取 **亚群 × type** 维度才等价。

## 来源

- `user`：由用户提供的 Python 脚本 `fig_split_v10.py` 1:1 复刻为 R（base graphics 零第三方依赖，不引 ComplexHeatmap/pheatmap —— 其几何系统与 matplotlib 手绘矩形不同，反而难对齐）
