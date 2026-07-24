---
name: heartbeat-monitor
description: 长任务心跳监控 — 独立后台进程持续记录进度，Agent 随时读取汇报
category: system
trigger_level: RED
trigger_keywords:
  - 心跳
  - 监控
  - heartbeat
  - monitor
  - 长时间
  - 后台监控
  - 进度汇报
  - 跑多久了
  - 还在跑吗
  - 进度
language: Python
memomics_module: heartbeat_monitor
---

# Heartbeat Monitor — 长任务心跳监控

## 功能

为超过 10 分钟的分析任务部署独立后台监控进程，持续记录 GPU、进程、文件产出、训练 epoch 到 `monitor.log`。Agent 任何时候读取此文件即可准确汇报进度——不需要反复调 `nvidia-smi` 或扫描文件。

## 触发条件

- 任意 `terminal` 提交了预计 > 10 分钟的任务
- 用户问"进度"、"跑多久了"、"还在跑吗"
- CellBender、SCTransform、大数据训练的 pipeline 启动时

## 工作流

```
1. 部署监控: terminal("python heartbeat.py --task 'CellBender' --dir F:/CellBender_v2 --interval 120 &", background=True)
2. 等待 N 分钟后检查: terminal("tail -5 F:/CellBender_v2/monitor.log")
3. 向用户汇报: "样本 5/26 已完成，GPU 85%，预计还需 20 小时"
4. 任务完成后停止: taskkill /F /PID <heartbeat_pid>
```

## 监控数据格式 (monitor.log)

```json
{"ts": "2026-07-25 02:15:00", "task": "CellBender", "iteration": 3, "elapsed_min": 6.0,
 "gpu": {"gpu_util": "87", "vram_used": "14336", "temp": "72"},
 "output_files": 5, "epoch": "23/150", "process_alive": true}
```

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| --task | 任务名称（用于日志标识） | 必填 |
| --dir | 监控目录（monitor.log 写入此目录） | 必填 |
| --interval | 检查间隔（秒） | 120 |
| --log | pipeline 日志文件名 | pipeline.log |
| --pattern | 产出文件匹配模式 | *.h5 |
| --gpu | 是否监控 GPU | True |
| --pid | 主进程 PID（监控存活） | 0 |

## 与现有机制的协同

| 机制 | 角色 |
|------|------|
| heartbeat.py | 独立后台进程，持续写入 monitor.log |
| task_plan.md | 分析蓝图，记录 Phase 状态 |
| server.py 心跳 | 每 30s 读 task_plan.md + 扫描新文件推前端 |
| headroom | 压缩过时的 monitor.log 节省上下文 |
| SOUL 规则 16 | terminal 必须 background=True |

## 注意事项

- 心跳脚本在后台运行，不阻塞 Agent
- Agent 空闲或压缩后，读 monitor.log 即可恢复"当前进度"感知
- 任务完成后用 `taskkill` 或 `pkill` 停止心跳进程
- monitor.log 超过 1000 行时用 headroom 压缩旧条目
