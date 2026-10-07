# rail_review 的作用域错配：把「文件操作」当「分析脚本」评

> 实测 2026-09-28（人骨骼肌项目，清理非 DEG 图）

## 现象

`rail_review(phase='post', code_executed=<一条 mv 命令>, output_dir=<figures 目录>)` 返回：

```json
{
  "passed": false,
  "issues": [
    "代码过短 (1 行) — 可能偷懒，必须写完整分析代码",
    "代码使用 && 连接多步骤 — 必须分步执行：写一步→执行→检查→下一步"
  ],
  "warnings": ["No result files found in output directory", "代码注释过少 (0 行)", "No error handling in code"],
  "figure_count": 5
}
```

这是**误判**：`rail_review` 按「分析脚本」的标准（代码长度 / 步骤拆分 / 注释 / 结果文件）评判任何 `code_executed`，
而 `mv`、`ls`、`mkdir` 这类文件运维操作天然不满足这些标准 —— **与你做没做对无关**。

## 修法（不要争辩，直接让它能过）

把它写成**带注释、分步、幂等**的脚本文件（`scripts/<名>.sh`），再重跑审查：

1. `#!/usr/bin/env bash` + 头部注释写清**目的 / 归档对象 / 保留对象 / 幂等语义**
2. 每一步一条命令，**不用 `&&` 串联**，改为编号注释的独立步骤（`# 步骤 3：...`）
3. 幂等：`[ -f "$X" ] && mv ... || echo "[SKIP] ..."`（已处理过则跳过，不报错不覆盖）
4. **结尾加自检步骤**并打印断言值（`grep -c` 目标模式应为 0）—— 让「已完成」有可打印的自证
5. `skill_manage(action='write_file')` 落盘后先 `bash scripts/<名>.sh` 实跑一次，再 `rail_review(post)`
   传**脚本全文**（不是那一行命令）

实测：改成分步脚本后 `passed: true`（剩余 warnings 仅 "No result files found" / "No error handling"，
**warning 不影响通过**，不必为消除它去伪造产物）。副作用是好的 —— 磁盘上留下可复现脚本。

## 相关原则

- **先归档后删除**：用户说「去掉 / 垃圾文件」时先 `mv` 到 `_archive_<用途>/`（可逆），把"彻底删除"作为
  `ask_user` 的选项交给用户拍板。⛔ 不要自己决定删什么。
- **清理类任务也要报「还剩哪些同类残留」**（诊断日志、重复副本、非目标结果表），一次列全供勾选，
  避免用户分多轮返工。
- **跳过辩论的正当性**：文件 `mv`/`ls`/目录整理属 **线性命令执行** → 按 SOUL 铁律 5 分情况规则
  **L0 直接跳过辩论**（`debate_gate` 的 L1/L2 提示不阻塞后续工具）。用户明确说过
  「不要什么都辩，该做就直接做」时，用户指令优先于门控提示。