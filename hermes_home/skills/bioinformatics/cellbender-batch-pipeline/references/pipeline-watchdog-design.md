# Pipeline Watchdog — 自我修复守护进程设计

## 设计目标

完全脱离 Hermes Agent 生命周期的独立 Python 进程，自动完成 CellBender 批量样本处理。

## 核心能力

1. **自动发现**: 扫描 `h5ad/` 找所有样本，扫描 `cellbender_output/` 找已完成样本
2. **GPU 驱动检测**: GPU > 15% = CellBender 在跑（比 PowerShell WMI 更可靠）
3. **自我修复**: bash loop 死了 → watchdog 检测空闲 GPU → 启动下一个
4. **卡死检测**: GPU 持续空闲 > 30 分钟 → 杀僵尸进程
5. **自动 ptrepack**: 每个样本 CellBender 完成 → 立即 ptrepack → seurat_h5/
6. **断点续跑**: 已有 filtered.h5 的样本自动跳过
7. **失败重试**: 每个样本最多 2 次，超过则跳过
8. **磁盘状态文件**: `pipeline_status.json` 实时更新完成/待处理列表

## 关键 Pitfall

### `cellbender_output_filtered.h5` 命名陷阱
CellBender 用 `--output` 参数做前缀。`--output cellbender_output.h5` → filtered 文件 = `cellbender_output_filtered.h5`（不是 `output_filtered.h5`）。
所有 `discover_samples()` 必须用此名称。

### Windows PowerShell WMI 不可靠
`is_cellbender_running()` 用 GPU 利用率 > 15% 作为主要信号，不用 PowerShell WMI。GPU 查询失败时回退到 tasklist 检查大内存 Python 进程。

### GPU = 2% 不一定是卡死
MCKP estimator 是纯 CPU 阶段，GPU 会掉到 2%，但进程仍在计算。区分：进程 0% CPU + 日志不增长 > 10 分钟才是真僵死。

## 启动方式

```bash
cd /f/PROJECT_DATA_DIR
nohup python scripts/pipeline_watchdog.py > watchdog_stdout.log 2>&1 &
```

完全脱离，不依赖任何 shell 会话。
