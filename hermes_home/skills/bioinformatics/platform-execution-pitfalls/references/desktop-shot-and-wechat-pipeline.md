# 桌面截图 → 落盘 → 推微信：这条流水线的解释器与错误判读

2026-09-25 实测（memomics-40625339 提出；memomics-8ca667e4 闭环）。
用户任务原话：`python scripts/desktop_shot.py --send-wechat --caption "MemOmics 桌面截图"`，
要求「把命令输出和报错原样贴出来，并明确回答：微信有没有收到」。

> **状态：已闭环。** 首轮留下的三个待查问题（适配器是否在线 / 到底发出去没有 / 该怎么诊断）
> 均已实测作答，见下方「坑四」「坑五」「§交付口径」。**先读坑一（解释器）**——它才是首选修复。

## 为什么这条流水线存在

`computer_use(action="capture")` 返回的 PNG **只进模型上下文**（Hermes 把 base64 拼进 tool_result 的图片块），
**不落盘**；而 MemOmics 的「新图片自动推微信」只认**磁盘上的图片文件**。`scripts/desktop_shot.py` 补的就是中间那一环：
用**同一个 cua-driver 后端**截图并写文件 → 产物既能进 WebUI 当产物看，也能被微信推送链路捡走。

- 用法：`--send-wechat`（存好立刻推）/ `--out` / `--app` / `--json`
- 退出码约定：`0` 成功 / `2` 驱动缺失 / `3` 截图失败 / `4` 微信发送失败
- 脚本尾部 `sys.exit(main())` —— **必须以脚本自身退出码为准**（见坑三）

## 坑一（首选修复）：解释器选错 → 截图阶段就死（exit 3，零产物）

```
python scripts/desktop_shot.py --send-wechat --caption "MemOmics 桌面截图"
→ 截图失败：FeatureUnavailable("Feature 'tool.computer_use' unavailable:
   install reported success but packages still not importable (may require Python restart).
   To enable manually: uv pip install 'mcp==1.26.0' 'starlette==1.0.1'")
→ exit 3，磁盘零产物（stdout 只有一行 sitecustomize banner）
```

**机制（两段式，缺一不可）**：

1. `hermes-agent/tools/lazy_deps.py:237` 把依赖写成**精确钉版**：
   ```python
   "tool.computer_use": ("mcp==1.26.0", "starlette==1.0.1"),   # CVE-2026-48710
   ```
   本机系统 Python312 实测 `mcp 1.28.0` / `starlette 0.52.1` ⇒ `feature_missing()` 判 missing。
2. 于是触发**懒安装**，而 `_venv_pip_install()` 装进的是 **`.venv`**；可脚本跑在**另一个解释器**上：
   ```
   install 成功 → feature_missing() 复查仍为真 → lazy_deps.py:832 抛
   "install reported success but packages still not importable"
   ```
   ⇒「装到 A、跑在 B」在回执上与「真没装」**完全同形**（与 `references/package-availability-and-torch-stack.md`
   的三源错配同一根因家族）。

- **不是工具的错**：同一台机器上 agent 侧的 `computer_use` 一直可用（Hermes 服务进程的解释器依赖齐）。
  坏的只是这条脚本路径挑的解释器。**别把它写成「computer_use 不可用」。**
- 也不是 ABI 问题：实测 `from mcp.server.fastmcp import FastMCP` 在两个解释器里都 OK。

修复（实测一次成功）：

```
.venv/Scripts/python.exe scripts/desktop_shot.py --send-wechat --caption "MemOmics 桌面截图"
→ 已保存: results/desktop_shots/desktop_20260925_195450.png (1568x882, 439114 字节)
```

`.venv` 里 `starlette` = **1.0.1**（另注：`mcp` 无 `__version__`，打印为 `?`，别据此判缺失）。

**通用判据**：报 `packages still not importable` ⇒ 先 `which python` + 逐包打印版本，
再换 `.venv` 解释器重跑。⛔ **不要**往系统 Python 硬凑装引脚版本（铁律 29：装包需用户同意），
也**不要**去改 `lazy_deps.py` 的钉版（那要跑 `webui/tests/`，属平台代码改动，须用户点头）。

同族「解释器/库错配」还有：python-docx 只在共享库 `D:/Python/site-packages`；
R 侧 CellChat 只在 R-4.4.2 用户库、内核走 4.5.3（见 `references/r-interpreter-and-library-selection.md`）。

## 坑二：`/api/weixin/send_image` 的两条分支 —— 「限流」是兜底文案，不是诊断结论

```
微信: 发送失败 - 发送失败或被限流（5 秒间隔 / 60 秒去重）      [exit=4]
```

服务端 `webui/server.py` 的相关分支：

```
13097:  if _weixin_adapter is None:
13098:      return {"ok": False, "error": "微信未连接"}        # ← 另一条分支
13103:  print(f"[MemOmics] 微信发图: {path} ({size} 字节)", flush=True)   # 每次发送前必打印
13104:  ok = await _send_weixin_image(path, caption)
13105:  if not ok:
13106:      return {"ok": False, "error": "发送失败或被限流（5 秒间隔 / 60 秒去重）", "path": path}
```

推断链：**没**返回「微信未连接」⇒ `_weixin_adapter` 非 None ⇒ 失败发生在 `_send_weixin_image()` 内部。
⚠️ 13106 那句把「限流」与「真失败」**合并成同一句文案**（`_send_weixin_image` 返回 False 的**全部**情况
都落到这里），所以**不能**据它判定「被限流」——必须去读 gate/发送实现（见坑四）。

## 坑三：shell 聚合退出码会把失败读成成功

命令写成 `... ; echo "=== EXIT_CODE=$? ==="` 时，回执 `exit_code` 是 **echo 的 0**，而非脚本的 3。
判成败要读**脚本自己打印的结果行**（`截图失败：…` / `微信: 发送失败 - …`），或写成 `; ec=$?; echo "EXIT=$ec"`。
与管道 `| tee` 吞退出码同一家族（见 SKILL.md「后台进程回执 `completed normally (exit code 0)`」行）。

## 坑四：gate 的**预占时间槽**会静默丢弃一次性发图 → **换路径重试即成功**

`_gate_weixin_send()`（`server.py:12271`）的语义：

```python
def _gate_weixin_send(text="", min_interval=2.0, dedup_window=5.0, reserve=True):
    if now < g["cooldown_until"]:            return False   # 熔断期
    if now - g["last_ok_ts"] < min_interval: return False   # 间隔不足
    if text and text == g["last_text"] and now - g["last_ok_ts"] < dedup_window: return False
    if reserve:
        g["last_ok_ts"] = now    # ← 预占时间槽（还没真发就先占用）
    return True
```

- `_send_weixin_image()` 用 `min_interval=5.0, dedup_window=60.0` 调它；
- 而 server 自身的 **agent 工具进度推送**也在高频调同一把 gate（`min_interval=2.0`）——
  所以一次性发图请求**可能撞上别人的预占槽而被直接丢弃**（`_WEIXIN_SEND_GATE["dropped"] += 1`，
  **不打任何日志**，在回执上与「真发送失败」长得一样）。
- **去重 key 就是图片路径本身**（`text == last_text`）⇒ 复用同一路径重试会命中 60s dedup。

**处置（2026-09-25 实测）**：**换一个全新路径重试**，第 1 次尝试即 `ok:true`。
有界重试配方 = 最多 3 次、间隔 8s、**每次新路径**（已封装进 `scripts/desktop_shot_fallback.py`）。

> 🔴 **教训**：首轮（memomics-40625339）把它当成「等更久再重试」并已判「基本可排除限流」——
> 那个结论**下早了**。真正的判据是「**换路径重试 + 查适配器状态**」，
> 而不是「等满 70 s 用同一路径再试」。**回执文案给不出定性，源码 + 重试实验才行。**

## 坑五：适配器状态探针 —— 一把把「适配器问题」与「发送问题」分开的尺子

```
GET http://127.0.0.1:8899/api/weixin/status
→ HTTP 200 {"connected": true, "account_id": "c5d31956f3ad@im.wechat", "qr_login_in_progress": false,
            "last_error": "", "agent_enabled": true, "adapter_alive": true, "msg_count": 8}
```

- 字段：`connected` / `adapter_alive` / `last_error` / `msg_count` —— **适配器健康 = connected && adapter_alive**。
- 实测本轮：适配器**一直是好的** ⇒ 发送失败**不是**适配器掉线，而是 gate 竞态（坑四）。
- 有效端点只有 `/api/weixin/status`；`/api/weixin/state`、`/api/weixin/info`、`/api/weixin/config` 均 **404**（别瞎猜）。

## 降级通路：绕开 cua-driver 直接抓屏 + 推微信

当官方脚本这条路不可用（或只需快速把图送到微信），用
**`scripts/desktop_shot_fallback.py`**（本 skill 自带，实测 `ok:true`）：

```bash
python <skill>/scripts/desktop_shot_fallback.py --status              # 先查适配器
python <skill>/scripts/desktop_shot_fallback.py --caption "MemOmics 桌面截图"
```

- 抓屏用 **`PIL.ImageGrab.grab(all_screens=True)`**（多显示器全覆盖；不碰 cua-driver，**绕过 lazy_deps 门禁**）；
- 落盘到 `results/desktop_shots/`（可用 `--out` / `MEMOMICS_DESKTOP_SHOT_DIR` 覆盖）；
- 再 `POST {"path": ..., "caption": ...}` 到 `/api/weixin/send_image`；
- 实测发出去的是 **3840×2160 全屏（5,296,969 字节）**，回执 `{"ok": true, ...}`。

⚠️ 两条纪律：① **`computer_use` 的 `capture` 与这条通路互不替代** —— 前者给模型看（不落盘）、
后者给磁盘与微信（不出图给模型）；需要「我看一眼 + 同时发微信」就两个都做。
② **发桌面全屏 = 把屏幕上的一切都发出去了**（含聊天窗口、密码框等）——用户明确授权才发；
拿不准就先 `--no-wechat` 落盘给用户自己看。

## 交付口径（用户问「微信到底收到没有」时怎么答）

必须**分开陈述两条通路的结果**，不要合并成一句：

| 通路 | 结果 |
|---|---|
| 用户指定的 `desktop_shot.py` | ❌ 没收到 —— exit 3，**死在截图那一步，根本没走到发送** |
| 降级通路（fallback） | ✅ 收到了 —— `HTTP 200 {"ok": true, ...}` |

诚实交付四件套：
1. **原样贴 stdout / stderr**（本例 stdout 只有一行 sitecustomize banner、stderr 是 `截图失败：FeatureUnavailable(...)`）；
2. **明确回答「微信有没有收到」**，按通路分开；
3. **给两层根因**（解释器错配 → 截图未出；gate 竞态 → 首次发送被丢）；
4. **给修复选项**（跑对解释器 / 改钉版需用户点头），不擅自改平台代码。
⛔ **不编造 `ok:true`、不编造命令输出、不把「限流」当既成结论。**

## 附带：诊断这条链路时的轮次纪律

本轮为定位它连做了 源码 grep → 版本探针 → 环境探针 → 状态探针，
**两次收到系统循环检测 OOB「判定为循环失控」**（把连续同形态的只读排查判成重复）。
处置：**根因一闭合就用一次决定性动作收束**（换路径重试 → 拿到 `ok:true` → 汇报），
不要继续追加「再确认一下」的验证轮次；收到 OOB 时按它说的做——**产物/结论已到手就立即给结论 + 路径**。