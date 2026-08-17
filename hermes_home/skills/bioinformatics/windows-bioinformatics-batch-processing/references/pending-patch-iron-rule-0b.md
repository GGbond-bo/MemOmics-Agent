# 铁规 0b: 主动监控协议 — 补丁待应用到 windows-bioinformatics-batch-processing SKILL.md

> 日期：2026-07-24
> 原因：skill_manage patch 受 review-turn 检查限制，暂时无法直接修改 SKILL.md
> 本文件包含待应用的补丁内容，下次能 patch 时应用

## 待插入位置

在 `## 🔴 铁规 0: 先调查再回答` 和 `## 🔴 铁规 2: Windows 进程生命周期` 之间。

## 完整补丁内容

---

## 🔴 铁规 0b: 主动监控协议 — 日志驱动，不等不问【v1.2 新增】

**背景**：2026-07-24 CellBender D3 — Agent 在同一连续会话中说"我会监控"但从没主动读日志。用户两次问进度，Agent 两次凭历史失败记录断言"管道停了"。教训：监控 = 读日志文件，不是许诺读日志。

### 三线监控法（每轮巡检必做）

| 监控线 | 读什么 | 回答什么 |
|--------|--------|---------|
| ① 总体进度 | `{work_dir}/logs/pipeline.log` 最后 50 行 | 已完成/失败/进行中样本列表 |
| ② 当前样本 | `{work_dir}/cellbender_output/{sample}/cellbender_output.log` 最后 5 行 | 当前 epoch、预估剩余时间 |
| ③ 磁盘产出 | `dir {work_dir}/cellbender_output/*/cellbender_output_filtered.h5` | 实际落盘文件数和大小 |

### 汇报格式

```
## 📊 Pipeline 进度（查了，不是猜的）

### 已完成（k/26）
| # | 样本 | 大小 | 耗时 |

### 失败
| # | 样本 | 原因 |

### 当前进行中
样本 X/26: {name}, epoch A/150 (~B%), 预计剩余 ~C min
GPU: {util}%, {used}/{total} MB
```

### 巡检频率
- 训练中：不等用户问，每完成一个样本主动汇报
- 用户问"进度"：立即执行三线监控 → 汇报
- Pipeline 完成：立即汇报 + 失败样本清单

### ⛔ 绝对禁止
- ❌ 说"正在监控"但不去读日志 — 这不是监控
- ❌ 凭历史失败记录推断当前状态 — 日志写着前 6 个失败 ≠ 现在停了
- ❌ 用 GPU 占用率代替日志读取

**关联**: `agent-loop-engineering` 已知失败模式 "没在跑但实际在跑" + Deflection Pattern
