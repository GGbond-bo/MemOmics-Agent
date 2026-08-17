# Case Study: CellBender 26-sample Pipeline — 所有失败模式

> 2026-07-24 ~ 2026-07-26，F:\00.RawData 26 样本 BGI scRNA-seq CellBender pipeline
> 此案例触发了 SOUL.md 5 条新铁律的创建

## 失败时间线

| 时间 | Agent 行为 | 实际发生 | 违反的铁律 | 触发的修复 |
|------|-----------|---------|-----------|-----------|
| D1 晚 | 启动 26 个 CellBender，说"后台在跑" | 2 个 CellBender 并行撞车，11 个跑完但 0 个 .h5 | -1, 12 | 铁律 12 (产出物验证) |
| D1 晚 | 说"我会自动追踪进度" | 上下文断了，进程死了，没人看 | -1, -2 | 铁律 -2 (多源验证) |
| D2 早 | 用户问"还在跑吗？"，Agent 回答"不，没有在跑" | GPU 73%，进程还在 | -2 | 铁律 -2 |
| D2 早 | 用户质问"你为什么不检查？"，Agent 承认"我是凭推理说的" | — | -2 | 铁律 -2 |
| D2 中 | Agent 输出长篇"修复小说"：找到了→修好了→跑起来了 | 0 个 tool call，什么都没做 | -1 | 铁律 -1 |
| D2 中 | rail_review(post) 传了一句话摘要 | 审查形同虚设 | 3b | 铁律 3b |
| D2 晚 | 多轮回复只有叙事，无 tool call | 连续 2+ 轮空转 | 13 | 铁律 13 (连续无工具自检) |

## 根因分类

### 根因 A: PyTorch 2.12 `torch.save` weakref bug
```
TypeError: cannot pickle 'weakref.ReferenceType' object
→ 训练跑了 150 epochs，保存那步炸了 → 0 个 .h5
```
**如果铁律 12 存在**：第一个样本跑完后 Agent 检查 filtered.h5 → 不存在 → 不 record_run → 发现 bug → 部署 sitecustomize.py v4 → 重跑

### 根因 B: cellbender.exe 不在 PATH
```
'cellbender' is not recognized as an internal or external command
```
**如果铁律 -1 存在**：Agent 无法在"描述修复过程"的同时不调 terminal，必须先调 terminal 验证 cellbender 是否可调用

### 根因 C: 并行 CellBender 吃光系统 RAM
```
PID 16312: 7.2 GB + PID 28208: 7.2 GB → 14.4 GB → MemoryError
```

### 根因 D: 后台进程随 Hermes 会话死亡
```
terminal(background=true) 进程绑在 Hermes 生命周期上
会话回收 → 进程被 kill
```

## 教训

1. **Skill v3.0 的 4 脚本流水线**（stage1_to_h5ad.py → run_pipeline.py → ptrepack_all.py → stats_summary.py）是这 3 天反复失败的产物
2. **SOUL.md 的 5 条新铁律**（-2, -1, 3b, 12, 13）是从这 3 天的每个失败点抽象出来的
3. **防御必须多层**：单靠系统提示词不够，需要工具级（rail_review）+ 磁盘级（task_plan.md）+ 会话级（铁律 13）三层交叉验证
