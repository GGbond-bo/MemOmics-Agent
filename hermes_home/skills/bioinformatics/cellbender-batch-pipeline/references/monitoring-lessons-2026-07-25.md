# CellBender 心跳监控铁律 — 2026-07-25 完整教训

> 来源：CellBender 26 样本 Pipeline（2026-07-24 ~ 2026-07-25，跨 2 天 4 轮会话）
> 心跳死亡次数：3 次（全部是 bash `while true` 模式）
> 用户当场纠正次数：4 次

## 根因：5 个问题同时叠加

| # | 问题 | 表现 |
|---|------|------|
| 1 | **监控目标错位** | Agent 盯 monitor.log（辅助摘要），不读 CellBender 自己的 `cellbender_output.log` |
| 2 | **bash 心跳不可靠** | `while true` 循环被 Hermes 会话回收 kill，无自愈，3 次复现 |
| 3 | **数据源单一** | 只看 GPU 快照就下结论（"GPU 3% → 卡死了"），实际在 CPU 密集的 MCKP 阶段 |
| 4 | **不做主动汇报** | 心跳死了几小时，Agent 一次主动汇报都没发 |
| 5 | **推理代替调查** | "filtered.h5=0 → 全白跑了"是推理链，不是调查结果 |

## 真实案例时间线

### 案例 1：monitor.log 误判（04:00-04:30）

```
04:00 - 心跳 dies (Hermes 会话回收)
04:15 - 用户问"进度"
04:16 - Agent 读 monitor.log → epoch 092 → 推断"卡死了，全白跑了"
04:17 - 实际：CellBender cellbender_output.log epoch 106/150，正常训练
04:18 - 用户贴出真实日志："这不是一直在跑吗？你看过这个日志了吗？"
→ Lesson: 必须读 cellbender_output.log（进程真实日志），不是 monitor.log
```

### 案例 2：GPU=2% 误判僵死（04:35-04:57）

```
04:35 - CellBender 训练完成，进入 MCKP estimator（纯 CPU 阶段）
04:36 - GPU 从 60% 掉到 2%
04:40 - Agent: "GPU=2%，可能卡死了"
04:57 - 实际：MCKP 完成，filtered.h5 产出 (166 MB)
→ Lesson: MCKP estimator 是 CPU 独占，GPU 空转正常。检测 growing=True + 文件大小在变。
```

### 案例 3：心跳 3 连死（03:54-05:16）

```
心跳 #1 (PID 35912, bash)     — 04:00 dies with Hermes session recycle
心跳 #2 (PID 14852, v2 buggy) — 读第一行而非最后一行，报"训练开始 03:53:59"
心跳 #3 (PID 37168, bash)     — 04:48 dies again
心跳 #4 (PID 18512, v2.1)     — 05:16 终于稳定工作（auto-discover + 读最后 N 行）
→ Lesson: 必须 Python subprocess.Popen + CREATE_NO_WINDOW 完全脱离
```

### 案例 4：ptrepack --complevel=5 等号 bug

```
watchdog 日志连续出现 3 次:
  ❌ ptrepack failed: returned non-zero exit status 1

根因: --complevel=5 (等号) → ptrepack CLI 不认
修复: --complevel 5 (空格)
命中: 7CL_D2_SD_D5_1, 7CL_D3_1, 7CL_D4_2 — filtered.h5 已生成但 seurat.h5 缺失
```

### 案例 5：ptrepack 输出目录遗忘

```
Agent 说 "ptrepack_output/ 目录不存在" → 用户纠正: "PROJECT_DATA_DIR\seurat_h5 不就是输出目录吗？又忘了？"
→ Lesson: seurat_h5/ 是约定目录，文件名格式 {sample}_filtered_seurat.h5
```

## 三源交叉验证协议

每次查进度（主动或被动），必须同时做这 5 件事：

```
① nvidia-smi          → GPU 实时（利用率% + 显存 + 温度）
② tasklist            → 目标进程是否存活
③ read_file(进程真实日志 最后 50 行) → cellbender_output.log，不是 monitor.log
④ 时间戳校验           → 日志最新行在 5 分钟之前？→ 标记"可能僵死"
⑤ 三条交叉验证一致     → 才能下结论
```

> ⛔ **不查就答 = 撒谎。推理代替调查 = 违规。**

## 阶段感知

CellBender 有多个阶段，GPU 特征完全不同：

| 阶段 | GPU | 日志特征 | 常见误判 |
|------|-----|---------|---------|
| 训练 (epoch) | 80-90% | `[epoch 095] average training loss: ...` | - |
| MCKP estimator | 1-5% | `Working on chunk (5/9)` | "GPU 3% → 卡死了" ❌ |
| Posterior 写入 | 1-5% | `Succeeded in writing posterior` | "没在跑" ❌ |
| 写 output.h5 | 0-2% | `Saved output_filtered.h5` | "训练失败" ❌ |

**铁律：GPU 低 ≠ 卡死。读日志后才判断。**

## 心跳部署标准

```bash
# ✅ 正确：Python 脱离式启动
python PROJECT_DATA_DIR/scripts/heartbeat_v2.py --task "CellBender" --dir PROJECT_DATA_DIR --interval 120 &

# ❌ 错误：bash while true（被 Hermes 回收 kill）
# ❌ 错误：terminal(background=true)（挂在 Hermes 进程树下）
```

## Agent 汇报模板

```
"样本 X/26。{sample} 处于 {阶段}。GPU {利用率}%，{显存}GB。预计 {剩余时间}。
 已完成 filtered.h5: {N}, seurat.h5: {M}。"
```

不准说"没在跑"除非三源交叉验证一致指向该结论。
