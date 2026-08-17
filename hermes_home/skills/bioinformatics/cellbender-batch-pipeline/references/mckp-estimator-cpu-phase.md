# MCKP Estimator CPU Phase — CellBender 收尾阶段

> 创建: 2026-07-25
> 事件: 4CL_SD_D4_1_scRNA 训练完成但 output.h5 未出现，GPU 掉到 2%
> 结论: 纯 CPU 计算，不是卡死

## 时间线

```
04:32  posterior.h5 写入完成 (1.5 GB)
04:35  PDF + cell_barcodes.csv 写入完成
04:35  "Computing target noise counts per gene for MCKP estimator"
04:35+ MCKP estimator CPU 计算中 (GPU 2%, VRAM 5GB, 进程 16GB RAM)
```

## MCKP 是什么

Minimum Cost Knapsack Problem estimator — CellBender 的最后一步。对每个基因计算目标噪声计数，用于去污染后的表达矩阵。纯 CPU 计算，不涉及 GPU。

## 症状 vs 僵死区别

| 信号 | MCKP 正常 | 真的僵死 |
|------|----------|---------|
| GPU | ~2% | ~2% |
| 进程存活 | ✅ | ✅ or ❌ |
| RAM | 16GB (不变) | 16GB (不变) |
| CPU 时间 | 持续累加 | 0% |
| 日志 | 停在 MCKP 那行 | 停在任意位置 |
| ckpt.tar.gz | 不再增长 | 不再增长 |

## 决策

**等，不要 kill。** 大样本（5 万基因）MCKP 3-5 分钟。小样本更快。

如果 10 分钟后仍无 output.h5：
1. 检查进程 CPU 时间是否仍在累加
2. 如果 CPU = 0% → 真僵死 → kill 重跑
3. 如果 CPU 持续 → 继续等

## 验证成功

output.h5 出现后 → CellBender 会自动应用 FPR → 生成 output_filtered.h5。
