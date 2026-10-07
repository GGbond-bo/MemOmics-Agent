# 自包含 HTML 报告：跨会话取材 → 过审 → 裁决落地

> 适用触发：「**把这次分析整理成一份 HTML 报告，要有图、有结论、有方法说明**」。
> 2026-09-24 实测（MF_120 EDA 报告，195 KB，10 个 section，rail_review(post) passed）。
> 引擎与 API 细节见 skill `bioinformatics-html-report`（`ReportBuilder` / `add_figure` / `auto_fill_from_logs`）。

---

## 1. 先定位「这次分析」是哪个会话（最容易踩的第一坑）

用户的"这次分析"**通常跑在上一会话**，而当前是全新会话：

- 当前会话目录可能只有 `notes.md` + `log/system_log.jsonl`（空壳），`search_history` 也只索引用户消息、看不到上轮 assistant 产出；
- 定位真实分析会话（两条命令，一次搞定）：

```bash
cd /e/MemOmics-Agent/results && ls -lt --time-style=+%m-%d_%H:%M | head -20
find results/<候选sid> -type f | head -40
```

- **判据**：同时有 `figures/` + `results/*.csv` + `conclusions/debate_*.json` + `REQUIREMENTS.md` 的目录才是真分析；只有
  `notes.md`/`log/`/`token_usage.jsonl` 的是空会话（同批创建的空目录常一次出现 5-6 个，别被 mtime 迷惑）；
- **写在哪**：报告写**当前会话** `results/<sid>/reports/`（WebUI 只认 results/ 下），数据源读**分析会话**的产出；
  报告 `author` 里注明分析会话号（如「会话 memomics-0f9b1172」），跨会话溯源才闭合；
- 候选差异明显时直接选最近有产出的那个并在汇报里说明，**不要问空问题**（"你指的是哪个分析？"——除非候选真的无法区分）。

## 2. 报告结构（对齐"有图 / 有结论 / 有方法"三要件）

| section | 放什么 |
|---|---|
| 1. Data & Methods | 数据绝对路径 + 只读/未过滤声明 + `add_pipeline` 分步（每步写真实脚本名与参数）+ 环境（R 版本、库路径、依赖声明） |
| 2. 核心图 | `add_figure`（**四面板全部必填**：`method_zh` / `result_zh` / `bio_zh` / `param_source_zh`，缺一即 `ValueError`） |
| 3. 队列/样本结构 | 组汇总表、样本分组映射表（`add_table(csv_path=...)` 直接吃分析会话的 CSV） |
| 4. 注释/分类 | 亚群 × 组矩阵表 + 注释层级概况 callout |
| 5. QC | 分位数 + 阈值筛查表、完整性核查 callout |
| 6. 结论与风险 | 分条 callout（每条一句话判定）+ 判定表 + **辩论记录** + 待补证据清单 |
| 日志溯源 | `auto_fill_from_logs(collect_session_data(session_id=<分析会话>))` 自动补 |

新表（如 QC 分位数、条件化判定表）在脚本里 `csv.writer` 落盘到 `results/<sid>/results/`，再 `add_table` 引用——
表既是报告内容也是可交付数据。

## 3. auto_fill_from_logs 的已知噪声（**如实处理，不要当结论**）

`collect_session_data(session_id=<分析会话>)` 之后：

- ✅ `state.db` 的工具调用是真来源（`messages` / `tool_calls` 计数可信）；
- ⚠️ **`Skill Error Log` 是全库错误日志**（本次 82 条，绝大多数与本分析无关）——保留但不要当本分析的失败记录；
- ⚠️ `run_records` 可能报 **0**，即使 `results/<分析会话>/log/run_record_*.json` 存在 —— 不要据此删掉运行归档，
  在结论区自己补一句运行要点；
- ⚠️ `_auto_fill_figures_and_debates_from_tool_calls` 会从历史工具调用里捞出一个 debate 段，
  **可能来自更早的一次 L1 草稿辩论**（无裁判裁决）。用之前先核对该段：是草稿/无裁决 → 在报告里显式标注
  「引擎返回推理草稿级输出，未作为裁决引用」，**绝不改写成正式辩论文本**。

## 4. 过审（rail_review post）

- **base64 内嵌图不算图**：报告目录里只有 `.html` 时 `figure_count=0` → 硬判 failed（issue 而非 warning）。
  修复 = 把图副本放进 `output_dir`：

```python
shutil.copy2(FIG, os.path.join(NEW, "reports", "Fig1_<名>.png"))
```

  再 `rail_review(phase="post", module_id="08_报告", output_dir="<reports 目录>", code_executed=<完整脚本>)` → 实测 `figure_count=1, passed=true`。
- ⛔ **不要重跑生成脚本**（属产物口径类判定，重跑不改结论，只多一轮循环告警）。
- 生成脚本落 `results/<sid>/scripts/build_<名>_html_report.py`，之后改参数 → `execute_python: exec(open(path, encoding='utf-8').read())` **秒级重出**（持久内核）。
- 脚本写作两条硬约束：① 长文案参数**每行一段隐式拼接**（跨行普通字符串 = `SyntaxError`）；
  ② 字符串内部不写半角双引号（用「」/中文引号），否则提前闭合报同一类错。

## 5. 辩论裁决落地（L2 之后必做，**报告只是载体**）

裁判输出里要吃干榨净的四样：

| 字段 | 落到哪里 |
|---|---|
| `recommended_params` | **逐条改写报告结论的措辞**（本次四条结论 = 降级 / 收窄 / 收窄 / 支持） |
| `next_actions[{action, owner, blocks}]` | 生成「条件化判定表」CSV → `add_table`；`owner=ai` 且 `blocks` 未完成的写成「补齐后即可重审」清单 |
| `fallback` / `missing` | 结论区 callout：当前状态 = 低置信 / 临时结论，列出待补证据 |
| 正反方论据 | `add_debate(rounds=[{pro, con, verdict, action, pro_score, con_score}])`，只写**真实**摘要 |

⛔ 禁止编造辩论轮次；⛔ 禁止把草稿级输出当裁决；裁决与用户原有认知冲突时**按裁决改**并在汇报里点明改了哪几条。

## 6. 收尾三件套

`skill_evolution(record_run)` → `rail_review(post)` → `session_memory(add, kind='file', 报告路径+生成脚本, importance≥0.8)`；
汇报里给：**绝对路径 + 文件大小 + 章节清单 + 过审结果**，并如实说明报告里的已知局限（自动填充噪声、草稿辩论标注）。