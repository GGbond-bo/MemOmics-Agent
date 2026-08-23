# 停止系统唤醒心跳（user: "停止，心跳停掉"）— 2026-08-03 实测

## 症状
用户说 "停止，不需要task_plan了" / "停止，心跳停掉" 之后，⏰ [系统唤醒 #N]
仍然每 ~15-60 分钟持续注入。`hermes cron list` = No scheduled jobs，
`hermes cron status` = Gateway not running，但唤醒不停止。

## 根因（本环境实测，server.py 自检机制）
唤醒**不是** Hermes cron，而是 `webui/server.py` 的 `_schedule_self_check()`
（约 line 482-570）——每个 agent turn 后重新调度，检查：
- `has_todos`（session todos 里有非 completed/cancelled 项）
- `has_plan`（`results_dir/task_plan.md` 文件存在）

关键 bug：task_plan.md 里标记 `🔒 CLOSED` / "已停止" 时，
self-check 的跳过条件只认 `"cancelled"` 和 `"**Status:** paused"` ——
**不认 CLOSED / 已停止**，所以标记 CLOSED 的 task_plan 依然触发唤醒。

## 停止方案（双保险，均实测有效）

### 1. 立即生效：重命名 task_plan.md
```bash
mv "results/<session>/task_plan.md" "results/<session>/task_plan_CLOSED.md.bak"
```
`has_plan = os.path.isfile(task_plan.md)` → False → self-check 直接 return。
内容完整保留在 .bak，不删数据。

### 2. 长期生效：patch server.py 跳过条件（重启 webui 后生效）
原代码只认 cancelled/paused，补上 CLOSED/已停止：
```python
if "cancelled" in plan_text.lower() or "**Status:** paused" in plan_text \
   or "**Status:** closed" in plan_text.lower() or "🔒 CLOSED" in plan_text \
   or "已停止" in plan_text:
    logger.info("... task_plan is cancelled/paused/closed, skipping self-check")
    return
```
⚠️ `_sync_debate_env` 的教训同样适用：server.py 的模块级代码
（`_schedule_self_check` 是每个 turn 调用，但 import 时加载的部分要重启才生效）。

### 3. 确认 cron 层无任务
```bash
hermes cron list     # No scheduled jobs
hermes cron status   # Gateway is not running — cron jobs will NOT fire
```

## 验证（ad-hoc verify 模式）
写 `hermes-verify-selfcheck.py` 到 Temp：
1. `ast.parse(server.py)` 语法通过
2. patch 后的 if 条件行覆盖 6 个关键词：cancelled / paused / closed / 已停止 / 🔒 CLOSED / **Status:**
3. task_plan.md 不存在（has_plan=False）+ .bak 存在且非空
4. `_schedule_self_check` / `_calc_self_check_delay` 函数仍在
实测 13/13 通过（注意：第一版验证脚本误匹配 logger 消息行而非 if 条件行——
定位条件行要用 `'in plan_text' in line and 'cancelled' in line`，不能匹配消息字符串）。

## 反模式
- ❌ 只改 task_plan 内容为 "CLOSED" 不重命名 → 不生效（跳过条件不认 CLOSED）
- ❌ 只 patch server.py 不重启 webui → 当前进程仍是旧代码，立即停止需靠重命名
- ❌ 直接杀 webui/server.py 进程 → 用户正用着的界面会断，不可取
