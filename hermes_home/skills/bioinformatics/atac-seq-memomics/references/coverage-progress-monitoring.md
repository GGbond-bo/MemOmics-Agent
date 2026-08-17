# ArchR Coverage 进度监控指南

## 问题

`addGroupCoverages` 运行时，stdout 只有粗略的 "Group X of Y" 行，且缓冲可能延迟。更好的进度源是 ArchRLogs 目录。

## 监控数据源优先级

| 优先级 | 数据源 | 精度 | 示例 |
|:---:|------|------|------|
| **1** | `ArchRLogs/ArchR-addGroupCoverages-*.log` | 染色体级 | `Group C8._.Y3_Hip_1 (20 of 57) : Processed Fragments Chr (14 of 21), 6.294 mins elapsed` |
| 2 | 脚本 stdout 日志 | 组级 | `Group C7._.Y3_Hip_2 (16 of 57)` |
| 3 | Coverage .h5 文件数量 | 完成组数 | `ls GroupCoverages/Clusters/*.h5 | wc -l` |
| 4 | GPU/CPU 利用率 | 活性 | `nvidia-smi`、`tasklist` |

## 从 ArchRLog 提取进度

```bash
# 找到最新 ArchR addGroupCoverages 日志
LOG=$(ls -t ArchRLogs/ArchR-addGroupCoverages-*.log | head -1)

# 看当前进度（最后 3 行）
tail -3 "$LOG"

# 输出示例:
# Group C9._.Y3_Hip_1 (22 of 57) : Processed Fragments Chr (1 of 21), 7.01 mins elapsed.
```

从最后一行提取：**当前组号 / 总组数 / 染色体号 / 耗时**。

## 进度估算

36K cells, 21 clusters, 57 组（每个 cluster × 3 个 sample 的组合）：
- 每组耗时：~19-30 秒（处理 21 条染色体）
- 总耗时：57 组 × ~25 秒 ≈ **14-24 分钟**
- ETA：`elapsed + (total - current) × avg_sec_per_group`

## 卡死检测

**判定卡死的条件**（按信心递增）：
1. ArchR 日志行数在 2 个心跳间隔内无变化（即 >4 分钟）
2. R 进程存活但日志停止，且 CPU 降至 ~0%
3. 磁盘上的 coverage .h5 文件时间戳不更新

**最常见的卡死原因**：
- **Foreground 超时**：`terminal()` foreground 600s 硬限 → 进程被系统 kill
- **Bash segfault**：MSYS bash + R 动态库冲突 → 随机 exit 139 或 hang

**修复**：必须 `cmd.exe /c` + background 模式（详见 SKILL.md 主文件）。

## 从卡死恢复

```bash
# 1. 确认卡死
echo "ArchR log lines: $(wc -l < $LOG) ... Last: $(tail -1 $LOG)"

# 2. 杀僵尸进程
taskkill /F /PID <旧R进程PID>

# 3. 重启（cmd.exe /c 绕过 bash）
terminal(command='cmd.exe /c "\"C:/Program Files/R/R-4.5.3/bin/Rscript.exe\" restart_script.R > restart.log 2>&1"',
         background=True, notify_on_complete=True, timeout=3600)

# 4. 验证：等 2 分钟后读 ArchR 日志确认在推进
```

## 心跳脚本适配

心跳脚本 (`heartbeat.py`) 应监控 ArchR 日志而非仅脚本 stdout：
```python
import glob, os

# 找到最新的 ArchR addGroupCoverages 日志
archr_logs = sorted(glob.glob(f"{output_dir}/ArchRLogs/ArchR-addGroupCoverages-*.log"))
if archr_logs:
    latest = archr_logs[-1]
    last_line = open(latest).readlines()[-1] if os.path.getsize(latest) > 0 else ""
    # 解析: "Group C9._.Y3_Hip_1 (22 of 57) : Processed Fragments Chr (1 of 21)"
```

## 验证 Coverage 是否可用

Coverage 完成后验证：
```r
proj <- readRDS("project_cov.rds")
cat("Cells:", length(proj$cellNames), "\n")
cat("Matrices:", paste(getAvailableMatrices(proj), collapse=", "), "\n")
# 预期: "GeneScoreMatrix, TileMatrix"（加上 "GroupCoverages" 如果正确链接）
```
