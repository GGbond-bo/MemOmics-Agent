---
name: windows-com-app-automation
description: "用 Windows COM + 脚本引擎确定性地驱动桌面应用（Illustrator/Photoshop/InDesign/Word/Excel）：cscript→VBScript→CreateObject→DoJavaScriptFile/DoScript 桥，ExtendScript ES3 手拼 JSON、颜色与渐变两个实测坑、隔离文档写操作的安全模式、可复制的 doctor/探测脚手架。触发：Illustrator 自动化 / 操控 Illustrator / 批量改 Illustrator / 图内文字批量改 / COM 自动化 / ExtendScript / JSX 脚本 / Photoshop 自动化 / 脚本控制软件 / 无 CLI 软件怎么自动化。"
version: 1.0.0
trigger_level: RED
trigger_keywords: [Illustrator自动化, 操控Illustrator, 批量改Illustrator, Illustrator脚本, ExtendScript, JSX脚本, COM自动化, Photoshop自动化, InDesign自动化, 脚本控制软件, 软件没有CLI, 桌面软件自动化, 图内文字批量改, cscript, DoJavaScriptFile, 画板操作]
author: MemOmics (auto-created)
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [COM, ExtendScript, JSX, Illustrator, Photoshop, 桌面软件自动化, cscript, Windows]
    difficulty: intermediate
    language: Python
    category: General Utility
prerequisites:
  python_packages: [click]
  external: [cscript.exe, 目标应用需已安装且可被 COM 自动化]
related_skills: [cli-anything, computer-use, academic-figure-skill]
---

## ⛔ MemOmics 强制规则

1. 写代码前 `search_knowledge` + `skill_view`；2. 8 步循环；3. 写一步跑一步；
4. 关键参数多值 + `debate_analysis`；5. 执行后 `rail_review(post)`；
6. 结果落 `results/<sid>/`；7. 出错/成功走 `skill_evolution(record_error/record_run)`。

> ✅ **已落地到索引（2026-10-04 19:08，提交 `235ea5ed`）**：顶层 `skill.json` 已补齐（RED，16 触发词），
> 门禁 PASS（387 技能：RED 66 / YEL 308 / GRN 13；876 例通过），实测 matcher 命中本技能。
> 新建技能时的收工管道与失败签名 → `skill_view("skill-registration-and-routing")`。

---

# Windows COM 桌面应用自动化（脚本桥）

**为什么用这条路**：GUI 应用没有 CLI，但 Windows 上多数商业软件暴露 **COM 自动化接口** + **脚本引擎**。
桥的形状固定，一条通路打通全部：

```mermaid
flowchart LR
    A["Python (Click CLI)"] --> B["cscript.exe //nologo run.vbs"]
    B --> C["VBScript:<br/>CreateObject('&lt;ProgID&gt;')"]
    C --> D["&lt;App&gt;.DoJavaScriptFile(op.jsx)"]
    D --> E["JSX 执行 → 拼 JSON 字符串返回"]
    E --> F["stdout: RESULT|{...}"]
    F --> G["Python json.loads → 结构化结果"]
```

比截图点坐标可靠得多：**确定性、快、不抢焦点、可重跑**。（临时点一两下的场景用 `computer-use` 即可。）

## When to Use

### ✅ 该用
- 用户要**批量/可复现**地操作 Adobe 系（Illustrator / Photoshop / InDesign）或 Office 系（Word / Excel）
- 用户说「操控我的 Illustrator」「图内文字批量改字号/字体」「导出整套变体」「批量改画板」
- 目标软件**没有 CLI**，但装了完整版（COM 可用）
- 需要**不动用户正在编辑的文件**前提下证明"能操控"（隔离文档探测）

### ⛔ 不该用
- 目标软件**没有 COM 接口**（不少开源软件）→ 走命令行/`computer-use`
- 只点一两下、看个界面状态 → `computer-use`（后台 UI 驱动，无需写桥）
- 想用 HKUDS 生态装现成 harness → `skill_view("cli-anything")`（本 skill 是**自己写后端**那条路）
- Web / 跨平台服务 → HTTP API / 官方 CLI，别上 COM

## Pipeline

```
Tool: terminal + write_file
1. 探活（只读，永远第一步）：桥通不通 + cscript 路径 + 当前文档数
2. 只读 op：枚举文档 / 画板 / 对象计数 → 期望真实数字；无文档时优雅返回 {doc_count:0}
3. 隔离写 op：新建独立文档 → 建对象 → 写文字 → 导出 PNG → close(DONOTSAVECHANGES)
4. 校验产物：exists=true + bytes>0，并 ls 复核落盘
5. 把真实 JSON 返回原样写进文档（不要只写"成功"）
```

**ProgID / 脚本入口对照**（换应用只改这两处）

| 应用 | ProgID | 入口 |
|------|--------|------|
| Illustrator | `Illustrator.Application` | `DoJavaScriptFile(path)` |
| Photoshop | `Photoshop.Application` | `DoJavaScriptFile(path)` |
| InDesign | `InDesign.Application` | `DoScript(script, language)` |
| Word | `Word.Application` | `Run(macroName)` |
| Excel | `Excel.Application` | `Run(macroName)` |

> 📄 完整可复制脚手架（VBS 运行器 + ES3 手拼 JSON 前置 + Python 侧要点）→
> `templates/windows-com-jsx-bridge.md`
> 🔧 通用探针（查桥 + 文档数 + 画板数，改 ProgID 即用）→ `scripts/com_bridge_probe.py`
> 📋 已验证实例（Illustrator 全链路实测记录 + 143 行 harness）→ `references/illustrator-harness-verified.md`

## Parameters

| 项 | 值 / 说明 |
|----|----------|
| cscript | `shutil.which("cscript")` → 兜底 `C:\Windows\System32\cscript.exe`（**别硬编码盘符**） |
| JSX 路径传参 | 用**正斜杠**（`Path(...).as_posix()`）——VBScript 里反斜杠会当转义 |
| 解码 | `encoding="utf-8", errors="replace"`——报错文本可能是中文 locale，防解码炸 |
| 返回约定 | `RESULT|{json}` / `COM_FAIL|...` / `JS_FAIL|...` 前缀分流 |
| 语言版本 | ExtendScript = **ES3**：无 `JSON`、无 `Array.forEach`、无箭头函数 |
| 保存策略 | 写操作默认 `SaveOptions.DONOTSAVECHANGES`（**绝不保存用户文档**） |

## Common Issues

| 报错 | 根因 | 解决 |
|------|------|------|
| `Error 1302: No such element`（取色板名） | 文档是 **RGB 色彩空间**，里面没有 `CMYK Red` 这类 CMYK 色板 | 直接 `var c=new RGBColor(); c.red=240;c.green=90;c.blue=70; rect.fillColor=c;` ——**不要**用 `swatches.getByName("CMYK Red")` |
| `Internal error`（中文 locale 下显示为乱码） | 把 Gradient **对象**直接当颜色赋值 | `var gc=new GradientColor(); gc.gradient=doc.gradients[i]; gc.origin=[x,y]; gc.angle=45; rect.fillColor=gc;` |
| 新建文档里 `swatches` 找不到渐变色板（`typename` 只有 `"Swatch"`，渐变 count=0） | 渐变**未注册进 `swatches`**，但 `doc.gradients` 有 5 个 | 走 `doc.gradients[i]`，**不要** `swatches.getByName(<渐变名>)`（必然失败路径） |
| `COM_FAIL:` | ProgID 不对 / 应用没装 / COM 未注册 | 用①探活确认；确认应用完整版（非绿色版） |
| `JS_FAIL:` + 行号 | JSX 语法非 ES3（用了 `JSON.` / 箭头函数 / `let`） | 改 ES3：`var` + 手拼 JSON |
| JSX 返回值是空/`undefined` | ExtendScript 取**最后一条表达式**做返回值 | 结尾写 `out + '';` 显式产出字符串 |
| 无文档时命令抛异常 | 没做空文档分支 | 先判 `app.documents.length === 0` → 返回 `{"doc_count":0}` |
| 用 `vision_describe` 的**主色榜缺席**判定「图里没有某颜色」→ 误判缺色（2026-10-04 实测，第3轮差点误判"缺蓝"） | 主色榜按**面积**取 top-N，细笔画/小面积目标（<0.5%）被截断；且榜上色是**量化合并簇**，不等于文档精确色 | ✅ 改用**像素级复核** → `scripts/verify_png_colors.py`（精确 RGB 计数 + ΔRGB≤12 近邻 + 饱和度>40 彩色簇 + sha256）。实测蓝字仅占 0.435% 未进 top5，但精确 `#0044cc` = 283 px 确实存在，另含抗锯齿边色 `#7fa1e5/#bfd0f2/#4073d9`，蓝字 bbox 与 `--x/--y` 参数吻合 |
| 拿 `vision_describe` 报的色值当「文档精确色」 | 管道输出是量化/合并簇：报 `#00a040`，PNG 里精确色其实是 `#00aa55`（53044 px） | 要写"精确色 / 精确 px 数"的结论，一律从导出 PNG 取像素值，不用管道色值 |
| 把 `n=3` 多轮闭环写成"确定性已验证" | 单次多轮只是 **smoke 证据**，排除不了偶然/环境依赖 | 结论分级：**smoke**（单次多轮全绿）／**确认**（固定版本+字体+颜色配置，N=10 冒烟 + N=29 确认，PNG sha256 与像素指标稳定）。未做重复运行不得称确定性 |

## 🔁 多轮闭环验收（画 → 导出 → 看图 → 调整 → 再看图）

> **"命令返回 ok" ≠ "图上确实变了"。** 每轮必须闭合成三层证据链，缺一层就会被用户/辩论质疑。
> 完整实测留痕（逐轮命令 + 真实 JSON + 判定谓词 + 辩论裁决）→ `references/multi-round-loop-verification.md`
> 像素级复核脚本（可直接跑，退出码可作 pass/fail 门）→ `scripts/verify_png_colors.py`

| 层 | 证据 | 说明 |
|----|------|------|
| ① 命令层 | `--json` 关键字段 | `changed` / `ok` / `index` / `total` / `bounds` / `fill` / `textframes` / `error` |
| ② 产物层 | 导出路径 + 字节数 + sha256 + 目录清单 | 字节数变化必须能解释（如字号 40→60 → PNG 6845→9151 B） |
| ③ 像素层 | `vision_describe`（OCR 文本+置信+bbox）＋ **PIL 精确色复核** | 主色榜**只作辅助**，不能单独当"缺色"证据 |

**判定口径（建议先写成谓词再跑）**
- 颜色 = **存在性 + 核心色 + bbox 容差**，不是"进没进 top-N 榜"：
  `green: core=#00aa55 min_px>=10000` ／ `blue: core=#0044cc min_px>=200 bbox_tol=5`（**用 `min_px`，比 `min_pct` 稳**）
- 文字 = OCR 命中 + 置信 ≥ 阈值；允许长句被 OCR 拆成多段。
- 几何 = `bounds` 差值与 `--dx/--dy` **逐项对账**（坐标系见下）。

**坐标系（实测，容易栽）**
`rect --x/--y` = 距画板左/上；返回的 `bounds` 是**文档坐标（y 向上）**。
`move --dx 200 --dy 120`（`--help` 写 dy positive = DOWN）→ `[60,540,360,360]` → `[260,420,560,240]`，即 y 值**减小** 120。别按屏幕 y 向下误读 dx/dy 符号。
`artboard_rect` 形如 `[0,600,800,0]`。另：`saved` 字段在 new-doc 时会是 `true`（新建无改动），**判"有没有落文档"要看磁盘，不看这个字段**。

**收尾三件套（每轮闭环结束必做，并写进汇报）**
```
close-untitled  → docs_before / closed / docs_after（清掉 harness 建的「未标题-*」，不保存）
doctor          → bridge / doc_count / active_doc（确认 doc_count=0）
ls + sha256sum  → 磁盘只有该轮该有的产物，无 .ai/.pdf 落盘
```

**长闭环的执行节奏（避开平台门禁，实测）**
- 每条 `terminal`（**含 `--help`/`ls`/`sha256sum` 这类只读命令**）都会置 pending 标记 → 下一条 terminal 被铁律 24 拦；
  因此**每条 terminal 之后紧跟一次 `skill_evolution(record_run)`**，再进下一条。
- 多轮同构闭环会触发**循环检测误报**（"连续执行相同/相似命令"）。这不是让你停：把每轮的命令**参数不同**（rw 轮次不同自然不同）、
  把一轮的三层证据压进**一次** terminal/execute 调用、汇报时按轮分段——别为同一件事发多条同形调用。

## Proven Scripts

> 经实际运行验证成功的脚本记录。`skill_evolution(action="record_run")` 自动追加至此表。

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|:----|:----|:----|:----:|:-----|:----:|:----:|:-:|
| - | - | Windows COM | 2026-10-04 | com_bridge_probe.py | 8 | - |  |

## References

- Adobe ExtendScript Toolkit / 各产品 Scripting Guide（Adobe 官方 PDF；按产品名搜）
- 本 skill 支持文件：
  - `templates/windows-com-jsx-bridge.md` — COM→JSX 桥脚手架（ProgID 表 / ES3 JSON / 安全模式 / 验证清单）
  - `references/illustrator-harness-verified.md` — Illustrator 实测记录与完整 harness 结构
  - `scripts/com_bridge_probe.py` — 通用探针
- 相关：`cli-anything`（HKUDS 生态的现成 harness + 自建规范）、`computer-use`（UI 驱动，适合点一两下）

---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(topic="{自动化脚本设计}", context="命令+返回+产物")
3. skill_evolution(action="record_run")
4. 更新 task_plan.md
```