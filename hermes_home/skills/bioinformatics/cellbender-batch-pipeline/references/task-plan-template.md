# task_plan.md 模板（含环境探测段）

## 用途

长任务分析开始前创建，作为 Agent 的外部工作记忆。上下文压缩/重启后恢复状态。

## 模板

```markdown
# Task Plan: {分析描述}

## Goal
{一句话分析目标}

## Environment（分析启动时自动探测）
| 工具 | 路径 | 来源 |
|------|------|------|
| cellbender | {find_tool("cellbender")} | {source} |
| ptrepack | {find_tool("ptrepack", "tables")} | {source} |
| python | {sys.executable} | sys.executable |

## Current Phase
Phase 1

## Phases

### Phase 1: {阶段名}
- [ ] {子任务}
**Status:** pending

### Phase 2: {阶段名}
**Status:** pending

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|

## Decisions Made
| Decision | Rationale |
|----------|-----------|
```

## Environment 段的设计原则

| 应该记录 | 不应该记录 |
|----------|-----------|
| ✅ 工具路径（ptrepack/cellbender/python） | ❌ SOUL.md 铁律（审查、三源验证） |
| ✅ Python 版本、关键包版本 | ❌ Agent 行为约束 |
| ✅ 本任务特有环境变量（TMPDIR 等） | ❌ Skill 操作步骤（已在 SKILL.md） |
| ✅ 关键决策及理由 | ❌ 通用分析参数（已在 SKILL.md 参数表） |

## 探测时机

**必须**在写 task_plan.md 之前执行：
1. `shutil.which("cellbender")` → 找到或告警
2. `find_tool("ptrepack", "tables")` → 找到或标记"h5py fallback only"
3. `sys.executable` → Python 路径

## 关键规则

- **task_plan.md 是唯一信任的状态源** — 不要凭记忆恢复
- **不重新执行已标记 complete 的 Phase**
- **同一错误不用相同方法重试 3 次以上**
- **Environment 段写入后，所有脚本从 Environment 段读取路径，不硬编码**
