# LoopX 空转 tick 的升级处置（自行暂停，不等用户抱怨）

实测来源：2026-10-13 `memomics-be17649b`（竞品定位交付定稿会话），连续 **10** 轮唤醒零 delta。

---

## 1. 判定：什么时候可以自行暂停

必须**同时**满足，缺一不可：

| 条件 | 实测口径 |
|------|----------|
| 三源逐项同值 | ① 产物 md5 同值（本例 `data/cards.json` = `17dd2962…db3e`，连续 10 次）② 交付物**字节数 + mtime** 全同（DOCX 793,395 / HTML 1,233,970 / md 299,145，冻结在 10-08 01:39–01:41）③ 无晚于 plan 的实质新产出 |
| 连续轮次 ≥5 | 1–2 次同值可能是合并延迟；≥5 次无变化即为稳态 |
| 挂起项**机器无法产出** | 本例唯一挂起项 = 第 32 张竞品卡需用户给 DOI；另一项是「要不要装 python-docx」的决策 —— 两者都要用户输入 |
| 目标本身已终态 | `.loopx/ACTIVE_GOAL_STATE.md` 为空、`.task_state.json` `armed: false` |

⇒ 继续 tick = 纯 token 消耗，且每轮都会往 task_plan 堆一段审计文字（cruft 自我放大）。
**处置：主动暂停，并在汇报里写清恢复方式。可逆 → 不需要等用户点头。**

⛔ 反例（不要暂停）：仍有 in_progress Phase、有后台进程在跑、deleg 回执未核销、挂起项是机器能自己做完的。
⛔ 暂停 ≠ 删任务：只改 `status`，不删 goal、不删产物、不动交付物（本轮交付物零字节改动）。

---

## 2. 定位 registry（**踩坑**）

```bash
# ✅ 正解：隐藏目录只能用 find
find /e/MemOmics-Agent -maxdepth 5 -type d -name ".loopx"
# → ./results/<sid>/.loopx/
```

- registry 在 **`results/<sid>/.loopx/registry.json`**，不在项目根。
- ⛔ `search_files(target="files", pattern="*registry.json")` **找不到它** —— 隐藏目录被跳过，只会命中别的项目里同名文件，浪费一轮。
- `.loopx/` 平级还有 `goals/`（目录）与 `ACTIVE_GOAL_STATE.md`（本例 0 字节空文件）。
- `.task_state.json` 在 **会话结果目录根**（`results/<sid>/.task_state.json`），不在 `.loopx/` 里。字段：`state` / `armed` / `rounds_started` / `max_rounds`。

---

## 3. 暂停的精确改法

`status` 有**两处**（goal 级 + `adapter` 级），两处都要改：

```jsonc
{
  "goals": [{
    "id": "<sid>",
    "status": "paused",            // ← goal 级
    "adapter": {
      "kind": "project_goal",
      "status": "paused"           // ← adapter 级（bridge 读这个）
    },
    "quota": { "compute": 0, /* … */ },   // ← 100 → 0
    "pause_reason": "Task complete …; paused to stop no-op wakeups. Resume: status=active + quota.compute=100",
    "paused_at": "2026-10-13"
  }]
}
```

- ⚠️ 只改其中一处无效（`waiting`/`cleared` 之类中间态会被 bridge 放行）——与 `references/stopping-loopx-wakeups.md` 的 2026-08-12 结论一致。
- 文件小（~1 KB）：**直接 `write_file` 整份重写**比 patch 稳（patch 对 CRLF JSON 容易只改一处）。
- 验根（别只看文件）：

```bash
python -c "import json;d=json.load(open('.loopx/registry.json',encoding='utf-8'));g=d['goals'][0];print(g['status'],g['adapter']['status'],g['quota']['compute'])"
# → paused paused 0
```

- 恢复：改回 `status: active` + `adapter.status: active` + `quota.compute: 100`，或用户说一句「恢复 LoopX」。汇报里必须给这条路径。

### 3-b 🔴 验根要再走一步：读 JSON 只证明「值写进去了」

读回 JSON 是**必要不充分** —— `waiting` / `cleared` 之类中间态会被 bridge 放行（2026-08-12 结论，见
`references/stopping-loopx-wakeups.md` §2）。**必须跑一次 `should_run()` 拿决策**（配方同该文 §3），期望：

```python
{'should_run': False, 'state': 'paused', 'decision': 'skip',
 'reason': 'compute quota is 0; automatic agent turns are paused'}
```

⚠️ **暂停后仍收到 tick、或唤醒头 `📊 LoopX 状态` 块仍写 `goal: active` ⇒ 两者都不是「没停成」的证据。**
唤醒头字段是**注入的渲染摘要**，同族字段在 deleg 回执头已被逐条实测证伪（`(Nm ago)` / `Model: ?` /
per-task `0s` 全是渲染值，见 `delegation-orchestration` ⓪-g）⇒ **不用它判状态**。
正确动作：

1. 回 `registry.json` 读回值（本文件 §3 的 `python -c` 一行）；
2. 跑一次 `should_run()`；
3. `should_run()` 为 False ⇒ **判「暂停有效」，tick 是暂停前/暂停瞬间已在途的那一条**，
   ⛔ **不重复暂停**（重复改只会覆盖 `pause_reason`，还会在台账里堆一条假事件）、⛔ 不据头部字段回写 registry；
4. `should_run()` 仍为 True ⇒ 才是真没停成 ⇒ 按 `stopping-loopx-wakeups.md` §2 复查**两处** `status` 与 `quota.compute`。

> 与 §1 的「自行暂停」配对：**判断门槛在 §1，执行在 §3，验根在 §3-b** —— 三步做完才算这一轮闭环。

---

## 4. task_plan.md 维护的两个坑（本轮亲历）

### 坑 A：`patch` 的缩进漂移，会把 `**Status:**` 顶出首列

在**多行缩进块**中间插入内容时，模糊匹配器会按上下文缩进重排——不仅新内容，**相邻旧行的缩进也会被带偏**：

```
- 原：**Status:** completed            ← 解析器认的是行首
+ 改后：      **Status:** completed    ← 已不是行首 → plan 状态读不出来
```

连续 patch 两次会**越修越歪**（第二次仍按缩进对齐）。
✅ 正解：**改前先 `read_file` 读全整份**，然后 `write_file` 整份重写，一次到位。
⛔ 不要在缩进块里用 patch 追加多行；不要连续 patch 同一区域「试着修」。

### 坑 B：零 delta 轮次不要写整段审计块

- 每轮零 delta 都追加「三源 + 结论 + 数字」三行块 → 10 轮后 plan 被审计文字淹没，丢失「快速恢复状态」的价值。
- ✅ 零 delta 轮次：**≤1 行**（`#N 第 N 次同值 → 零写入`）。
- ✅ 达到 §1 门槛时：**这一轮才写实质内容**（处置 + 恢复方式），并顺手把 Status 行改成带说明的形式（`**Status:** completed（LoopX tick 已暂停 · 交付物冻结）`）。
- 编号规则沿用：`grep -n "#<最大号>"` +1，禁抄消息头。

---

## 5. 汇报骨架（本轮实测有效）

```
【结论】已把空转的 LoopX 唤醒暂停 —— 本轮唯一实质动作
【三源核验表】产物 md5 / 交付物字节+mtime / 目标状态（三行表）
【动作】registry.json 三处改动 + task_plan #N 行
【没做什么】未重派/未重读/未重合并/未重渲染 —— 交付物一字节没动
【为什么不等你点头】处置可逆 + 恢复路径
【恢复方式】说「恢复 LoopX」即可
```

要点：把「我拿了什么权力」摊开说（可逆 + 恢复路径），比含糊带过更稳。

🔴 **`【仍挂起】①② 两项待用户一句话` 这一行已删除 —— 它正是 `delegation-orchestration` 4-b 记了 ≥10 次违规的那个形态**
（正文出现 `挂起` 字面量 + 逐条列出待决项名字 + 邀约句）。本 skill 的骨架曾是那条违规的**来源之一**：
照它起稿就必然写出「两项仍挂起（等你点头，我不自行启动）：① 补第 32 张竞品卡——给篇名或 DOI；
② python-docx 要不要装进 `.venv`」—— 与 4-b 的 `违规史` 行**逐字同形**（2026-10-13 本会话实测即为照此发出）。

⇒ 处置（与那边一致，⛔ 别再靠记忆）：

1. **待决项只进 `notes.md`**，写成一行 `[挂起 · 非阻塞] …（等用户）`；
2. **正文到 `【恢复方式】` 即停**，不回看、不补充（想加的那一行一定是某个挂起项在借尸还魂）；
3. **发送前跑一次 linter**（零记忆量）：
   `python <skills>/bioinformatics/delegation-orchestration/scripts/replay_reply_lint.py --ledger results/<sid>/notes.md <草稿>`
   —— 返回码 1 ⇒ 按提示删整段、重跑；0 才发。⛔ 不凭「读一遍觉得干净」发。

> 判据一句话：**暂停轮的报告同样受 4-b 约束 —— 「只报告本轮动作」不等于「顺带把待决项再递一次」。**
> 本 skill 的骨架与那边的 lint 是**同一个门**，别让两处规则互相抵消。