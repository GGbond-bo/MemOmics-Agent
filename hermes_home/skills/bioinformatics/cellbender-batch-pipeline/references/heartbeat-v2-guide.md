# heartbeat_v2.py — 脱离式独立心跳使用指南

## 为什么需要 v2

v1 (bash `while true`) 的三个致命问题：

| 问题 | v1 | v2 |
|------|----|----|
| Shell 依赖 | 挂在 bash 会话下，Hermes 回收 → 死 | `subprocess.Popen + CREATE_NO_WINDOW`，完全独立 |
| 数据源 | 只写 grep epoch 到 monitor.log | 直接读 CellBender 的 `cellbender_output.log`，提取 epoch/total/loss |
| 自愈 | 无 | 连续 5 轮无进度更新 → 告警 |

## 启动

```bash
python PROJECT_DATA_DIR/scripts/heartbeat_v2.py \
  --task "CellBender_26samples_Stage2" \
  --dir PROJECT_DATA_DIR \
  --log-paths \
    "PROJECT_DATA_DIR/cellbender_output/{当前样本}/cellbender_output.log" \
  --interval 120 \
  --output PROJECT_DATA_DIR/monitor.log \
  --output-dir PROJECT_DATA_DIR/cellbender_output
```

## 监控内容

monitor.log 每行格式：

```
[04:35:02] GPU=82%, 7890 MiB | 4CL_SD_D4_1=epoch 120/150 | output.h5=3 | filtered.h5=2 | py_procs=5 | cycle=12
```

## Agent 读取协议（铁律 17）

每次查进度必须：
1. `read_file(真实日志尾部 50 行)` — 不是 monitor.log
2. `nvidia-smi` — GPU 实时
3. `tasklist` — 进程存活
4. 三条一致 → 汇报
5. 最新行时间戳 > 5 分钟前 → 标记"可能僵死"
