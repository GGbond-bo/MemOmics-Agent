---
name: computer-use
description: "控制电脑: 截屏 + 鼠标点击/拖拽 + 键盘输入 + 窗口管理（走 Hermes computer_use 工具, cua-driver 驱动）"
when_to_use: "[computer-use] 用户要截屏、看屏幕、点按钮、在桌面软件里输入、切窗口时触发 —— 唯一入口是 computer_use 工具"
version: 2.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [computer-use, desktop, automation, screenshot, mouse, keyboard, window-management, 电脑控制, 截屏]
    difficulty: basic
    language: Python
    category: General Utility
prerequisites:
  r_packages: []
  python_packages: []
### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

---

# 电脑控制 (Computer Use)

**唯一入口是 Hermes 的 `computer_use` 工具** —— 不是 shell 命令、不是 pyautogui 脚本、不是本技能目录里的脚本（`scripts/` 为空）。
旧版本文档里出现的 `screen_capture` / `screen_ocr` / `mouse_click` / `keyboard_type` / `window_list` 等**都不是真实工具**（2026-09-25 全仓扫描确认：这些名字在任何代码里都不存在），照抄会浪费一整轮。

## 一句话用法

`computer_use(action="capture", app="screen")` → 拿到整屏 PNG + 带编号的可交互元素 → `computer_use(action="click", element=7)` → 再 capture 验证。

## 依赖：cua-driver（外部二进制，不是 pip 包）

| 操作 | 命令 |
|------|------|
| 看状态 | `hermes computer-use status` |
| 体检 | `hermes computer-use doctor` |
| 安装/升级 | `hermes computer-use install`（macOS / Windows / Linux 同一命令） |
| 自定义路径 | 环境变量 `HERMES_CUA_DRIVER_CMD` 指向二进制绝对路径 |

- MemOmics 启动时由 `webui/cua_bootstrap.py` 自动定位（PATH 未刷新也能找到官方安装目录），日志里会出现 `[computer_use] cua-driver -> <路径>`。
- 找不到二进制时**不报错**：工具会整个从模型工具表里消失 —— 现象是"MemOmics 不能操控电脑"，实际只是没装驱动。
- 2026-09-25 本机实测：cua-driver 0.28.3（Windows 10.0.26200 / x86_64），`doctor` 全绿。

## 平台矩阵（同一套 action，三平台不同后端）

| 平台 | UI 读取 | 输入投递 | 额外权限 |
|------|---------|----------|----------|
| Windows | UIAutomation（`cua-driver-uia.exe`） | SendInput / PostMessage（不抢焦点） | 无（安装时零前置条件） |
| macOS | Accessibility（AX）+ 私有 SkyLight SPI | `SLPSPostEventRecordTo` | 辅助功能 + 屏幕录制（TCC 授权） |
| Linux | AT-SPI（X11 与 Wayland） | XTest / virtual-keyboard | 需要 `DISPLAY` 或 `XDG_SESSION_TYPE=wayland`；alpha 质量 |

## 动作表（真实 action 枚举，共 14 个）

| action | 关键参数 | 说明 |
|--------|----------|------|
| `capture` | `mode`(som/vision/ax), `app`, `pid`, `window_id`, `max_elements` | 截屏 + 元素树；**无副作用** |
| `click` / `double_click` / `right_click` / `middle_click` | `element` 或 `coordinate`, `button`, `modifiers`, `delivery_mode` | 点击 |
| `drag` | `from_element`/`to_element` 或 `from_coordinate`/`to_coordinate` | 拖拽 |
| `scroll` | `direction`(up/down/left/right), `amount`(默认 3) | 滚轮 |
| `type` | `text` | 输入文字（按当前键盘布局） |
| `key` | `keys` 如 `ctrl+s` / `return` / `escape` | 组合键/单键 |
| `set_value` | `value`, `element` | 下拉框/滑块**直接设值**，不弹原生菜单、不抢焦点 |
| `wait` | `seconds`（≤30） | 等待渲染 |
| `list_apps` / `list_windows` | — | 枚举可见应用/窗口（含 pid、window_id） |
| `focus_app` | `app`, `raise_window`（默认 false） | 切目标；默认**不置顶**，不打断用户 |

## 关键行为（2026-09-25 真机实测，别凭直觉写）

- **不抢焦点是默认**：`delivery_mode` 默认 `background`，输入直接投递给目标窗口；`focus_app` 默认不 raise。
- **默认目标 = 最前台窗口**，可能抓到覆盖层（实测抓到过 `NVIDIA Overlay.exe`，整张图近乎全黑）。**要整屏必须显式 `app="screen"`**（等价哨兵：`desktop` / `fullscreen` / `all`），它会解析到桌面/任务栏这类真实窗口。
- `mode="som"` 返回"带编号覆盖的 PNG + elements"，视觉模型首选；纯文本模型用 `mode="ax"`（只给元素树，无图）。
- `max_elements` 默认 100、上限 1000：Electron/IDE 能发布 500+ 节点，被截断时结果里带 `total_elements` / `truncated_elements`，可用 `app=` 缩小范围或调高上限。
- 元素编号来自**最近一次** `capture(mode="som")`；窗口变了要重新 capture 再点。
- capture 返回的是 base64 PNG（实测整屏 1568x882 约 440KB）；要落盘就自己写文件，微信推送走服务端 `_send_weixin_image()`。

## 标准工作流（截屏 → 定位 → 操作 → 验证）

```
1. capture(mode="som", app="screen")        # 先看清楚：有哪些窗口、元素编号
2. 选 element=N（比像素坐标可靠得多）
3. click / type / set_value / key
4. 再 capture 一次验证；没达到目标就回到 2
```

## 示例

### 看屏幕上有什么（最常用）
```
computer_use(action="capture", app="screen", mode="som")
→ 报告：窗口列表 + 桌面图标 + 元素编号；不要逐字转录用户的私人内容
```

### 点一个按钮
```
computer_use(action="capture", app="Edge")          # 先拿编号
computer_use(action="click", element=12)            # 按编号点，不要猜坐标
computer_use(action="capture", app="Edge")          # 验证
```

### 在下拉框里选值（不弹菜单）
```
computer_use(action="set_value", element=5, value="Blue")
```

### 切窗口 / 输入
```
computer_use(action="list_windows")                 # 拿到 pid/window_id
computer_use(action="focus_app", app="notepad")     # 默认不置顶
computer_use(action="type", text="Hello")
```

## 安全与边界

- `capture` 无副作用；**其余 action 受审批门控**（Hermes 侧 approval / MemOmics 侧确认门）。
- 危险动作（关闭/删除/发送/支付/发布）必须先向用户说清"我要点哪里"，得到确认再执行。
- 不要主动操作聊天/邮件/银行类私人窗口；用户在场且明确要求时才动。
- 旧文档里的 `FAILSAFE=True`（鼠标甩到左上角中止）**是 pyautogui 的机制，cua-driver 没有**，不要承诺。

## 排错对照表

| 现象 | 真实原因 | 处理 |
|------|----------|------|
| `doctor` 说 not installed | 二进制不在 PATH，且未设 `HERMES_CUA_DRIVER_CMD` | `hermes computer-use install`，或重启 MemOmics（bootstrap 会重新定位） |
| 工具在模型工具表里根本不出现 | 同上 —— 可用性检查失败时工具被整体摘掉 | 先看服务日志里的 `[computer_use]` 行 |
| 截图近乎全黑 / elements=0 | 默认目标是最前台窗口，命中了覆盖层 | 显式 `app="screen"` 或指定 `app`/`pid`/`window_id` |
| UIA 枚举 >2000ms 退回 Win32 列表 | 桌面节点太多（驱动自己的降级策略） | 用 `app=` 缩小到具体窗口 |
| Linux 报无显示 | 无图形会话 / 未设 DISPLAY | 设 `DISPLAY` 或 `XDG_SESSION_TYPE=wayland` |

## References

- 上游文档: `hermes-agent/website/docs/user-guide/features/computer-use.md`
- 工具实现: `hermes-agent/tools/computer_use/{schema.py, tool.py, cua_backend.py, doctor.py}`
- MemOmics 定位引导: `webui/cua_bootstrap.py`
- 安装器（PS 5.1 需打补丁用 curl，见 2026-09-25 事故记录）

---

## 🗣️ 辩论机制（debate_analysis）

本 skill 在执行后，如果涉及**参数选择、方法决策、结果判断**等不确定环节，**必须**调用  工具进行多角色辩论。

### 辩论规则
- **正方 3 位专业编辑**（各自独立，互相看不到）：生物学编辑 / 统计学编辑 / 生信编辑
- **反方 4 位专业编辑**（各自独立，互相看不到，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
- **裁判**：看到所有 7 方论点后给出裁决 + 置信度（高/中/低）
- **上下文隔离**：每个编辑是独立的 LLM API 调用，messages 只包含自己的 prompt
- **分科知识库**：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
- **辩论结果自动归档**到 results/.../log/debate_*.json

### 触发场景
- 参数选择有多个合理选项时（如截图区域全屏 vs 指定窗口、元素编号 vs 像素坐标）
- 结果可能受方法选择影响时（如 UIA 元素树 vs OCR 定位）
- 生物结论需要验证可靠性时
- QC 阈值不确定时（如 MT% 阈值 10% vs 15% vs 20%）

### 不触发场景
- 参数有明确知识库推荐且无争议时
- 纯计算步骤（如保存文件、读取数据）
