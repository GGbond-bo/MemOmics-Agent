# Zombie Cascade — 内存饥饿重现配方

## 触发条件

1. `run_pipeline.py` 父进程被 Hermes 会话终止（`taskkill` / 会话回收 / 上下文压缩）
2. CellBender 子进程（通过 `subprocess.run()` 启动）变为孤儿，继续占用 GPU+RAM
3. 用户/Agent 多次重启 pipeline → 每次重启又产生新的孤儿
4. 累积 3+ 个孤儿后，剩余 RAM 不足 → 后续样本在 `compute_denoised_counts` 阶段崩溃

## 真实案例 (2026-07-24, PROJECT_DATA_DIR)

### 僵尸进程清单

| PID | 样本 | RAM | 状态 |
|-----|------|-----|------|
| 11928 | 4CL_SD_D5_2_scRNA | 6.6 GB | 2.5 天僵尸，GPU 46% |
| 39624 | 7CL_D2_1_scRNA | 4.6 GB | 2.5 天僵尸 |
| 7192 | 7CL_D2_2_scRNA | 1.5 GB | 2.5 天僵尸 |

### 孤儿输出目录（无 filtered.h5）

```
cellbender_output/
├── 4CL_SD_D5_2_scRNA/   ← 只有日志，无 h5
├── 7CL_D2_1_scRNA/      ← 空日志文件
├── 7CL_D2_2_scRNA/      ← 只加载了数据
└── 7CL_D2_SD_D4_1_scRNA/ ← 文件被锁定
```

### 错误症状

**Sample 1 (4CL_SD_D4_1_scRNA)**: 
```
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 262. MiB 
for an array with shape (34318820,) and data type float64
```
→ 出现在 `compute_denoised_counts` → `_chunk_estimate_noise` 阶段
→ 根因：3 个僵尸吃掉了 11+ GB RAM，导致 numpy 无法分配连续 262 MB

**Sample 2 (4CL_SD_D4_2_scRNA)**:
→ 150 epochs 全部跑完，posterior.h5 保存成功
→ 但 `compute_denoised_counts` 阶段崩溃，无 filtered.h5

**Sample 3 (4CL_SD_D5_1_scRNA)**:
→ 仅 216 秒即崩溃（epoch 9），可能被 OOM killer 杀

## 清理步骤（已验证有效）

```bash
# 1. 查所有 cellbender 进程（注意：进程名是 python.exe，需查命令行）
powershell "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*cellbender*' } | Select-Object ProcessId, CommandLine"

# 2. 逐个杀
taskkill /F /PID <PID>

# 3. 确认 GPU 释放
nvidia-smi

# 4. 清理孤儿目录（保留可能有用的日志）
# 用 Python shutil.rmtree 处理文件锁定
python -c "import shutil; shutil.rmtree(r'PROJECT_DATA_DIR\cellbender_output\<sample>', ignore_errors=True)"

# 5. 验证清理
ls cellbender_output/  # 应为空
nvidia-smi  # utilization < 10%
free -m     # > 30 GB free
```

## 预防措施

1. **pipeline 启动前执行清理清单** (见 SKILL.md)
2. **用 `subprocess.Popen` + `CREATE_NO_WINDOW` 代替 `start /B`** — Popen 返回 PID 便于追踪
3. **pipeline 脚本加超时 kill** — 每个 CellBender 子进程设 `timeout=3600`
4. **定期巡检** — LLM 应每 30 分钟读一次日志 + 检查进程表
5. **备份日志** — `run_pipeline.py` 用 `"w"` 模式会覆盖历史，启动前先备份
