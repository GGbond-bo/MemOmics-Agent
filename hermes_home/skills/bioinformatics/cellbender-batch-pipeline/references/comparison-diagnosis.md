# CellBender 故障诊断：对比法

## 核心原则

当某个样本的 CellBender 表现异常（慢、GPU 不工作、loss 不收敛等），**不要凭日志推理根因，直接对比已完成样本**。

## 诊断步骤

### Step 1: 对比命令行参数

```bash
# 异常样本
head -3 <problem_sample>/cellbender_output.log

# 正常样本（已完成）
head -3 <working_sample>/cellbender_output.log
```

逐项比对：
- `--cuda` 是否存在
- `--total-droplets-included` 值是否一致
- `--expected-cells` 值是否一致
- 其他参数是否有差异

### Step 2: 对比数据加载阶段输出

```bash
# 加载阶段的关键行（第10-25行左右）
head -25 <sample>/cellbender_output.log | grep -E "(Including|Using|empty droplets|droplets-included)"
```

关注：
- `Using 5000 probable cell barcodes, plus an additional X barcodes, and Y empty droplets`
  - Y 值异常大（>50,000）→ 可能遗漏 `--total-droplets-included`
- `Including X features in the analysis`
  - X 值差异过大 → 输入数据可能不同

### Step 3: 对比 epoch 速度

```bash
grep "seconds per epoch" <sample>/cellbender_output.log
```

正常范围：**25-40 秒/epoch**（--total-droplets-included 25000 + --cuda）
异常：>100 秒/epoch → 参数遗漏

### Step 4: 对比 GPU 使用

```bash
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
```

正常：GPU 利用率 30-80%，显存 >5000 MB
异常：GPU <10%，显存 <4000 MB → --cuda 遗漏或数据加载瓶颈

## 实际案例：4CL_SD_D4_2 (2026-07-26)

| 检查项 | 异常样本 | 正常样本 (4CL_SD_D4_1) | 差异 |
|--------|---------|----------------------|------|
| `--cuda` | ❌ 无 | ✅ 有 | **致命** |
| `--total-droplets-included` | ❌ 无 (全量 140 万) | ✅ 25000 | **致命** |
| epoch 速度 | 187.7 秒 | ~30 秒 | 6x 慢 |
| GPU 利用率 | 4% | 40-80% | 10x 低 |
| empty droplets | 1,338,883 | 191 | 7000x 多 |

**修复**：kill 进程 → 加 `--cuda --total-droplets-included 25000` 重跑 → epoch 速度恢复到 33 秒，GPU 47%。
