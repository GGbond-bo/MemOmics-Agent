# 服务重启与「改动是否真的生效」验证（2026-10-01 memomics-afd2d418 唤醒 #7 实测）

适用：**改了仓库代码，但运行中的常驻服务（WebUI / 守护进程）仍加载着旧代码**。
典型触发 = task_plan 里挂着「等用户重启后跑 smoke」这类 AI 自认为只能等用户的项（见 SKILL.md 陷阱 E3d / E3e）。

核心命题：**离线全绿 ≠ 改动生效。** 26 个单测通过、模块能 import、带前缀技能名能解析 —— 这些只证明「磁盘上的代码是对的」，
不证明「跑着的进程用的是它」。唯一硬判据 = **服务进程的启动时刻晚于被改文件的 mtime**。

---

## 1. 先认清「哪个进程才是服务」

同一份改动在本机能看到**两个 python.exe，cmdline 都是 `webui\server.py`**。实测（`psutil`）：

| PID | 角色 | 线程 | RSS | 监听 | 父进程 | 启动 |
|---|---|---|---|---|---|---|
| **43864** | **真实对外服务** | 56 | 382.1 MB | **127.0.0.1:8899** | 54408（python） | 10-01 00:04:16 |
| 54408 | **包装壳**（start.bat 起的） | **1** | **1.2 MB** | **无** | 25376（cmd.exe） | 10-01 00:04:16 |

判据（不要靠 cmdline 猜）：

```python
import psutil
PORT = 8899
listeners = {}
for c in psutil.net_connections(kind="inet"):
    if c.status == psutil.CONN_LISTEN and c.laddr.port == PORT:
        listeners[c.pid] = f"{c.laddr.ip}:{c.laddr.port}"     # 端口 → pid
# 再按 cmdline 收集全部 server.py 进程，用 listeners 命中与否分流：
#   命中 → servers（对外服务，stop 先停它）
#   未命中 → helpers（包装壳，随树一起停）
```

- ⛔ **只按 cmdline 过滤**会把包装壳也算成「第二个服务」→ stop 数错、mtime 对比做两遍、汇报里出现两个 PID。
- 壳的特征好认：**1 线程 / 1.2 MB / 无 inet 监听**（真服务是几十线程 + 几百 MB）。
- `taskkill /PID <服务> /T` 会带上壳；壳单独残留时再补一刀。

---

## 2. 生效性判据

| 判据 | 说明 |
|---|---|
| **文件 mtime vs 进程 create_time** | `proc.create_time() > os.stat(file).st_mtime` → 已装载；反之为「早于 → 需重启」。轻量、无需侵入进程。 |
| **模块自证指纹（推荐加固）** | 在被改模块里定义 `ENGINE_VERSION = f"{文件名}@sha256:{前12位}@size:{字节}@mtime_ns:{ns}@git:{短SHA}"`，import 期 `logger.info` 一次 → **重启后**任何一次 `import` 都能打出「这一进程到底加载了哪份代码」。缺它时「运行态旧版本直接证据」无法采集（AI 没法窥探别人的进程内存），只能在裁决 `missing` 里挂着。 |
| 健康检查 | `urllib.request.urlopen(f"http://127.0.0.1:{PORT}/")` → `HTTP 200`。用于判断「服务是活的」以及重启后是否起来。 |

⚠️ **进程判据的四个坑**（详见 `tooling-false-positives.md`）：
① 按镜像名（`python.exe`）枚举会把**瞬时 python 子进程**算成服务（它们恰在改动之后启动 → 误报「已装载」）；
② 探针的 `--match-cmdline` 关键词会写进**探针自己的 argv** → 自匹配；必须排除自身及祖先 PID；
③ 判定前重查 PID 是否仍存在（瞬时进程第二次查即 `NoSuchProcess`）；
④ **判「已装载」要比判「需重启」更严**——任何在改动之后启动的无关进程都会命中「晚于」。

---

## 3. 重启 runbook 的设计（`scripts/restart_service_runbook.py`）

三条设计原则：
1. **默认只读演练**：不打 `--execute` 就只探测 + 打印动作序列 + 健康检查，任何时刻可安全跑。
2. **授权令牌门禁**：`--execute` 必须同时给 `--confirm RESTART-8899`，否则 `exit 1` 拒绝（实测：`--confirm WRONG` → 拒绝执行）。
3. **失败可回滚**：健康检查超时 → 打印日志尾部 → 提示手动 `start.bat` 恢复。

动作序列（六步）：

| 步 | 动作 | 关键参数 |
|---|---|---|
| 1 | `taskkill /PID <服务> /T` 优雅停（再补壳） | 不带 `/F`，给 8 s 宽限 |
| 2 | 轮询端口释放 | ≤30 s；8 s 未退 → `/F /T` 强杀；仍占用则**放弃重启、不改动** |
| 3 | detached 启动 `.venv\Scripts\python.exe webui/server.py` | `cwd=ROOT`；env `HERMES_HOME` / `PYTHONPATH`(ROOT + hermes-agent) / `MEMOMICS_PORT=8899` / `MEMOMICS_RUN_GATE=1` / `PYTHONUTF8=1`；`creationflags=CREATE_NEW_PROCESS_GROUP\|DETACHED_PROCESS`；stdout/stderr → `log/server-runbook-<ts>.log` |
| 4 | 健康检查轮询 | ≤90 s 直到 HTTP 200 |
| 5 | 跑 smoke（`smoke_engine_after_restart.py`） | 期望 `[4]` 打印「晚于引擎 ✅ 已装载新代码」 |
| 6 | 回滚 | 失败 → 日志尾部 25 行 + 提示手动跑 `start.bat` |

⛔ **`start.bat` 有「端口已占用即退出」守卫**（`netstat -ano | findstr ":8899 .*LISTENING"` 命中 → `pause` + `exit /b 0`，打印"服务已在运行"）——
所以**必须先停再起**；指望重跑 start.bat 覆盖是不行的。

---

## 4. 升级路径（顺序不可换）

```
只读预检（端口→pid / 健康检查 / 有无分析进程 / 有无用户活动会话）
   → 写 runbook + dry-run 演练（拿到 exit=0 + 门禁可拒的实测）
   → ask_user 弹窗要一次性授权（措辞里附"会短暂断连、刷新即恢复"，降低决策成本）
   → 用户授权后才 --execute
   → 健康检查 → smoke 对照 → 记录 last_restart_report.json
```

**为什么不能跳第二步直接要授权**：裁决给 owner=ai 的动作带 `blocks`——「无演练回滚前禁止自动重启」。
没演练过回滚就动手，等于拿用户的会话赌；演练是把「AI 能安全执行」这件事变成**可展示的证据**，用户才会勾授权。

**为什么不能自己 kill**：本机无编排、无审批链，WebUI 是用户正在开的界面；kill 属越权，且断连/上下文丢失的责任 AI 担不了。
正确的自证方式是「我把风险都排除完了，只剩你点一下」。

---

## 5. 部署类问题怎么调 debate

topic/context **必须写清运维约束**，否则场景分类会落到 general，拿到通用裁判：
目标进程与端口、是否同一服务、有无编排、用户是否可能在使用、有无演练过的回滚、双方 PID / mtime / 变更清单。

引擎会自动判 `scenario=ops_environment`（label「运维部署生效」），裁判身份换成「SRE 发布经理兼用户会话保护裁判」，
评分维度换成：`service_impact` / `restart_safety` / `evidence_sufficiency` / `authorization_boundary` /
`reversibility` / `post_restart_validation` / `cost_of_inaction`。

本机实测输出形态（**属正常，别当故障**）：
- 裁决 `need_more_info`，`confidence: low`，`decision` = 「先不自行 kill；做只读检查 + 请授权；空闲且授权才重启」；
- `next_actions` 4 条，owner=ai 的带 `blocks`（"未完成前禁止 kill/重启"、"无演练回滚前禁止自动重启"、"未完成前不得宣称改动已生效"）；
- `fallback` = 不重启 + 标记「离线已验证待装载」；
- L1 采样里正反方可能只回**推理草稿**（`draft_only: true`、`content` 为空；裁判整理稿走回退路由修复后仍给出完整 JSON）——
  **裁决本体（verdict / decision / next_actions / missing）依旧可用**，按它执行即可，不要因为草稿态重跑辩论。

---

## 6. 不要做的事

- ❌ 把「服务未重启」写成 ChatGPT 式的"已完成、等待验收"——**没到「进程晚于文件」就不许说生效**（task_plan 挂着的用户项原样保留）。
- ❌ 连续多轮觉醒只重复同一张「等待用户」表 —— 每轮先问「AI 现在能干掉哪一半」（E3d 原则），本轮答案就是预检 + runbook。
- ❌ 同一议题硬凑辩论轮次 —— 同议题已辩过且活选项 <2 时按 L0 跳过并写明理由。
- ❌ 动 `.loopx/registry.json` / `.task_state.json` 等系统文件 —— 写变更单 + `ask_user` 给选项，用户批准才动。

---

## 7. ⛔ 不要用「工具返回值里有没有新字段」当生效判据（2026-10-01 memomics-afd2d418 实测，判决性反例）

本次会话连续十几轮把一条**自造判别法**当验收标准交给用户：

> 「手动调 `skill_evolution(query_logs)`，返回 JSON 里含 `engine` 字段 = 新模块生效；没有 = 旧模块。」

用户答复「我这就重启 MemOmics 服务」后，同一调用实测（本轮）**既没有 `engine` 字段**、`proven_runs` 也变成空数组
（`"尚未注册或目录不存在"`）—— 而更早的轮次曾记录**同一调用**「返回含 `engine=…@sha256:7e22c3abad22…`」+「找到 5 条记录」。

⇒ 同一命令、同一技能名，**跨轮返回不一致**。这条判别法**两头都没被验证过**：既没做「旧态必为假」的阴性对照，
也没做「新态必为真」的阳性对照，却被写成让用户执行的验收口。

| 规则 | 说明 |
|---|---|
| ① 工具返回值 ≠ 进程内部状态的可靠观测量 | 返回值可能被不同调用路径加工（自动自进化路径每次 `exec_module` 重载 vs 常驻 server 里手动分发路径吃旧模块），也可能被截断/归一化。用它的**形状差异**反推「进程加载了哪份代码」是**循环论证**——你想证明的正是「这条路走的是哪个模块」，而返回值本身由那个模块产生。 |
| ② 自造判别法交付给用户前，必须在**两个状态各跑一次** | 阳性对照 + 阴性对照，两次原始输出都贴出来。只在一侧观察过一次就写进「判别法 / 验收标准」＝ 把未验证的假设变成用户的动作。 |
| ③ 可交付的硬判据只有两条 | **进程 `create_time` vs 被改文件 `mtime`**（§2 表第一行）+ 模块自证指纹 `ENGINE_VERSION`。重启后**在新进程里**独立 import 该模块并打印指纹，才是「新代码已装载」的正向证据。 |

⛔ **发现自己前若干轮把未验证的判别法讲给用户之后**：**同一轮就纠正** —— 明确说「之前给你的判别法不成立，证据是 X」，
并把 task_plan / 记忆里的错误表述一并改掉，别让下一轮把它当基线继承（呼应 SKILL.md 陷阱 C5b「错信息不被继承」）。

---

## 8. 探针 / runbook 脚本的家在 skill 目录，不在会话 `results/` 目录

本轮唤醒按记忆里的写法去查 `results/memomics-afd2d418/scripts/deploy_smoke_probe.py` → `No such file or directory`；
脚本真实位置 = `hermes_home/skills/bioinformatics/wakeup-progress-check/scripts/`（同目录还有 `restart_service_runbook.py`、
`verify_wakeup.sh`、`verify_watcher.sh`）。会话 `scripts/` 里另有一份**早期同名脚本**（`smoke_engine_after_restart.py`，4.2 KB），
两者内容不同、**不要混用**。

```bash
# 一次列全，别只查一个位置就下「不存在」结论
ls -l results/<sid>/scripts/*.py \
      "hermes_home/skills/bioinformatics/wakeup-progress-check/scripts/"*.py 2>&1 | head -20
```

→ 可复用脚本一律从 skill 目录调用：`python "E:/MemOmics-Agent/hermes_home/skills/bioinformatics/wakeup-progress-check/scripts/<脚本>"`。
→ 首查 0 命中 ≠ 不存在（SKILL.md 陷阱 C5）：**两个位置都 `ls` 过**才可以对外说「不存在」。