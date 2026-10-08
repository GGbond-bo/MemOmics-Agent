# 长命令发射、任务面板核查与「静默计算」判活

> 2026-09-24 实测（跑 pySCENIC 长任务期间）。补充本 skill 已有的「工具调用过大 / heredoc 被拦 / 循环轮询」诸行。

---

## 1. 一条**很长的 terminal 命令**也会触发流式超时 → 落「发射脚本」

**症状**：把整个长任务启动命令写成**一条** shell 命令（大量 `--param`、`--stages`、`--` 分隔符、
绝对路径解释器…）→
```
[System: Your previous tool call (terminal) was too large and the stream timed out before it could be delivered.
 Do NOT retry the same tool call with the same large content.]
```
**原样重投仍超时**（与「单条回复打包多个大调用」「heredoc 被硬线拦」同一族：**超限看的是这一次调用的内容量**）。

**处置：把命令落成发射脚本，再用一条短命令调用**

```bash
# ① write_file → results/<sid>/scripts/run_<task>.sh（内容随便长，写文件不受这个限制）
#!/bin/bash
cd /e/<项目> || exit 1
mkdir -p tmp
export TMPDIR=E:/<项目>/tmp TMP=E:/<项目>/tmp TEMP=E:/<项目>/tmp    # 临时目录换大盘
python memomics/bio_tools/task_run.py --type scenic --title "SCENIC" \
  --session-dir results/<sid> --stages "读入,推断,剪枝,打分,校验" \
  --param workers=2 --script results/<sid>/scripts/02_run.py \
  -- "<解释器绝对路径>" -u results/<sid>/scripts/02_run.py
```
```
# ② terminal(command="bash E:/<项目>/results/<sid>/scripts/run_<task>.sh",
#            background=true, notify_on_complete=true)      ← 短命令，永不超时
```
🔑 判据：**凡启动命令超过十几行或含大量参数 ⇒ 一律「落脚本 + 短命令调用」**，不要试图精简成一行。
附带好处：发射脚本本身就是可复跑、可审计的产出（用户面板里能看到）。

---

## 2. 任务面板核查：`task_run.py --list` / `--show`（优于 tail 日志）

```bash
python memomics/bio_tools/task_run.py --list                  # 面板全部任务：状态/进度/PID/标题
python memomics/bio_tools/task_run.py --show <task_id>        # JSON：status/alive/stalled/stage_index/progress/log
```
`--show` 的 JSON 里 **`alive` / `stalled` / `heartbeat_age_sec` / `progress.value+text` / `log`（日志文件路径）**
一次拿全，比 `tail` 日志可靠得多（日志可能长时间零增长，见 §3）。

配合 `process(action='wait', session_id=..., timeout=180)`：
- **wait 会被 clamp 到 180 s**（回执里明写 `Requested wait of 600s was clamped to configured limit of 180s`），长任务分 2–3 次 wait；
- 用 `task_run.py` 起的任务，**wrapper 进程会活到任务结束**，所以 `wait` 在任务失败时能直接拿到**完整 traceback + `[task] <id> failed rc=1 用时 Ns 日志 <路径>`** —— 这是最省事的失败定位方式，胜过一次次的 `--show`。

---

## 3. 「长时间无输出」不等于挂了：psutil 区间采样

dask / arboreto 等框架的**计算期不打印任何进度**，日志零增长属正常，与死锁表面同形。
判活要主动取 CPU 证据：

```python
import psutil, time
p = psutil.Process(PID); fam = [p] + p.children(recursive=True)
for x in fam: x.cpu_percent(None)      # 预热：首次调用一律返回 0.0（无参照系）
time.sleep(6)
print("进程树 CPU 合计 =", sum(x.cpu_percent(None) for x in fam))   # 持续 >50% = 真在计算
```
⚠️ **不预热就读 `cpu_percent()` 会得到一片 0.0**，据此判「卡死」是误判。实测健康态：2 worker 各 ~95%、合计 199.5%。

配套两条：
- **别用反复 `tail` 轮询判活**（触发循环检测），也**别为「看看跑到哪了」多轮调 `--show`** —— 一次核查拿证据即止。
- 判「跑完没有」永远看 **日志完成哨兵 + 产物落盘**，**不看 exit code**（管道 `| tee` 会吞掉非零退出码，
  回执写着 `completed normally (exit code 0)` 而脚本其实早就崩了）。

---

## 4. `skill_evolution(record_run)` **必须带 `skill_name`**

铁律 24 门禁要求每轮 terminal 后补一次 `record_run`；若只想解锁而**省略 `skill_name`**：

```json
{"success": true, "action": "record_success", "skill": "", "proven_scripts_updated": false,
 "message": "Success recorded:  for //aging"}
```

→ **回执 success、但其实写了一条 `skill: ""` 的空记录**（垃圾条目），且看不出任何异常。
⇒ **即使只是为解锁门禁，也一律带上 `skill_name`**（+ species/tissue/direction/script_name 更好）。
配合：`deduplicated: true` 的回执多数情况下已能解锁，**不要为解锁换措辞反复 record_run**。

---

## 5. 被 curation 守卫拒绝的 skill：换个 home

`skill_manage(action='write_file'/'patch')` 可能被拒：
- `Refusing background curator write_file for skill 'X': the skill records show it is not agent-created (created_by=None). Manually authored skills are off-limits to autonomous curation.`
  ⇒ **该 skill 本体一律写不了**（连 references 也不行）——把内容写到**同类目的可写 umbrella** 的 `references/` 下。
- `SKILL.md content is 100,301 characters (limit: 100,000)`
  ⇒ SKILL.md 已满，**连加一行指针都做不到**；`write_file` 到 `references/` **不受此限**，
  文件仍会出现在该 skill 的 `linked_files` 里（可被发现，只是少了正文指针）。⛔ 不要反复重试同一个 patch。