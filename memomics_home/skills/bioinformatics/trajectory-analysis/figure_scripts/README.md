# Figure Scripts — User Custom Visualizations

> 这个目录存放你**自己写的**可视化脚本。当你说"用我的图"或"用我的可视化"时，
> MemOmics 自动加载这里的脚本，替代 skill 默认的绘图逻辑。

## 工作原理

1. **写好脚本放这里** — 任意 `.R` 或 `.py` 文件
2. **下次说"用我的图"** — `rail_review(pre)` 检测到此目录非空，提示 agent 加载
3. **审查照样触发** — `rail_review(post)` 检查生成图片的质量（不空白、不 NA、> 5KB）
4. **辩论照样触发** — `debate_figure_conclusions` 照常对图片结论进行辩论
5. **自动沉淀** — 运行成功后 `skill_evolution(action="record_run")` 记录你的脚本
6. **下次复用** — `skill_evolution(action="query_logs")` 返回历史参数，自动匹配

## 命名约定

```
figure_scripts/
├── custom_umap.R          # 自定义 UMAP
├── custom_heatmap.R       # 自定义热图
├── custom_volcano.R       # 自定义火山图
├── my_style.R             # 全局样式（ggplot2 theme、配色方案）
└── README.md              # 本文件
```

## 脚本要求

- **输出路径**: 使用 `OUTPUT_DIR` 环境变量或相对路径 `figures/`
- **输出格式**: PNG 或 SVG（用于 HTML 报告嵌入）
- **铁律头**: 每个脚本第一行必须包含 `# MemOmics: rail_review(pre) → debate_analysis → rail_review(post)`
- **参数化**: 用大写变量（`SPECIES`、`TISSUE`、`INPUT_PATH`）声明参数，方便下次自动填充

## 什么时候自动触发

| 用户说 | 行为 |
|:---|:---|
| "用我的图" / "用我的可视化" | 加载 `figure_scripts/` 下全部脚本 |
| "用上次那个 UMAP" | 查 `query_logs` → 匹配 `figure_scripts/custom_umap.R` |
| "不要默认的图，用我自己的" | 跳过 skill 默认绘图，执行 `figure_scripts/` |

## what-about.md 机制

当 agent 发现 `figure_scripts/` 非空时，会在分析计划中自动添加：

```
[FIGURE_SCRIPTS] 检测到 figure_scripts/ 有 N 个自定义脚本:
  - custom_umap.R (last used: 2024-07-08)
  - custom_heatmap.R (last used: 2024-07-05)
是否使用这些脚本替代默认绘图？[Y/选择特定脚本/N使用默认]
```
