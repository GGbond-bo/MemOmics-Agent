# 用户脚本库总索引（User Scripts INDEX）

> **用途**：登记所有"用户提供且实际运行验证通过"的脚本，支持跨会话回忆与复用。
> **触发**：用户说"之前那个脚本 / 那个分析 / 那个代码 / 上次的 XX" → 先查本索引。
> **分类规则**（SOUL.md 用户脚本铁律）：画图→`plotting/`，比对/对比流程→`comparison/`，其他按用途建类。

## 分类目录

| 分类 | 用途 | 位置 | 说明 |
|------|------|------|------|
| `plotting` | 画图 / 出图 / 可视化 | `skills/plotting/<名称>/` | 用户画图脚本库（含 CNS 标准版） |
| `comparison` | 比对 / 对比流程 / 差异比较 | `skills/comparison/<名称>/` | 用户比对脚本库（2026-08-22 建） |
| `statistics` | 统计检验 / 显著性计算（独立/配对比较、细胞比例检验） | `skills/statistics/<名称>/` | 用户统计检验脚本库（2026-08-22 建；来源含用户口头需求→AI 编写，标 source: user-requested） |

## 已沉淀脚本登记表

| 名称 | 用途 | 触发词示例 | 路径 | 沉淀日期 | 状态 |
|------|------|-----------|------|---------|------|
| `fig-split-program-heatmap-R` | AUCell 程序打分矩阵热图（18 程序 × 6组/5效应/10亚群，base graphics R 版，RdBu_r，6图×4格式@300dpi） | "fig_split_v10 的 R 版" / "18 程序打分热图出 R 版" / "五效应 Cohen's d 热图 R" | `skills/plotting/fig-split-program-heatmap-R/` | 2026-09-15 | ✅ 已验证（矩阵 Δ≤1.4e-14、取色 RGB 差=0、几何逐项一致） |
| `deg-updown-counts-by-subcluster` | DEG 各比较组 × 8 亚群 上下调基因数量柱状图（Python/matplotlib 五联面板，symlog 统一轴，下蓝左/上红右） | "DEG 各比较组亚群基因数量图" / "updown 8sub 柱状图" / "上调下调数量柱状图" / "五面板统一 symlog 柱状图" | `skills/plotting/deg-updown-counts-by-subcluster/` | 2026-10-01 | ✅ 已验证（v7b 实际出图交付，5 格式齐全） |
| `deg-volcano-5comps-8sub-R` | DEG 五比较组 × 8 亚群火山图（R ggplot2+ggrepel，14×7in，灰柱+抖动点+top5标注+亚群色块，含单点补标通道） | "火山图 R 版" / "5 比较组 8 亚群火山图" / "DEG 火山图带亚群标签块" / "volcano 8sub FINAL" | `skills/plotting/deg-volcano-5comps-8sub-R/` | 2026-10-01 | ✅ 已验证（5图×4格式=20文件 + 配套 toplabels/summary 表） |

> 沉淀流程见 `skills/plotting/README.md` 与 `skills/comparison/README.md`（六步：运行验证 → 汇报 → 必问 → 确认入库 → record_run 留档 → 汇报触发词）。
> ⚠️ 未验证的脚本不允许入库；未询问用户不允许入库（双重门禁）。
