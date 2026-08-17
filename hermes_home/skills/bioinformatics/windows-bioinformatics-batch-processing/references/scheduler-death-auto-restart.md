# 调度器死亡 + 自动重启方案（2026-08-07 memomics-1135ed52 95 分钟事故）

## 事故概况
GSE278576 人海马 40 样本 ArchR QC 串行批处理中，`run_serial.sh` 在样本完成后**反复静默死亡**（无日志、无报错、MSYS bash 被回收），但 `monitor_serial.sh` 继续存活、每 3 分钟写 `done=25/40`。Agent 连续多轮三源验证都看到"monitor 活着 + done 冻结 + 无 worker"却未意识到调度器已死，用户连续追问 5 次"进度呢？"才暴露。**当日发生两次**：

| 次数 | 时间 | 冻结状态 | 停滞时长 | 触发恢复 |
|:---:|------|--------|:---:|------|
| 第 1 次 | 12:01→13:37 | 25/40（hc1265 完成后） | **94 分钟** | 用户 ping 后 Agent 手动重启 |
| 第 2 次 | 14:29→14:39 | 26/40（hc8 完成后） | **~10 分钟** | Agent 唤醒检查发现后手动重启 |

**确认是反复发生的 bug，非偶发。**

## 根因：监控只报状态不重启

```
正常运转：
  run_serial.sh（串行调度器）→ 逐个样本 create_arrow_qc.R → P3 完成后自动下一个
  monitor_serial.sh（心跳监控）→ 每 3 分钟查进程/产出/日志 → 写 monitor.log

死亡场景（本次事故）：
  hc1265 12:01 完成 → run_serial.sh 退出 → 无人启动下一个样本
  monitor 12:04 起写 "done=25/40 procs=0 log=hc1265.log age=Xm"
  12:16 起写 "ALERT: STALL" → 但只写 alerts，不执行重启
  连续 94 分钟 ALERT（12:16→13:38），监控正确检测但无人响应
  用户 13:36 ping → Agent 发现后手动重启 → 恢复
```

**判定口诀**：`done 计数冻结 + 无 worker 进程 + monitor 还在写 = 调度器死了（不是任务在跑）`。monitor.log 活着只能证明 monitor 活着，不能证明 pipeline 活着。

## 修复方案：监控循环加自动重启

在 `monitor_serial.sh` 的停滞判定分支中加入**幂等重启**逻辑：

```bash
# 停滞判定扩展：procs==0 + log_age > STALL_MIN + done < TOTAL → 自动重启调度器
if [ "$procs" -eq 0 ] && [ "$log_age_raw" -gt "$STALL_MIN" ] && [ "$done" -lt "$TOTAL" ]; then
    # 防重复重启：检查是否已有 run_serial.sh 在跑
    if ! ps -W 2>/dev/null | grep -q "run_serial.sh"; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] AUTO-RESTART: scheduler dead (done=$done/$TOTAL, stalled ${log_age_raw}min) → restarting run_serial.sh" >> "$MON_LOG"
        # 幂等重启：SKIP 逻辑自动跳过已完成样本
        nohup bash "$SCRIPT_DIR/run_serial.sh" >> "$SCRIPT_DIR/restart_$(date +%H%M%S).log" 2>&1 &
        # 等待 20s 验证新 worker 出现
        sleep 20
        new_procs=$(powershell.exe -NoProfile -Command "(Get-Process Rscript -ErrorAction SilentlyContinue | Measure-Object).Count" 2>/dev/null)
        if [ "$new_procs" -gt 0 ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] AUTO-RESTART OK: new worker detected (procs=$new_procs)" >> "$MON_LOG"
        else
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] AUTO-RESTART WARN: no worker after 20s, may need manual check" >> "$MON_LOG"
        fi
    fi
fi
```

## 幂等重启原理
`run_serial.sh` 的 SKIP 逻辑：`filtered_cells.csv` 存在 = 样本完成 → 跳过。重启后自动从断点继续，不会重复跑已完成样本。重启命令只需：
```bash
bash batch/run_serial.sh
```
不需要手动补跑单个样本——SKIP 逻辑已覆盖。

## 防重复重启
用 `ps -W | grep "run_serial.sh"` 检查是否已有调度器在跑（避免监控自己反复拉起多个调度器实例）。

## 验证方法（20 秒恢复确认）
重启 20 秒后：
1. PowerShell 查 `Get-Process Rscript` 计数 > 0 = worker 已启动
2. 检查新样本 .bat mtime 更新（`ls -lt batch/run_*.bat | head -1`）
3. 检查新样本 log 出现 "START" 行

## 演进（2026-08-07 17:35-18:00 级联崩溃后）：独立 watchdog_v2.sh — 监控与重启分离

monitor 内嵌自动重启引发级联崩溃（monitor 重启了硬编码的旧版 run_serial.sh → 与 v2 并发 → ArchR tmp 竞争 → 连环失败，详见 `auto-restart-hook-stale-script.md`）后，方案演进为**独立看门狗进程**，与 monitor 完全分离：

- **watchdog_v2.sh** = 独立 bash 进程，PowerShell `Start-Process` 脱离 Hermes 生命周期（PID 12800），`while true; sleep 120` 轮询
- 每轮写 `[TS] watchdog procs=N done=M/40` 到 monitor.log；判定 `procs==0 且 done<TOTAL` → 启动 sanctioned 版 `run_serial_v2.sh`（**带 300s 冷却 + pgrep 双保险**防重复启动）
- monitor（monitor_serial.sh / monitor-serial-loop.sh）退化为**只报状态**：写 monitor.log + alerts.json，不做任何重启决策

**✅ 端到端验证（2026-08-07 18:06→18:11，无需任何人工干预）**：
```
[18:06:33] WATCHDOG_V2 START (PID 12800)
[18:06:33] watchdog procs=1 done=32/40     ← 上一轮 hc11 还在跑，不动作
[18:08:48] watchdog procs=0 done=32/40     ← 检测到调度器又死了（procs=0）
[18:08:48] START run_serial_v2.sh (done=32/40)
[18:08:48] started PID 27369
[18:08:56] hc11 START (Rscript 实际启动)
[18:10:49] watchdog procs=1 done=32/40     ← 冷却期内 worker 出现，自愈完成
[18:11:40] hc11 TabixFile 读取 25%
```
**结论：standalone watchdog 设计有效——调度器反复静默死亡的自愈不需要 Agent 在旁盯守。** 模板见 `templates/watchdog-serial.sh`（改 DONE_DIR/TOTAL/RUN_SCRIPT 等 6 变量即可复用）。⚠️ 关键防坑：`RUN_SCRIPT` 变量必须是**当前 sanctioned 版本名**（重启钩子硬编码旧名 = 复现级联 bug）。

## 适用范围
任何 `run_serial.sh` + `monitor_serial.sh` 双层架构的串行批处理任务。核心原则：**监控必须闭环——检测到停滞 → 自动执行恢复动作，不能只写 alerts 等人来处理。** 自愈优先级：standalone watchdog（watchdog-serial.sh 模板）> monitor 内嵌自动重启（已证实会级联）> 纯手动重启（94 分钟事故）。
