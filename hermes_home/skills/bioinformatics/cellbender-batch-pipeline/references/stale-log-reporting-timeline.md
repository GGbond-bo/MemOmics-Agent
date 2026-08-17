# 读陈旧日志汇报假进度 — mtime 不检查

> 来源: CellBender D4 — 2026-07-26 16:20-16:44, 用户激烈纠正

## 事件时间线

| 时间 | 事件 |
|------|------|
| 15:54 | `4CL_SD_D4_2_scRNA` 训练完成 (epoch 150/150) |
| 15:54-16:20 | MCKP estimator chunk 5/9 → `_ArrayMemoryError` 崩溃 |
| 16:20 | `cellbender_output.log` 最后一次写入 (mtime = 16:20) |
| 16:20-16:44 | CellBender 进程已退出，GPU 3% 空闲 |
| 16:44 | 用户问"进度" |
| 16:44 | Agent: `read_file("cellbender_output.log")` → 读到崩溃日志 → 汇报"MCKP 又崩了" |
| 16:44 | **没有检查 `stat cellbender_output.log` 的 mtime** |
| 16:44 | 用户: "你他妈的，蠢货...现在以及下午4点44了，你还在看之前的日志" |

## 根因

`read_file()` 返回文本内容，**不返回文件 mtime**。Agent 读到了 24 分钟前的崩溃日志，将其当成"当前实时状态"汇报。

Agent 没有执行以下必要步骤：
1. 读日志前 → `stat` 文件 mtime
2. 比较 mtime 与当前时间
3. 如果 mtime > 5 分钟前 → 交叉验证 GPU + 进程

## 铁律（已写入 cellbender-batch-pipeline pitfall 34）

```
每次 read_file(日志) 后，必须同时 stat 该文件：

① mtime < 5 min  → 日志活跃，内容可信
② mtime 5-30 min → 可能已停滞，交叉验证 GPU + tasklist
③ mtime > 30 min → 日志已死
   禁止用其内容汇报"当前状态"
   只报告: "最后记录在 HH:MM，之后无更新"
```

## 正确调查流程（16:44 应该做的）

```
1. stat cellbender_output.log → mtime = 16:20 (24 分钟前)
2. 判定: 日志可能已死 → 不可直接汇报
3. nvidia-smi → GPU 3% → 确认无 CellBender 在跑
4. tasklist → 无 CellBender 进程
5. ls cellbender_output/4CL_SD_D4_2_scRNA/ → 无 output.h5, 无 filtered.h5
6. 汇报: "4CL_SD_D4_2 最后记录在 16:20 (MCKP 崩溃)，24 分钟无更新。GPU 空闲。需要介入。"
```

## 违规检测

```
read_file(path) 返回值被用于"当前状态"断言
  → 检查是否在同一轮调用了 stat path
  → 没有 → 违规
```
