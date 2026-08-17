---
name: computer-use
description: "控制电脑: 截屏+鼠标点击/拖拽+键盘输入+窗口管理+OCR文字识别。让LLM能操作任何桌面软件。"
when_to_use: "[computer-use] 控制电脑: 截屏+鼠标点击/拖拽+键盘输入+窗口管理+OCR文字识别。让LLM能操作任何桌面软件。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [computer-use, desktop, automation, screenshot, mouse, keyboard, window-management, ocr, 电脑控制]
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

控制电脑: 截屏 + 鼠标点击/拖拽 + 键盘输入 + 窗口管理 + OCR 文字识别。

适用场景: 操作任何桌面软件、自动化 GUI 任务、填写表单、截图分析、窗口管理

## When to Use

当你需要 **操作用户的电脑** 时使用此 skill。典型场景:
- "帮我打开记事本写一段话"
- "截个屏看看我现在屏幕上是什么"
- "帮我点击屏幕上的某个按钮"
- "帮我在这个软件里输入文字"
- "列出当前打开的所有窗口"
- "把XX窗口最大化"

## 核心工作流 (截屏-分析-操作-验证 循环)

```
1. screen_capture()     → 截取当前屏幕, LLM 分析截图
2. screen_ocr()         → (可选) OCR 识别屏幕文字, 获取元素坐标
3. mouse_click() / keyboard_type() / keyboard_hotkey()  → 执行操作
4. screen_capture()     → 再次截屏, 验证操作是否成功
5. 如未达到目标, 回到 step 2
```

## 可用工具

### 截屏 & 视觉
| 工具 | 说明 |
|------|------|
| `screen_capture` | 截取全屏/区域/窗口, 返回 base64 图片 |
| `screen_ocr` | 截屏 + OCR 识别文字, 返回文字+坐标 |

### 鼠标
| 工具 | 说明 |
|------|------|
| `mouse_click` | 点击坐标/图像匹配, 支持双击/右键 |
| `mouse_drag` | 拖拽 |
| `mouse_scroll` | 滚轮 |
| `mouse_move` | 移动鼠标 (不点击) |

### 键盘
| 工具 | 说明 |
|------|------|
| `keyboard_type` | 输入文字 (支持中文) |
| `keyboard_hotkey` | 组合键 (如 "ctrl,c") |
| `keyboard_press` | 单键 (enter/esc/tab/...) |

### 窗口管理
| 工具 | 说明 |
|------|------|
| `window_list` | 列出所有窗口 |
| `window_focus` | 激活/最小化/最大化/关闭窗口 |
| `window_move` | 移动/调整窗口大小 |

### 辅助
| 工具 | 说明 |
|------|------|
| `clipboard_get` | 读取剪贴板 |
| `clipboard_set` | 写入剪贴板 |
| `wait` | 等待 N 秒 |

## 安全机制

- **FAILSAFE=True**: 鼠标快速移到屏幕左上角 (0,0) 立即中止所有操作
- **坐标范围检查**: 点击坐标超出屏幕会拒绝
- **危险操作确认**: 关闭窗口/删除等操作需要用户确认
- **中文输入安全**: 通过剪贴板粘贴, 避免输入法干扰

## 常用操作示例

### 打开记事本并输入文字
```
1. keyboard_hotkey("win,r")           → 打开运行
2. keyboard_type("notepad")           → 输入 notepad
3. keyboard_press("enter")            → 回车
4. wait(1)                            → 等待记事本启动
5. keyboard_type("Hello World")       → 输入文字
```

### 截屏并识别屏幕文字
```
1. screen_capture()                   → 截全屏
2. screen_ocr()                       → OCR 识别文字+坐标
3. 根据 OCR 结果中的文字坐标, mouse_click(x, y)
```

### 切换窗口
```
1. window_list()                      → 列出所有窗口
2. window_focus("浏览器", "activate")  → 激活浏览器窗口
3. screen_capture()                   → 截屏确认
```

## 坐标系统

- 原点 (0,0) 在屏幕**左上角**
- X 轴向右增大, Y 轴向下增大
- `screen_capture()` 返回的 `width/height` 是屏幕分辨率
- `screen_ocr()` 返回的 `words[].x/y` 是文字在截图中的坐标

## References

- Source: MemOmics built-in
- Category: system
- Language: Python
- Dependencies: pyautogui, mss, pygetwindow, pytesseract, PIL, cv2


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
- 参数选择有多个合理选项时（如分辨率 0.4 vs 0.6 vs 0.8）
- 结果可能受方法选择影响时（如不同注释方法给出不同结果）
- 生物结论需要验证可靠性时
- QC 阈值不确定时（如 MT% 阈值 10% vs 15% vs 20%）

### 不触发场景
- 参数有明确知识库推荐且无争议时
- 纯计算步骤（如保存文件、读取数据）
