# Windows CellBender 两大致命错误修复手册

> 2026-07-24 验证于 26 个骨骼肌样本 (PROJECT_DATA_DIR\)

## 错误 A: ckpt.tar.gz 训练后解压失败

### 现象

```
cellbender:remove-background: Inference procedure complete.
cellbender:remove-background: Attempting to unpack tarball "ckpt.tar.gz" to ...
cellbender:remove-background: Failed to unpack existing tarball.
FileNotFoundError
```

### 根因

Windows 临时文件管理器在 CellBender 训练期间锁定了 `%TEMP%\tmpXXXX\*_train.loaderstate` 文件，导致 ckpt.tar.gz 写入不完整。训练完成（150 epochs）后 CellBender 尝试解压 ckpt 做 posterior 计算时失败。

### 修复步骤

```bash
# 1. 清理 Windows 临时目录（启动 pipeline 前）
rm -rf /c/Users/USERNAME/AppData/Local/Temp/tmp* 2>/dev/null

# 2. 删除失败样本的 ckpt（如果 pipeline 没自动删）
rm -f PROJECT_DATA_DIR/cellbender_output/{failed_sample}/ckpt.tar.gz

# 3. 重新跑该样本（训练算力没浪费，但约需 8 分钟从头训练）
```

### 受影响的样本 (2026-07-24)

- 4CL_SD_D4_1 (33 min)
- 4CL_SD_D5_1 (34 min)
- 7CL_D2_SD_D5_1 (37 min)
- 7CL_D3_1 (44 min, chunk 192/192 跑完了但 ckpt 坏了)

---

## 错误 B: ArrayMemoryError — 后处理稀疏→密集转换 OOM

### 现象

```
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 2.05 GiB 
for an array with shape (13749562, 20) and data type float64
```

发生在 `compute_denoised_counts` → `_chunk_estimate_noise` → 
`apply_function_dense_chunks` → `log_prob_sparse_to_dense`

### 根因

CellBender 在估计背景噪声时，将稀疏矩阵转为密集 numpy 数组。对于高基因数样本（如骨骼肌 ~47K genes），中间数组可达 1-2 GiB float64。在多僵尸进程残留的情况下（RAM 被吃光），分配失败。

### 修复步骤（按优先级）

```bash
# 方案 1: 提高 low-count-threshold（推荐，对去污染质量无实质影响）
--low-count-threshold 15  # 从 5 提高到 15，排除 ~30% 低表达噪音基因

# 方案 2: 减少分析液滴数（如果方案 1 不够）
--total-droplets-included 15000  # 从 25000 降到 15000

# 方案 3: 杀僵尸释放 RAM（必须 + 方案 1/2 配合）
taskkill /F /IM cellbender.exe
taskkill /F /IM python.exe  # 仅杀 CellBender 子进程
```

### 受影响的样本 (2026-07-24)

| 样本 | 分配失败大小 |
|------|-------------|
| 4CL_SD_D4_2 | 2.05 GiB (13.7M × 20 float64) |
| 4CL_SD_D5_2 | 1.19 GiB (5 × 32M int64) |
| 7CL_D2_SD_D4_2 | 1.05 GiB (5 × 28M int64) |

---

## 错误 C: monitor.log 输出检测误报

### 现象

`monitor.log` 显示 `done=0/26` 但 `dir cellbender_output/*/cellbender_output_filtered.h5` 显示已有 2+ 个产出文件。

### 原因

`run_pipeline.py` 的进度 JSON 文件 `_pipeline_progress.json` 在监控脚本读取时还未刷新（写入延迟）。

### 修复

不要信任 JSON 里的 `done_count`。直接统计磁盘上的实际文件：

```bash
# 正确的完成数
ls PROJECT_DATA_DIR/cellbender_output/*/cellbender_output_filtered.h5 2>/dev/null | wc -l
```
