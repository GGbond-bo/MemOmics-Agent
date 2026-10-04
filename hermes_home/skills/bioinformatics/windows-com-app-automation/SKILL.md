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