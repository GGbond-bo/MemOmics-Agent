---
name: deg-updown-counts-by-subcluster
description: >-
  骨骼肌 DEG 各比较组 × 亚群的上调/下调基因数量柱状图（Python matplotlib，五联面板）。
  每根柱标注自身基因数，下调蓝(#2166AC)在左、上调红(#B2182B)在右，五面板共享 symlog(linthresh=1) 统一 x 轴
  + 十倍阶梯刻度 0/10/100/1,000/10,000，柱端进入最外侧 20% 自动改柱内白字防重合。
  触发词："DEG 各比较组亚群基因数量图" / "updown 8sub 柱状图" / "上调下调数量柱状图" / "五面板统一 symlog 柱状图"
metadata:
  hermes:
    category: user-skill
    tags: [user, plotting, deg, barplot, symlog, matplotlib]
source: user-requested
verified: 2026-10-01
---

## 使用场景

- 已有**算好的**「比较组 × 亚群 × 方向」基因计数矩阵，要出「各亚群上下调基因数量」对比柱状图。
- 典型场合：DEG 做完后向人展示**不同比较组（Aging / DM / 运动前后）× 不同亚群**的响应规模差异。
- 触发词示例："把这个计数表画成柱状图" / "每个亚群上调下调各多少基因，画出来" / "五个比较组并排"
- ⚠️ 本脚本**只画计数**，不重算统计（计数矩阵须由上游 DEG 流程产出）。

## 输入要求

| 输入 | 格式 | 说明 |
|------|------|------|
| 计数矩阵 | CSV（`deg_subcluster_updown_coef025_matrix.csv` 型） | 每行 = 比较组 × 亚群 × 方向，含计数字段；由上游按过滤阈值（如 FDR<0.05 & \|coef\|≥0.25）统计得出 |

脚本头部两个路径常量需按新项目改：

```python
OUT = r"E:/MemOmics-Agent/results/<sid>/task2/figures"
SRC = r"E:/MemOmics-Agent/results/<sid>/task2/results/deg_subcluster_updown_coef025_matrix.csv"
```

## 版式（用户 2026-09 逐轮定稿，勿擅改）

| 要素 | 取值 |
|------|------|
| 亚群数 | 8 个（剔除 RSS / Specialized MF）：Pure I → IIA → IIX → LRP1B+(I) → RP_high(I) → RP_high(II) → OTUD1+(I) → OTUD1+(II) |
| 面板 | 五联：Aging、DM、Ex_Young、Ex_Old、Ex_DM |
| 计数顺序 | **蓝 Down 在左 \| 红 Up 在右**（用户已确认口径） |
| 配色 | 上调 `#B2182B`、下调 `#2166AC` |
| x 轴 | **统一标准**：`symlog(linthresh=1)` + 十倍阶梯刻度 0/10/100/1,000/10,000（五面板共用一根轴；symlog 让 16,535 与 15 同轴可读） |
| 数值标注 | 每根柱标自身基因数；`frac>0.80`（进入轴最外侧 20%）→ 改柱内白字右对齐 |
| 模块带 | 单一「MF」竖带贴柱区左侧（替代原双家族彩色括号 —— 会与右对齐亚群名压叠） |
| 尺寸导出 | 180×88 mm；png@400 / pdf / svg / tiff@600 |

## 变体开关（同一脚本两种箭头位置）

```python
MF_VARIANT = globals().get("MF_VARIANT", "right")   # right=箭头在各自数字右侧 | center=箭头贴中心线内侧
STEM = globals().get("STEM_OVERRIDE") or "fig_deg_updown_8sub_MF_v7_arrows_vertical"
```

- 内核 exec 注入 `MF_VARIANT` / `STEM_OVERRIDE` 可一脚本出多变体；
- 入库版已把开关**硬编码为 `center`** + `STEM_OVERRIDE="fig_deg_updown_8sub_MF_v7b_arrows_at_center"`（即 v7b，用户选定版）。

## 输出

- `fig_deg_updown_8sub_MF_v7b_arrows_at_center.{png,pdf,svg,tiff}` + `_source_data.csv`
- 同族历史变体（v1–v7a）在 `task2/figures/`，脚本族 `31_`–`37_`。

## 验证状态

- **验证日期**：2026-10-01；数据来源：真实（骨骼肌 48 样本 6 组，DEG 过滤表 25,696 行）
- v7b 已实际出图并交付（图 + 脚本同目录），`rail_review(post)` 因"未生成图片"报 false 属脚本交付轮的预期误判（非质量问题）。

## 修复记录（踩过的坑）

1. **左侧家族括号压叠**：原「家族括号 x=0.150 + 旋转家族名 x=0.137」与右对齐亚群名（6.6pt 13 字符左缘约 0.094）必压叠 → 改单一「MF」模块竖带。
2. **不统一 x 轴会误导**：各面板独立缩放时 Aging(16,535) 与 Ex_Young(15) 视觉等宽 → 必须共享 symlog 统一轴。
3. **柱端数值标签越界**：大值柱贴近轴端时外侧标注出面板 → `frac>0.80` 改柱内白字。
4. **变体靠内核注入不会留脚本**：`MF_VARIANT` 注入跑出的图，磁盘上只留脚本本体（默认 `right`）→ 交付时须把开关硬编码另存为独立可跑版，否则用户找不到"那张图的脚本"。

## 来源

- `user-requested`：用户口头需求（"DEG 各比较组展示不同亚群基因数量"）→ AI 编写 → 实际运行验证通过 → 2026-10-01 用户确认沉淀。