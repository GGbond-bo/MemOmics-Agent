# Agent 侧系统唤醒检查协议（System Wakeup #N）

场景：`⏰ [系统唤醒 #N] 检查主线任务进度` — 主 Agent 被系统唤醒（**非** cron 心跳），
prompt 模板固定三行：1. 读 task_plan.md 看当前 Phase 2. search_files 看最新产出 3. 继续执行下一个待办。

## 铁律 1: 找 task_plan — 按 mtime 选最新，禁止按路径假设

本机实测（2026-08-08, 唤醒 #3）存在 **6 个 task_plan.md**：
- `MEMOMICS_HOME/task_plan.md` — **过期副本**（7月30 旧版），不是真身！
- `MEMOMICS_HOME/results/<session_dir>/task_plan.md` — 每个 session 一份真身

```bash
ls -lt MEMOMICS_HOME/results/*/task_plan.md MEMOMICS_HOME/task_plan.md | head
```

选 **mtime 最新** 的一份读。读旧 task_plan = 基于过期状态决策 = 跨 session 污染（同铁律 -5）。

> ⚠️ **无 task_plan.md ≠ 无任务（2026-08-08 唤醒 #4 实测）**：部分 session 目录（如 `memomics-1135ed52`）可能没有 task_plan.md 或文件为空，但 `batch/alerts.json` 显示任务状态（如 `{"done":40,"total":40}`）。唤醒检查必须同时查：
> - `{results_dir}/task_plan.md`（Phase 状态）
> - `{results_dir}/batch/alerts.json`（批处理完成信号）
> - `{results_dir}/batch/monitor.log` 尾部（watchdog 输出，如 `ALL DONE (40/40)`）
> 三者都查过才能下"任务完成/无运行中任务"的结论。alerts.json + monitor.log 是 task_plan 缺失时的可靠替代证据。

## 铁律 2: 三源验证（铁律 -2 在唤醒场景的应用）

| 数据源 | 工具 |
|--------|------|
| task_plan Phase 状态 | read_file(最新 task_plan.md) |
| 后台进程 | process(action="list") |
| 产出物 | search_files 最新产出目录 + 计数 |

三者一致才开口汇报。本会话验证样例：process list 为空 + QC_filtered 目录 42 项
（40 样本目录 + QC_summary_all40.csv + 附加文件）= 无运行中任务，判断成立。

## 铁律 3: ⛔ "继续执行下一个待办" ≠ 自动启动 blocked phase

task_plan 中标 `等待用户确认` / `用户红线：不自动执行` / `阻塞` 的 Phase **绝对不能自动启动**。
用户红线优先级 > 唤醒 prompt 的"继续执行"。

本会话实测（memomics-1c1890da，猴-人脑 scATAC 全流程）：
- Phase 4（人海马 ATAC merge+LSI+聚类）标 `等待用户确认（用户红线：不自动执行）`
- Phase 7（猴-人 CRE 跨物种对比）标 `阻塞：数据未齐 + 用户停止指令`
- 正确行为 = 停下汇报，列出用户可选指令，结束回合，**不启动任何分析**

正确汇报结构：
```
✅ 状态表（完成项 / 阻塞项 / 阻塞原因）
⛔ 结论："无自动可执行待办，等待用户指示"
📋 用户可选指令列表（如 "开始 P4" / "开始跨物种对比"）
```

## 为什么这是重复出现的类

用户跑长任务（CellBender/ArchR 40 样本/跨物种专利）时会**持续**收到系统唤醒
（本会话是 #3，说明 #1/#2 已发生过）。每次唤醒都是同一个陷阱组合：
读错 task_plan（mtime 选错）+ 误启动 blocked phase（把"继续执行"当授权）。
