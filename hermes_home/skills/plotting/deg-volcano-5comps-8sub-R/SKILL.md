---
name: deg-volcano-5comps-8sub-R
description: >-
  骨骼肌 DEG 五比较组 × 8 亚群火山图（R ggplot2 + ggrepel）：背景灰柱 + 全部基因抖动点 + top5 基因标注
  + y=0 彩色亚群标签块 + p3 主题；14×7 inch @300dpi，8 亚群自定义色板 + 配套文字色，
  支持用户确认的补标补丁（EXTRA_LABELS）。触发词："火山图 R 版" / "5 比较组 8 亚群火山图" /
  "DEG 火山图带亚群标签块" / "volcano 8sub FINAL"
metadata:
  hermes:
    category: user-skill
    tags: [user, plotting, volcano, deg, ggplot2, ggrepel]
source: user
verified: 2026-10-01
---

## 使用场景

- 已有**多个比较组**的 DEG 表（每 sheet 一个对比），要出「一对比一张、图内含 8 个亚群」的火山图。
- 典型场合：同一批样本的多条件 DEG（Aging / DM / 运动前后 5 个对比）横向对比展示。
- 触发词示例："帮我画 5 个比较组的火山图" / "火山图每个亚群一块" / "给火山图补标某个基因"
- ⚠️ 脚本**复刻用户 notebook 原稿样式**（cell#3/#4/#6/#7），非通用火山图模板。

## 输入要求

| 输入 | 格式 | 说明 |
|------|------|------|
| 多对比 DEG 工作簿 | XLSX，**每 sheet 一个对比** | 需含 `celltype`、`regulation`(up/down)、`coef`、`fdr`、基因名列 |
| 数据过滤 | 建议已过滤（如 FDR<0.05 且 \|coef\|≥0.25） | 表内不存在 fdr≥0.05 的行时，脚本会**整类删除「不显著(灰)」类别** |

脚本头部路径常量：

```r
F1 <- "D:/我的下载/DEG_fdr05_coef025_5contrasts.xlsx"   # 优先用户路径
F2 <- "E:/MemOmics-Agent/results/<sid>/task2/results/DEG_fdr05_coef025_5contrasts.xlsx"  # 缺失则会话内同 md5 副本
SRC_FILE <- if (file.exists(F1)) F1 else F2
OUT <- "E:/MemOmics-Agent/results/<sid>/task3/figures"
```

## 参数（用户原稿取值，勿擅改）

| 要素 | 取值 |
|------|------|
| 画布 | `14 × 7 inch` @300dpi（= 4200×2100）。**必须够宽**：标签最大宽 "Pure Type IIA"=1.415 inch @17.1pt(size=6)，8 色块并排每块 1.66 inch > 1.415 → 不重叠 |
| 比较组 | Aging=`Y_Pre_vs_O_Pre`、DM=`O_Pre_vs_OD_Pre`、Ex_Young=`Y_Pre_vs_Y_Post`、Ex_Old=`O_Pre_vs_O_Post`、Ex_DM=`OD_Pre_vs_OD_Post` |
| 亚群顺序 | Pure Type I → IIA → IIX → LRP1B+(I) → RP_high(I) → RP_high(II) → OTUD1+(I) → OTUD1+(II) |
| 亚群色板 | `#2f3084 #76a5d9 #43a8a8 #3c75a9 #197638 #a44395 #f9a213 #dba478` |
| 配套文字色 | `white black black black white white black black` |
| 点径 / 字号 | 点 1.5 / 基因标签 size=6 / 轴标题 13 / 图例 15（**全部沿用原稿**） |
| 图层 | 背景灰柱 + 全部基因抖动点 + top5 基因标注 + y=0 彩色亚群标签块 + `theme_p3()` |

## 补标机制（EXTRA_LABELS）

用户确认的**单点补标**通道：某基因 |coef| 很大但 FDR 未过硬门槛（如 `TMSB4X` DM/OTUD1+(I)/up，|coef|=1.619、FDR=2.09e-03，被 `fdr<=0.001` 挡在 top5 候选池外）→ 在该点补基因名标签，**不改颜色/位置/y 轴范围**（点本已画出，仅补标签）。其余图、其余中等显著行一律不动。

## 输出

- 5 图 × 4 格式 = 20 文件：`fig_volcano_{Aging,DM,Ex_Young,Ex_Old,Ex_DM}_8sub_FINAL.{png,pdf,svg,tiff}`
- 配套表：`fig_volcano_*_8sub_FINAL_toplabels.csv`（每图标注了哪些基因）+ `fig_volcano_5comps_8sub_FINAL_summary.csv`

## 验证状态

- **验证日期**：2026-10-01；数据来源：真实（DEG 过滤表 25,696 行 / 5 对比 × 8 亚群，R + ggplot2）
- 已实际出图并交付（20 文件 + 配套表）；用户逐轮确认版式（画布加宽、数据源换为过滤表、top5→补标 TMSB4X）。

## 修复记录（踩过的坑）

1. **画布太窄 → 亚群名挤叠**：8×6 inch 时色块宽 1.415 inch < 标签宽 1.415 inch 临界 → 加宽到 14×7。
2. **数据源用错**：必须用**已过滤表**（FDR<0.05 & \|coef\|≥0.25）；用全量表会把"灰=不显著"类别画出一大片空柱。
3. **`rbind` 对 tbl_df 校验严格**：补标行 `rbind(top_genes, supp)` 报 `numbers of columns of arguments do not match` → 换 `dplyr::bind_rows` 通过（base::rbind 不吃 dplyr 的 tbl_df）。
4. **只补指定那一处**：补标是用户逐点确认制，不要顺手把其他 FDR 中等行也标上。

## 来源

- `user`：用户 notebook 原稿（cell#3/#4/#6/#7）1:1 复刻为可跑 R 脚本；2026-10-01 用户确认沉淀。