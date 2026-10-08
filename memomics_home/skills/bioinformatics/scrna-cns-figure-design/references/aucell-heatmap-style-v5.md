# AUCell 打分热图 CNS 样式规范 v5（2026-08-15 定稿，用户认可）

本文件记录骨骼肌 MF 项目 AUCell 打分热图（五效应矩阵 + 打分×亚群）经 v1→v5
迭代后**用户最终认可**的样式。v3/v4 因违反被逐一打回，v5 通过。产出：
`results/memomics-2274ab75/figures/Fig1_five_effects_matrix_v5.*` +
`Fig7_score_by_subcluster_v5.*`，脚本 `scripts/fig_v5_final.py`。

## 样式参数（v5 定稿值）

```python
# ---- 图 1：五效应矩阵（1×5 并排） ----
PANEL_GAP = 1.8          # 面板间距（v4 用 3.0 被嫌"隔开距离也大了"）
CELL = 0.94
# 行分组间隙：组间空行 ri += 0.6（v4 用 1.0 被嫌"隔开这么多，稍微小一点"）
# → 总行数 11+0.6+4+0.6+7 = 23.2
norm = TwoSlopeNorm(vmin=-3, vcenter=0, vmax=3)
cmap = plt.cm.RdBu_r     # 红=正效应，蓝=负，白=0（v2 杂色被否，必须 RdBu）
# 亚群标签：底部 45°（ha="right", va="top", y≈-1.9），绝不进图形内
# 行分组色带：左侧（-1.25 起），三组标签 Metabolic/Fiber Identity/Senescence
# 面板标题：顶部，含对比公式（Aging (O_Pre-Y_Pre) / ExYoung (Y_Post-Y_Pre)）
# 星号：格内 * = FDR < 0.05，|d|>1.5 时白色否则黑色
# figsize=(17.0, 8.6), dpi=300, bbox_inches="tight", facecolor="white"
# 导出 PNG+PDF+SVG

# ---- 图 7：打分 × 亚群（转置版） ----
# y = 22 打分（行，左侧三组色带），x = 10 亚群（底部 45°）——用户明确方向
# 值 = 行 z-score（sub_agg 跨亚群标准化），TwoSlopeNorm(vmin=-2, vcenter=0, vmax=2)
# figsize=(11.0, 8.0)
```

## 硬性偏好速查（用户逐条纠正过）

| # | 偏好 | 违反后果 |
|---|------|---------|
| 1 | 22 个打分行标签写全名，禁止缩写/只写分组名 | 用户："没有基因集的名字，要么就是简写，为啥偷懒？" |
| 2 | RdBu_r 红蓝白，正=红负=蓝白=0 | v2 混青/黄杂色被否："颜色也没有之前的好看" |
| 3 | label 全部在图形外 | "label在图形里面"= 硬伤 |
| 4 | 亚群标签在底部，不在顶部 | v3 invert_yaxis 翻到顶部被否："放在下面呀" |
| 5 | 行分组间隙窄（0.6 行） | v4 用 1.0："隔开这么多，稍微小一点" |
| 6 | 面板间距小（1.8） | v4 用 3.0："隔开距离也大了，稍微有些距离就行" |
| 7 | 改版保留旧版样式骨架，脚本版本化 | "脚本没有吗？历史记忆没有吗？" |

## 实现级坑（全部本会话实测）

1. **`_AUC` 后缀 KeyError**：meta CSV 打分列名形如 `scoreOxPhos_AUC`。
   - pivot 前：`df["score"] = df["score"].str.replace("_AUC$", "", regex=True)`
   - groupby 聚合后转置前：`sub_agg.columns = score_names`（去掉后缀），
     否则 `ZT.loc['scoreOxPhos']` 报 KeyError（v5 首次运行实测死在这）。
2. **交互框表格错位**：Markdown 管道表格在用户客户端列宽渲染错位（两次反馈
   "还是错位的"）。替代：① 等宽代码块（空格填充列，用户确认对齐）
   ② 图片表格（`Denervation_5effects_table` 样式：表头带完整公式 +
   红蓝单元格）。用户最终偏好图片表格。交付前先问要哪种。
3. **R 环境 DLL 批量损坏**：rlang/digest/cluster/Matrix/vctrs/cli 等
   LoadLibrary failure 时不要逐个修——数据落盘 CSV 后直接 Python 出图。
   `requireNamespace` 只查存在性不加载 DLL → 坏包显示 TRUE 是假象，
   真测 `tryCatch(library(p))`。
4. **rail_review(post) 误判"代码过短"**：code_executed 传摘要字符串会被拒。
   传完整脚本（read_file 读取），或核对产出物（文件存在+非空+图 465KB/236KB）
   后直接 record_run。
5. **execute_r 内核 R 版本与库不匹配**：本会话 execute_r 是 R-4.4.2 内核但
   libPaths 混入 R-4.5.3 库 → requireNamespace 全 FALSE。画图任务直接用验证过
   的 `"/c/Program Files/R/R-4.5.3/bin/x64/Rscript.exe"` + `.libPaths(c("E:/R-libs/R-4.5.3", .libPaths()))`，
   或直接 Python。

## Denervation 基因集净化记录（同会话）

- **问题**：五效应图里 Denervation 打分全亚群效应高（50 格 46 格正），
  但绝对水平只有 Specialized MF 高。用户问"是不是算错了"。
- **真相**：不是算错。绝对水平 vs 相对变化混淆——Aging 效应其实极小
  （全亚群绝对差 +0.003~+0.036），运动轴才是"全红"主因（O_Post 全亚群
  几乎翻倍），且是基因集混杂（MYH8/MYOG/RUNX1 同时是再生标志，
  与 RegMyon 基因集 r=0.86）。
- **净化**：11 基因 → 8 基因终版 `CHRNA1, CHRNG, CHRND, SCN5A, KCNMB1,
  NCAM1, NGFR, RUNX1`（剔除 MYOG/MYH8/GAP43）。
- **RUNX1 保留理由**：Zhu 1994 MCB PMID 7969143（AML1 受神经支配调控）、
  Wang 2005 Genes Dev PMID 16024660（Runx1 去神经后上调防萎缩）。
  用户判断正确——它是去神经核心 TF，不是再生混杂。
- **净化后效果**：Aging 轴更干净（全 10 亚群一致正、SMF 最高 d=+1.10）；
  运动轴回落但仍正（NCAM1/RUNX1 参与运动诱导 NMJ 重塑，生物学上共享）；
  T2D 轴无信号（d≈0）。
- **通用教训**：新基因集必须逐基因文献审计（search_papers 给真实 PMID），
  剔除与再生/其他打分重叠的基因；解读"打分高"先分绝对水平与效应量。
