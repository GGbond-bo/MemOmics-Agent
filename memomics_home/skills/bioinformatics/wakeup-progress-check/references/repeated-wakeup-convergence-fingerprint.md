# 终态会话的重复空转唤醒：指纹核验 + 收敛终点

适用：任务早已交付，会话处于终态，系统仍连续多轮唤醒（本配方来自 2026-10-13 memomics-be17649b
竞品定位交付会话，实测连续 **11 轮**空转）。每轮都重跑同一套核验 = 白烧 token + 把唤醒历史堆进
上下文（E3 恶性循环的燃料）。

## 1. 一条命令取全指纹（守 E6「round 内 terminal ≤1 条」）

```bash
cd <会话根> && echo '== canonical ==' && md5sum <核心数据文件> && \
ls -l --time-style=+%m-%d_%H:%M <核心数据文件> && \
echo '== deliverables ==' && ls -l --time-style=+%m-%d_%H:%M <交付目录>/ && \
echo '== delegation batches ==' && ls -1t <delegation 缓存>/live/ && \
echo '== new files ==' && \
find <会话目录> -newermt "<task_plan mtime>" -type f \
  | grep -vE '\.loopx|token_usage|system_log|\.log|task_plan|notes\.md|REQUIREMENTS' | head -20; \
echo '== DONE =='
```

四个面一次拿全：**核心产物的 md5 + 字节数** / **交付件清单** / **回执批次目录清单** /
**晚于基线的非系统文件**。分段哨兵（`== x ==` + 结尾 `== DONE ==`）同时消除
「空输出 = 0 命中 还是 命令失败」的歧义。

## 2. 判据：md5 是终态会话最硬的变化指纹

| 观察 | 判定 |
|---|---|
| **核心产物 md5 与前几轮同值**（记「第 N 次同值」）+ 字节数同 + 交付件 mtime 同 | 零变化 ⇒ **零写入**（不重渲染、不补账、不重派） |
| `live/` 批次目录数与最新批次与前几轮同 | **无新回执**（不是没查，是查了没变） |
| `find -newermt` 只命中 `.loopx/` `token_usage.jsonl` `notes.md` `review/` 等**记账文件** | 无新交付物（记账文件不算产出，同 Step 2「系统内部文件不算新产出」） |

⚠️ 用 **md5 而非 mtime** 作主指纹：mtime 会被无关重写刷新，md5 同值才证明「内容一字未动」；
⚠️ 交付件（DOCX/HTML/md）也要同时报**字节数**，只报 md5 不足以让用户/下一轮确信。

## 3. 回执重放判定的升级口径：键存在 ≠ 本批贡献

回执核销不能只查「键在不在产物里」——键早就可能由**别的批次**写入了。必须做**内容同一性检验**：
从本批回执里取几条**逐字片段**（arch / evidence_quote），去落盘产物里 `grep` 命中 ⇒ 本批确实贡献过
⇒ 是重放；若键在但片段**对不上** ⇒ 才是真缺口。

## 4. 收敛终点（关键，最易漏）

1. **第一轮**：跑第 1 节那条指纹命令 → 出证据表（项/实测值/判定）→ 写一行台账/plan 记录。
2. **同一轮**：把「收尾决策」做成 `ask_user(kind=clarify)` **弹窗一次**（选项 = 停掉唤醒 / 保持现状 /
   补产物 / 装缺失依赖 / 开新任务，推荐项标 `recommended`），而不是在正文里写一句开放式问句。
   ⛔ **每议题只发一次**。
3. **弹窗发出之后**：唤醒轮收敛为**一行状态**（「无变化 + 未做任何写入」）——
   ⛔ 不再重跑指纹命令、不再重发同一张表、不再追加记录。长度逐轮递减直到静默。
   （与 §弹窗已发 ≠ 循环会停 一致：契约干净时唤醒源是 LoopX registry / task_state，
   只能由用户一句话结束，Agent 侧继续核验没有任何作用。）

## 5. 「会话要求路径不存在」警告的第三种形态：字符串截断

前两种已在 SKILL.md Step 2.5 记录（① 误报 → search_files 核实；② 真阴性 → 问用户）。
本例是**第三种**：警告文本里的路径本身就是**前缀截断**的（如
`<数据目录> transfer enables a`，尾部明显断在单词中间），而同一路径在会话锚点里
标注「已实测存在，24,214,769 B」。

→ 判定 = **展示层截断，不是文件缺失**：路径被截断到固定宽度属渲染行为，**不核实、不打扰用户、
  不作废路径**；汇报里一句话说明「路径告警系字符串截断假警报，完整文件在盘」即可。
→ 判据：警告里的路径**结尾不像完整文件名**（断在词中/无扩展名/恰好卡在固定字符数）⇒ 截断型；
  结尾完整但仍报缺失 ⇒ 才按前两种形态（search_files 核实）处置。

## 6. 追加锚点：行内审计链模板（本会话第 12 轮实测，2026-10-13）

本会话的 task_plan 是**模板变体三**：既无 `## 🏁 唤醒 #N 记录` 块、也无 `## 红线与约束`，
而是在 `### Phase 1` 下用 `- [x] #11 …` / `- [x] #12 …` **行内 bullet 串**记每轮核销。

| 环节 | 本类模板的正确做法 |
|---|---|
| 取号 | 链尾最大 `#NN` + 1（read_file 看链尾即可）——`#84` 标题截断 / `#90` 裸 bullet / `#116` body 污染三个取号陷阱都是为 `🏁` 块设计的，**此处不适用** |
| 追加锚点 | **唯一的 `**Status:** completed` 行**：`old_string="**Status:** completed"` → `new_string="<新 bullet>\n**Status:** completed"`（本类模板里它只出现一次、天然位于链尾之后），实测一次成功 |
| ⛔ 别用 | Phase 标题行（多个 Phase 都含 `### Phase`）、`**Status:**` 其它形态 |
| 压缩 | 链内 ≥5 条同类核销 bullet **不必压缩**——每条 2–4 行且各带**不同批次编号/证据**（`deleg_xxx`、md5 第 N 次同值），与 `🏁` 块里"逐字相似的终态记录"性质不同，压缩会丢批次证据 |

## 7. `find -newermt` 基线的隐藏陷阱：`Runtime State.started_at` 不是基线（2026-10-13 实测）

新模板的 `## Runtime State` 段含 `started_at`（本会话 = 01:57）。它**不是**"上次记账时刻"——
拿它当基线会把**整个会话期间**的记账文件全列出来：`.memory/turn_archive/*`、`.memory/conclusions.md`、
`notes.md`、`REQUIREMENTS.md`、`review/assets.json`、`log/run_record_*.json`，
看上去像"未记账产出"，极易触发**多余的补账 / 复查回合**（E3 循环的燃料）。

→ 基线**只能是 `task_plan.md` 自身 mtime**：`ls -l --time-style='+%Y-%m-%d %H:%M' task_plan.md`
  取 ISO 时间直接喂 `find -newermt`（勿用 `awk '{print $6,$7,$8}'`——中文区域会给"8月 9 10:47"，
  find 报 `cannot figure out how to interpret`）。
→ 判"未记账产出"前先自问：这文件是**产物**还是**本会话自己的记账文件**？后者不算产出、不补账
  （与 §2 表格第三行、Step 2「系统内部文件不算新产出」同源）。

## 8. 无进程类会话不要为"凑三源"跑 GPU/进程源

文献 / 交付物 / 知识产权类终态会话**没有 Rscript/python 分析进程**，Step 3 的进程源与 GPU 源全是空跑。
⛔ 不要为凑三源去跑 `nvidia-smi` / `tasklist`（纯耗 token + 触发循环检测，见陷阱 E6）。
等价强度的替代就是 §1 那条指纹命令 **+ 唤醒源两文件**：

| 源 | 命令 | 判读 |
|---|---|---|
| 唤醒源 | `grep -m1 '"status"' .loopx/registry.json` + `head -c 300 .task_state.json` | `status: active` ⇒ LoopX 周期唤醒；`armed: true` + `reason: user message…` ⇒ 用户消息武装；两者皆非 ⇒ 回头查完成契约（E5 三分法） |
| 载体 | `md5sum <核心产物>` | 同值 = 零漂移（记"第 N 次同值"） |
| 交付 | `ls -l --time-style='+%Y-%m-%d %H:%M' <交付目录>/` | 字节 + 时间戳全同 = 未触发重渲染 |

本会话第 12 轮实测：`registry.status=active` + `task_state.armed=false/rounds_started=8`
⇒ **LoopX tick 唤醒**（非完成契约缺陷、非用户消息）⇒ 零写入，只追加一行审计 bullet 后收尾，
并在回复里一句话告知用户"停掉唤醒的唯一开关是 `status: paused` + `quota.compute=0`"。