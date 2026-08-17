# 重启风暴 → 脚本级 unlink(tmp) → 级联失败（2026-08-07 GSE278576 40 样本实锤）

## 事故时间线（memomics-1135ed52，ArchR createArrowFiles 批处理）

| 时刻 | 事件 | 证据 |
|------|------|------|
| 17:20 | run_serial_v2.sh 启动 hc12 | v2.out: `START hc12` |
| 17:35:29 | hc12 成功 exit=0（**唯一成功样本**） | v2.out: `END hc12 OK` |
| 17:35→17:56 | **monitor 被反复重启 6 次**（17:45/17:50/17:56 连续 MONITOR START） | monitor.log |
| 17:48:34 | **3 个 Rscript 并发** | monitor.log: `procs=3` |
| 17:45-17:54 | hc11/hc73/hc19/hc26/hc40 全 FAILED（exit=1/127） | v2.out + v3.out |
| 17:57 | hc11 失败根因暴露：`.tabixToTmp Cannot open file 'E:\...\tmp\tmp-GSM8549647_hc11-arrow-...arrow' does not exist` | logs/hc11.log |
| 18:05 | 部署 watchdog_v2.sh 接管，防并发 | watchdog_v2.sh |
| 18:08:49 | watchdog 拉起 run_serial_v2.sh → hc11 重跑成功（tabix 33% 推进中） | run_serial_auto.out |

## 根因链（三层，缺一不可）

1. **重启风暴**：monitor_serial.sh 的停滞检测用 `procs == 0` 判死。串行批处理**样本间切换间隙 procs=0 是正常状态**（上一个样本已退出、下一个还没拉起），monitor 把间隙当停滞 → 自动重启 run_serial → 多个 monitor 实例各自重启 → 3+ 个 run_serial 并存 → Rscript 并发。
2. **脚本级 unlink(tmp) 地雷**：create_arrow_qc.R 开头做"pre-clean"：
   ```r
   tmp_dir <- file.path(out_root, "tmp")
   if (dir.exists(tmp_dir)) unlink(tmp_dir, recursive = TRUE, force = TRUE)
   ```
   单实例时这是合理的残留清理；**多实例并发时 = 进程 A 把进程 B 正在写入的 tmp-arrow 删掉** → B 的 tabixToTmp 报 "Cannot open file ... does not exist"。这是**脚本自带的并发地雷**，比 ArchR 自身的共享 tmp 更致命（ArchR 共享 tmp 至少还有锁，脚本 unlink 是无差别删除）。
3. **版本增殖 + 锁碎片化**：run_serial.sh / v2 / v3 并存，锁名各不同（.run_serial.lock / .run_serial_v2.pid / .run_serial_v3.pid）→ 单实例锁形同虚设，旧版被 monitor 重启钩子拉起后与 v2 并发。

## 修复模式 = watchdog_v2 设计（本 session 验证有效）

```bash
# 防并发三重保险，缺一不可：
# ① 冷却期：LAST_RESTART_TS + 300s，防重启风暴
# ② pgrep 双保险：启动前确认无 "bash.*run_serial_v2.sh" 存活
# ③ 归零确认：procs==0 且 done<TOTAL 才启动
if [ "$PROC_COUNT" -eq 0 ] && [ "$DONE_COUNT" -lt "$TOTAL" ]; then
  if [ $((NOW_S - LAST_RESTART_TS)) -ge 300 ]; then
    if ! pgrep -f "bash.*run_serial_v2.sh" >/dev/null 2>&1; then
      nohup bash batch/run_serial_v2.sh >> batch/run_serial_auto.out 2>&1 &
      LAST_RESTART_TS=$NOW_S
    fi
  fi
fi
```

关键点：
- **重启钩子里的脚本名必须逐字核对**（升级 v2/v3 时同步改 monitor 钩子，旧版改名 .bak 归档，锁名统一）
- 防重启风暴的冷却期 300s 必须显式配置，不能靠"procs==0 再查一次"（间隙性误判）
- 恢复后不杀当前存活 worker（浪费已跑进度），等它完成 → Rscript=0 → watchdog 自动拉起下一轮

## 判定口诀

- 连续样本 FAILED + 失败都是 `.tabixToTmp Cannot open file` → 先查**并发**（`Get-Process Rscript` 计数）再查磁盘/权限
- monitor.log 出现**连续多次 MONITOR START** = 重启风暴正在进行，立即检查 monitor 钩子脚本名 + 锁名是否版本错配
- 样本脚本开头的 `unlink(tmp_dir)` 在**任何批量场景都是并发地雷**——要么删掉，要么加锁（只有当前实例自己的 lock 才能删）
