# Agent 常见错误（grn-pyscenic）

> 每次加载此 skill 后，在写代码前检查此文件。**以下错误已被用户纠正，不要等用户再次指出。**

## 错误清单

### 1. 加载 skill_view 后凭记忆写代码

**用户纠正："奇怪，你都触发skill了，怎么还要自己写代码呢？"**

**正确做法**：加载 SKILL.md 后，先检查 `linked_files` 中的 `scripts/` 和 `templates/` 目录。如果 skill 包含现成脚本模板（如 `run_grn_workflow.py`、`plot_regulon_visualizations.py`），优先使用或修改，**禁止从头写**。SKILL.md 中写明了「脚本必须基于模板」，不是让你看了就写——是让你直接用。

### 2. 不查看 skill 的 scripts/ 目录是否存在可用函数

**用户纠正**：同上

**正确做法**：使用 `skill_view(name="grn-pyscenic", file_path="scripts/run_grn_workflow.py")` 查看现有脚本。SKILL.md 明确写了 "DO NOT write inline GRNBoost2/cisTarget code — use run_complete_grn_workflow()"。如果现有脚本有兼容性问题（如 `SparseCSRMatrixView` 没有 `.A` 属性），**修改脚本本身**，而不是弃用脚本从零写。

### 3. cisTarget 失败时直接跳过

**用户纠正**：用户已明确要求 follow rules

**正确做法**：cisTarget 因基因名不匹配失败时，先查 SKILL.md 的 Common Issues 表——`AssertionError: Signatures dataframe is empty!` 已有修复方案：先过滤表达矩阵只保留与 ranking 数据库列名匹配的基因，再重跑。

### 4. 不调 skill_evolution(action="record_run")

**系统铁律**：脚本成功 + rail_review(post) 通过后，必须调 `record_run` 记录参数/结果/质量评分。失败时调 `record_error` 记录根因+修复方案。

### 5. 不出图或少出图

**用户纠正："我怎么感觉你出图少了很多呢？"**

**正确做法**：SCENIC 分析完成后，必须生成至少：
- TF 活性热图（Zone×TF）
- 关键 TF 箱线图/小提琴图
- TF 伪时间梯度图（如有 scTour 结果）
- 每条路线独立出图，不合并混用