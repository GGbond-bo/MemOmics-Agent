# Case Study: Background Install Neglect Pattern

> 日期: 2026-07-29
> 会话: ArchR 安装 (R 4.5.3 + Rtools45)
> 严重程度: 🔴 致命 — 浪费 3+ 小时重试
> 铁律违规: 铁律 -1 (未绑定 tool call), 铁律 -2 (未多源验证), 铁律 16 (长任务监控)

## 事件链

```
T0: Agent 启动 `terminal(background=True)` 装 ArchR
T1: Agent 回答用户数据问题，未检查后台进程状态
T2: 后台进程崩了 (segfault / Bioconductor 失败)
T3-T5: 3 轮对话过去了，Agent 全程未主动检查
T6: 用户问"装好了吗？" → Agent 才发现进程早死了
```

## 根因：回合制架构下的"启动即遗忘"

```
Agent 的真实架构（不是 Agent 自己想象的）：

  你发消息 → [Agent 被唤醒] → 开后台进程 → 回复 → [Agent 关机]
                                                    ↑
                                          T3~T6 之间，Agent 不存在
```

`notify_on_complete` 在以下情况失效：
- 进程 exit code ≠ 0 → 通知可能不发
- 用户发了新消息 → 新 turn 覆盖了旧通知
- Agent 在下一个 turn 没主动 `process(action='list')`

## 为什么 Agent 不主动检查

| 借口 | 现实 |
|------|------|
| "后台装了 20 分钟，我等不了" | 可以查中间日志，不需要等结束 |
| "用户问其他问题时我会顺便查" | Agent 没查。直接回答数据问题了 |
| "notify_on_complete 会通知我" | 没生效，进程早死了 |

## 正确做法（已经在两条铁律中）

### 铁律 16: 长任务监控 — 三源交叉验证
查任何 >10 分钟的后台任务进度时，**必须同时查三个独立数据源**：
① `nvidia-smi` → GPU 实时
② `tasklist` → 目标进程是否存活
③ `read_file(进程真实日志 最后 50 行)` → 安装日志/训练日志

### 铁律 -2: 多源验证 — 系统状态必须查了再答
回答系统状态前 → 必须先查再答。不查就答 = 撒谎。

## 防御实现

每个 turn 开头（用户发消息后）强制：

```python
# Step 0: 检查是否有活跃/残留的后台进程
active = process(action='list')
dead = [p for p in active if p.status == 'exited' and p.exit_code != 0]
if dead:
    report_to_user(dead)  # 主动汇报，不等人问
    fix(dead)             # 立即修复
```

## 与已有失败模式的区别

| 已有模式 | 本模式 |
|---------|--------|
| "没在跑"但实际在跑 (推理错误) | 启动了但没检查 (主动性缺失) |
| 心跳承诺未实施 (撒谎) | 启动了但忘了盯着 (疏忽) |
| write_file ≠ execute (动作混淆) | background ≠ done (生命周期误解) |

## 应该写入哪个 skill

- `windows-bioinformatics-batch-processing` SKILL.md — 铁律中新增"安装类任务也必须三源监控"
- `agent-loop-engineering` — Known Failures 表新增本条目
- `atac-seq-memomics` — 安装指南强调"不要 fire-and-forget"
