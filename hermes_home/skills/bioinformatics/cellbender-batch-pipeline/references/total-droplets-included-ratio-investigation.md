# `--total-droplets-included` 比例调查 (2026-07-29)

## 问题

用户质疑：6 个人脑样本，CellBender 检出 11K-25K 细胞，用 `--total-droplets-included 25000` 是否足够？

最紧的样本 3506H_4 检出 24,617 细胞，只剩 383 空滴在包含集内。

## 调查方法

1. 查 `cellbender remove-background --help` 获取官方参数说明
2. 查 GitHub broadinstitute/CellBender 官方 Tutorial
3. 查 GitHub Issues #414, #442
4. 读 6 个样本的实际日志（`cellbender_output.log`）

## 证据

### 证 1: 官方 Tutorial 比例

```bash
# generate_tiny_10x_dataset.py 示例
cellbender remove-background \
  --input tiny_raw_feature_bc_matrix.h5ad \
  --output tiny_output.h5 \
  --expected-cells 500 \
  --total-droplets-included 2000
```

**比例 = 4:1**（2000 总液滴 / 500 预期细胞）。

注释："do not do any preprocessing or feature selection or barcode selection first."

### 证 2: 官方 `--help`

> "The number of droplets from the rank-ordered UMI plot that will have their cell probabilities inferred. **Include the droplets which might contain cells. Droplets beyond TOTAL_DROPLETS_INCLUDED should be 'surely empty' droplets.**"

关键句："Droplets beyond ... should be 'surely empty'"——此值之外的液滴标记为确定空滴。

### 证 3: GitHub Issue #414

标题："Problem when input total-droplet is lower than predicted expected-cells"

当 `--total-droplets-included` < CellBender 自动估计的细胞数 → `ValueError: cannot convert float NaN to integer` 崩溃。

### 证 4: 我们的实际日志

**2309H_3:**
```
Using 6844 probable cell barcodes, plus an additional 18156 barcodes, and 14451 empty droplets.
```
- 包含集内: 25,000 (6844 + 18156)
- "确定空滴"（包含集外）: **14,451**
- 检出细胞: 22,767
- 包含集内空滴: 2,233

**3506H_4（最紧的）:**
```
Using 10430 probable cell barcodes, plus an additional 14570 barcodes, and 14462 empty droplets.
```
- 包含集内: 25,000
- "确定空滴"（包含集外）: **14,462**
- 检出细胞: 24,617
- 包含集内空滴: **仅 383**

"Largest surely-empty droplet has 779 UMI counts" — 确定空滴最大 UMI 远低于细胞平均（1,799）。

## 结论

| 方面 | 判定 |
|------|------|
| **环境 RNA 估计受影响？** | **否** — 14,000+ 确定空滴是环境估计的主力，不依赖包含集内的空滴 |
| **结果质量？** | 6/6 正常收敛，去除率 10-17%，无 NaN |
| **比例够吗？** | **勉强够，但不推荐** — 官方用 4×，我们最紧的只有 1.04× |
| **风险？** | 若任一样本细胞数 > 25,000 → Issue #414 NaN 崩溃 |

## 建议

| 场景 | `--total-droplets-included` |
|------|---------------------------|
| 预期细胞 5K-10K | 25,000 ✅ |
| 预期细胞 10K-20K | 30,000-40,000 |
| 预期细胞 20K+ | 40,000-50,000 |
| 不确定 | `max(expected_cells × 4, 25000)` |

**通用公式**: `total_droplets ≥ max(expected_cells × 4, expected_cells + 5000)`

### 如果在包含集内只有几百空滴（如 3506H_4 的 383），为什么环境估计不受影响？

CellBender 的环境 RNA profile 来自两部分：
1. 包含集内的空滴（383 个）— 用于训练中的 batch 采样
2. **包含集外的"确定空滴"（14,000+）**— 用于环境 RNA 的先验估计

主力是后者。这就是为什么即使包含集很紧，环境估计仍然稳定。

## `--total-droplets-included` 与 `--expected-cells` 的关系

- `--expected-cells`: 用于设定 CellBender 的细胞数先验（帮助模型初始化）。**不设** → CellBender 自动估计（通常偏低 30-50%）
- `--total-droplets-included`: 设定参与推断的液滴上限
- 两者独立，但 `--expected-cells` 的自动估计值 **不能超过** `--total-droplets-included`

如果设 `--expected-cells 5000` 但 CellBender 最后检出 24,617 细胞 — **没问题**，这说明模型在训练中学到了更准确的细胞分布。先验只是个初始猜测，不是硬限制。

但如果设 `--total-droplets-included 10000` 而实际有 24,000 细胞 — **就会崩溃**（Issue #414）。
