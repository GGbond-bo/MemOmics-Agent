# Session Resumption Protocol: Stale task_plan.md Detection

> **问题**：跨会话恢复时，`task_plan.md` 可能来自已完成/旧会话的残留，描述的完全是另一个任务。直接信任它 → 汇报错误状态 → 用户纠正（或更糟：不纠正，继续沿着错误方向执行）。

## 触发条件

- Agent 新 turn 开始（用户发消息 / 上下文恢复 / 系统唤醒）
- 读取 `task_plan.md` 后，描述的 Phase/Task 与 session 目录下的文件不匹配
- 或用户问"进度"/"在跑吗"类问题时

## 四源交叉验证协议（在 task_plan.md 的基础上多加一层）

```
Step 1: 读 task_plan.md → 获取声称的 Current Phase
Step 2: tasklist → 正在运行的进程（Python/R）
Step 3: nvidia-smi → GPU 状态
Step 4: ls 输出目录 → 实际产生的文件（时间戳、大小）
Step 5: read_file system_log.jsonl → 最近工具调用了解实际任务上下文
Step 6: 交叉验证：task_plan.md 声称的 Phase vs 实际运行的进程 vs 实际产出文件
```

## 三种结果处置

### A. 匹配：task_plan.md 与实际情况一致
→ 继续按 task_plan.md 执行

### B. task_plan.md 描述的任务已完成，但新任务正在跑
```
示例：task_plan.md 说 "Phase 1: CellBender in_progress"
      但实际：CellBender 26样本已于 7月27日完成
      实际跑的是：Rscript 06_coverage_peaks.R (ArchR ATAC-seq)

→ 汇报："task_plan.md 是旧残留（CellBender 已完成），实际任务：[从进程+产出推断]"
→ 更新 task_plan.md 为实际任务
```

### C. task_plan.md 描述的任务已完成，无新任务
→ 汇报："所有 Phase 已完成，无后台任务在跑"

## 2026-07-29 案例

| 数据源 | 发现 |
|--------|------|
| task_plan.md | Phase 1: CellBender 去背景 in_progress |
| tasklist | Rscript PID 2884 (1.38GB) + PID 54384 (7.7MB) |
| nvidia-smi | GPU 3% idle — 这是CPU密集型任务 |
| ls 输出 | ArchR_Output/project_clustered.rds (29MB, 03:26), GroupCoverages/Clusters/ C1-C9 done |
| system_log | CRE保守性框架研究 + ArchR安装脚本 |

**结论**：task_plan.md 是 CellBender 旧残留（7月27日已完成），实际任务是 ArchR ATAC-seq pipeline (Step 5: GroupCoverages, 23/57 组完成)。

## 关键原则

> **task_plan.md 是参考，不是权威。系统状态（进程+GPU+文件）才是权威。**
> 
> 当 task_plan.md 与系统状态矛盾时，以系统状态为准，然后更新 task_plan.md。
