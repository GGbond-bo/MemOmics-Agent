# Stale 根 task_plan 与唤醒空转（2026-10-19 实测）

## 症状

系统唤醒一轮轮触发，理由是「主线任务 Phase 1 还在 `in_progress`」，
但任务在别的目录里其实早已完成并核验通过。注入的 `task_plan.md 主线区摘要` 也是旧内容。

## 根因：计划被写进了子目录，根计划没人更新

- 系统（完成契约 / 自检循环）读的固定是 **`results/<sid>/task_plan.md`（根）**。
- 实际执行时任务常拆成子工作流，进度被写进 `results/<sid>/<sub>/task_plan.md`
  （本例：根停在 `Phase 1 in_progress`、mtime 22:00；`task2/task_plan.md` 23:02 已是全 `complete`）。
- 根那份的 mtime 落后于实际完成时间 → 契约判定"还有未勾选待办" → 唤醒不歇。
- **注入摘要看着像"系统最新状态"，其实只是根文件的渲染**，不能当事实源。

## 处置流程（唤醒第 1 步）

```bash
ls -la results/<sid>/task_plan.md results/<sid>/*/task_plan.md   # 比 mtime，找最新
grep -n '^[[:space:]]*- \[ \]' results/<sid>/task_plan.md         # 根还有多少未勾选
```

1. **以最新 mtime 的那份为事实源**，把根同步成终态：
   - 主线区（`## 🏁` 之前）**不得有任何 `- [ ]`**
   - 每个 Phase 补 `**Status:** complete`
   - 补 `## Final Outputs`（只放**本机**真实存在且非空的产物）
2. **终态三源复核**（都做过才算数）：远端 `ls -la` 看对象大小/mtime + 验收报告 CHECK 行 + 本地产出逐个 `-s` 非空。
3. **清掉会误判的路径写法**（见下）。
4. 重跑 `rail_review(post)` 通过 + `skill_evolution(record_run)` 留档。

## 产出路径写法（会决定契约能不能满足）

| ❌ 会踩 | ✅ 改写 |
|---|---|
| 主线区列出远端绝对路径当产出：`/cluster/.../Muscle_..._L2_umap.rds` | 单列一行注明「远端，不参与本机校验」，或写不带盘符的相对片段 `user/.../x.rds` |
| 花括号合写：`.../scripts/{merge_X.R, verify_X.R}` | 一行一个完整路径（花括号会被当成一个怪路径去 stat） |
| 只在正文提一句「产物已生成」 | 每个声明路径用**完整 `E:/...` 绝对路径**逐条列出（validator 按盘符/`data|results|output/` 前缀识别） |

原则：**能被 validator 解析成"本机路径"的字符串，必须真的存在于本机且非空。**

## 配套工具技巧

- **`read_file` 去重后拿不到内容**：压缩后复读同一文件会返回
  `{"status":"unchanged","content_returned":false}`，正文不返回，于是"记得读过但看不到内容"。
  **绕过：带显式 `offset`/`limit` 再读一次**（如 `offset=1, limit=120`），即可拿到全文。
- **7 GB 级对象别重读**：让作业脚本自己写一份 `verify_report.txt`
  （逐条 `PASS: <检查> <结果>` + `#TASK:OUTPUT`），唤醒核查只 `grep` 这份报告（秒级），
  配合一次远端 `ls -la` 核对大小/mtime 即构成三源。本例 4 项 CHECK 全 PASS 就是这样留证的。

## 反面清单

- ⛔ 看到唤醒说 in_progress 就去集群 `pgrep` 找进程 —— 先比 task_plan 的 mtime，进程早没了。
- ⛔ 用注入摘要当"最新状态"，回头再手写一份新计划 —— 会与磁盘上的子计划互相打架。
- ⛔ 为了让契约通过去删声明路径 —— 该做的是把远端路径写对位置，不是瞒报产物。