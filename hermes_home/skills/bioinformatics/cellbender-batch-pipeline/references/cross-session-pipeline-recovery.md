# Cross-Session Pipeline Recovery — 跨会话恢复清单

## 触发场景

Pipeline 在后台运行 → Hermes 会话结束 → 进程树被杀 → 下次唤醒时 pipeline 完全死亡。脚本可能被移入 `_TRASH/`，心跳/进度文件全部消失。

## 恢复协议（按顺序执行，不可跳过）

### Step 1: 读 task_plan.md → 提取上下文

- 读会话 task_plan.md（`results/<session_dir>/task_plan.md`）
- 提取：原始目标、样本列表、参数、已完成样本
- ⚠️ 不信任 checkbox 状态 — 仅作为"应该是什么"的参考

### Step 2: 磁盘三源验证

```
① find <output_dir>/*/cellbender_output_filtered.h5 → 真实完成数
② ls -lt 检查文件修改日期 → 排除旧跑遗留（pitfall 41）
③ nvidia-smi + tasklist → 确认无残留进程
```

### Step 3: 查找被清理的脚本

如果 task_plan 标记"脚本已写"但磁盘找不到：

```
search_files("run_*.py", path=<output_dir>)
ls <output_dir>/_TRASH/
ls <output_dir>/_DEL*/
```

常见：脚本被手动或自动化清理移入 `_TRASH/`。恢复：`cp _TRASH/run_remaining.py .`

### Step 4: 清理残缺产出

检查每个 running/pending 样本目录：
- 有 `ckpt.tar.gz.tmp` → 写入中途被杀，不可恢复 → 删
- 有 `ckpt.tar.gz` → CellBender checkpoint hash 不可靠（pitfall 1b）→ 删，从头跑
- 有 partial `cellbender_output.h5` 但无 `filtered.h5` → 删
- 有旧跑遗留的 `filtered.h5`（mtime 很早）→ 保留（跳过该样本）

```bash
# 清理示例
rm -f <dir>/ckpt.tar.gz.tmp <dir>/ckpt.tar.gz <dir>/cellbender_output.h5
# 不删 filtered.h5（如果是有效的已完成产出）
```

### Step 5: 确认脚本完整性

- 读恢复后的脚本，验证参数与 task_plan.md 一致
- 验证路径（input .h5ad 位置、output 目录）在当前环境可达
- 验证工具路径（CellBender/Python）来自 environment.json 动态探测

### Step 6: 重启 + 验证

```bash
# 后台启动（脱离式，不是 terminal background）
terminal("cd <output_dir> && python run_remaining.py",
         background=true, notify_on_complete=true)

# 15 秒后验证
sleep 15
nvidia-smi → GPU > 15%？
cat _pipeline_progress.json → current sample?
tasklist → python/cellbender 进程存在？
```

### Step 7: 重新部署心跳

```bash
terminal("python heartbeat_v2.py --task <name> --output-dir <dir> --interval 120",
         background=true)
# 5 秒后验证心跳日志写入
cat monitor_v2.log | tail -3
```

### Step 8: 更新 task_plan.md

- 更新 Phase 状态（done/running/pending 逐样本标注）
- 更新 Runtime State 表
- 在 Errors Encountered 记录：第N次重启、原脚本在 _TRASH、清理了哪些残缺产物

## 常见失败模式

| 症状 | 根因 | 修复 |
|------|------|------|
| task_plan 标记 ✅ completed 但脚本不存在 | 脚本被移入 _TRASH/ | Step 3 |
| 上次跑完的样本 filtered.h5 消失 | pipeline 重启时 clean 逻辑误删 | Step 4 — 清理前先确认 mtime |
| 心跳日志为空 | 心跳随 session 一起死 | Step 7 — 重新部署 |
| task_plan.md 内容过时 | Agent 在跨 session 间做了工作但没更新 session task_plan | 每次 Phase 变更后立即 write_file 更新 task_plan |

## 与现有 pitfall 的关系

- **pitfall 41**（旧跑遗留产物假完成）→ Step 2 的 `ls -lt` 日期验证
- **pitfall 44**（_TRASH 脚本恢复）→ Step 3-4
- **pitfall 17**（心跳随 pipeline 死）→ Step 7
- **pitfall 1/1b**（ckpt hash 不可靠）→ Step 4 清理理由
- **pitfall 43**（跨会话任务污染）→ Step 1 只读当前 session task_plan
