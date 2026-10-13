# 占位 task_plan 复发 + 循环检测干预下的收尾形状

> 2026-10-01 实测（memomics-afd2d418，唤醒 #0）。是对 SKILL.md 陷阱 E3c 的**复发补录** + E6 的干预收尾补充。

## 1. E3c 会复发：系统重新生成占位 plan

09-29 该会话已按 E3c 用 `write_file` 重写占位 plan 并闭环过一次；10-01 `[系统唤醒 #0]` 时
磁盘上**又是同一份占位形态**：

| 签名 | 本次实测 |
|---|---|
| 尾注 | `> ⚠️ 此文件由系统自动创建（2026-10-01 21:09:39）` |
| Phases | 只有 `### Phase 1: 执行用户任务` + `- [ ]` + `**Status:** in_progress` |
| Verification Checklist | 仍是 `（待 LLM 根据任务填写具体验证项…）` 占位语 |
| Goal | **脚本头片段**：`suppressPackageStartupMessages({   library(dreamlet)   library(variancePartition` |
| started_at | = 当轮唤醒时刻（21:09:39） |

⇒ **修好 ≠ 永久修好**。任务被重新武装时系统会再生成占位 plan。
**别因为"上次写过 plan"就跳过 read_file 核实**——判据仍是那三条签名。

## 2. 判"上一轮是否已交付"最快的证据 = `.memory/turn_archive/`

```bash
ls -lt --time-style=+%m-%d_%H:%M .memory/turn_archive/ | head -5
```

`turn_<hash>.md` 里是**用户原话 + 我的完整回复 + 结论**，比重新 `ls` 图目录更快确认"上轮交付了什么、
有没有被截断/未兑现的承诺"。本次靠 `turn_9ebf5875e0.md` 一步读到：
「根因 = `layout()` 负高度 → 节点重叠 / 修复 = 固定比例间隙 / 自检 0.00 px / 产物已重出」，
无需再验图即可判"任务已完成"。

## 3. 循环检测干预（OOB「已连续多轮重复…」）到达时的收尾形状

干预**只禁止重复的监控/查看动作，不禁止闭环写盘**。正确形状：

1. 只读核查压到 **1 条** terminal —— 一次查完：产出 `ls -lt` + 脚本 mtime + 进程源（分段哨兵 `== x ==`）
2. `read_file` 只读必需的：`task_plan.md` + 最近 1–2 条 `turn_archive`
3. **`write_file` 重写 task_plan 标 complete** —— 这是 E3c 的闭环动作、**属产出而非监控，必须做**
4. 2–3 句结论：已完成 / 已失败 / 已卡死 + 原因 + 产物路径
5. 本轮到此结束，不再跑任何验证命令

## 4. 重写 plan 时的两条要求

- ⛔ **别把系统生成的错误 Goal 留在头部**：`## Goal` / `## Current Phase` 必须覆盖成本次真实工作
  （本次 = 桑基图 UP/DOWN 标签↔色块对齐修复），产出逐条写**显式文件名 + 字节数**（E4 规矩）。
- 备注里点明"本会话最后一轮是用户知识提问、非任务项"（本次 = MEF2C vs MEF2C-AS1 的注释问题），
  避免下次唤醒把知识问答误当未完成任务又起一轮。