# CellBender 必传参数检查清单

> **触发条件**：每次启动 CellBender 前，必须逐项检查以下参数。遗漏任何一项都会导致严重性能问题。

## 完整参数模板

```bash
cellbender remove-background \
  --input <input.h5ad> \
  --output <output.h5> \
  --fpr 0.01 \
  --epochs 150 \
  --learning-rate 0.0001 \
  --total-droplets-included 25000 \
  --expected-cells 5000 \
  --low-count-threshold 5 \
  --cuda
```

## 参数逐项说明

| 参数 | 值 | 遗漏后果 |
|------|-----|---------|
| `--cuda` | (flag) | **GPU 完全不使用**，CPU-only 运行，epoch 速度 10-20x 慢 |
| `--total-droplets-included` | 25000 | **加载全量液滴**（可达 100 万+），epoch 速度 5-10x 慢，GPU 利用率 <5% |
| `--expected-cells` | 5000 | CellBender 自动估算不准确，显式指定 |
| `--fpr` | 0.01 | 官方默认值，不要改 |
| `--epochs` | 150 | 官方默认值 |
| `--learning-rate` | 0.0001 | 官方默认值 |
| `--low-count-threshold` | 5 | 官方默认值 |

## 诊断：遗漏症状速查

### 遗漏 `--cuda`
- GPU 利用率 <5%
- 显存占用 <500 MB
- 日志无 "CUDA" 关键词
- checkpoint 中无 `random.cuda` 文件

### 遗漏 `--total-droplets-included`
- epoch 速度 >100 秒（正常 ~30 秒）
- GPU 利用率 <10%
- 日志显示 "Including XXX empty droplets" 数量 >50,000
- 日志显示 "plus an additional 20000 barcodes" 行中 empty droplets 数远大于正常

### 两者都遗漏
- epoch 速度 >150 秒
- GPU 利用率 ~4%
- 显存 ~3300 MB（仅数据加载，非训练）
- 预计完成时间 >7 小时（正常 <2 小时）

## 诊断方法

当怀疑参数缺失时，**不要凭日志推理，直接对比已完成样本的命令行**：

```bash
# 读取当前样本的命令行（日志第1-2行）
head -3 <sample>/cellbender_output.log

# 读取已完成样本的命令行
head -3 <completed_sample>/cellbender_output.log

# 逐一对比每个参数
```

## 修复流程

1. `taskkill /F /PID <pid>` 杀掉当前进程
2. 清理旧 checkpoint：`rm <sample>/ckpt.tar.gz`
3. 用完整参数重新启动
4. 等第一个 epoch 完成后验证速度（应 ~30 秒/epoch）
5. 确认 GPU 利用率 >30%
