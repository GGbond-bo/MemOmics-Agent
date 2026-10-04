---
name: cli-anything
description: "通过 CLI-Anything（HKUDS）把桌面/后端软件变成 agent-native CLI 来操控：用 cli-hub 装现成 CLI（gimp/inkscape/blender/freecad/qgis/zotero/obsidian/blender…71 个），或按官方 7 阶段规范自建 harness（含 Illustrator COM/ExtendScript 实战范例）。触发：操控软件 / 批量控制桌面软件 / 软件自动化 / agent-native CLI / cli-hub / CLI-Anything / 给某软件做个 CLI / 批量改 Illustrator 文件。"
version: 1.0.0
trigger_level: RED
trigger_keywords: [CLI-Anything, cli-hub, 操控软件, 操控, 软件自动化, 批量控制桌面软件, agent-native CLI, harness, 做个CLI, 做个命令行, 包装成CLI, 批量改, 统一字号, inkscape, 矢量图批量, 批处理软件, Illustrator自动化]
author: MemOmics (auto-created)
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [CLI-Anything, cli-hub, agent-native, harness, 软件控制, 软件自动化, 桌面软件, ExtendScript, Illustrator, 批量操作]
    difficulty: intermediate
    language: Python
    category: General Utility
prerequisites:
  python_packages: [click, cli-anything-hub]
  external: [git, cscript.exe (Windows, for COM bridges)]
related_skills: [computer-use, diagram-design, scientific-figure-export]
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化平台。使用前必须先通过 skill_view 加载本文件。以下规则覆盖所有默认行为。

### 规则1: 写代码/下命令前 → 必须先查 --help，禁止凭记忆编命令
- CLI-Anything 的命令树是**每个 harness 自己定义的**，仓库里 71 个 harness 各不相同。
- 任何调用前先 `cli-anything-<软件> --help` 和 `<子命令> --help`，**实测确认参数形态再写命令**（2026-10-04 实测：mermaid harness 的 `project new` / `diagram set` **只接受选项不接受位置参数**，凭直觉写 `diagram set "flowchart TD..."` 直接报 `Got unexpected extra argument`）。
- 官方文档（HARNESS.md / 各 harness 的 SKILL.md）是唯一权威，不许照抄记忆里的命令。

### 规则2: 8步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. skill_view 加载本 SKILL.md（获取命令模板+坑表）
3. check_env 检查环境（缺包按铁律 29 询问用户后装到项目内）
4. rail_review(pre) 前置审查（软件是否在跑？CLI 装了吗？输出路径合法吗？）
5. 写这一步的命令（先 --help 核实参数）
6. terminal 执行（分步执行，禁止 && 连接多步骤）
7. debate_analysis 多方辩论（涉及关键参数/批量改写用户文件时）
8. rail_review(post) 后置审查（产物真实存在吗？大小合理吗？用户文件有没有被改坏？）
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完整个流程用 && 连接执行
- ✅ **必须**分步：查 help → 试跑 → 核对输出 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值/批量改写参数（分辨率、字号、导出格式、批量范围）→ **至少尝试 2 个值**
- 参数变更后调 `debate_analysis` 辩论"这个参数合理吗？会不会改坏用户文件？"
- 不确定的参数就辩论，不要自己拍脑袋；最多 3 轮

### 规则5: 执行后审查（强化版）
- 每步执行完调 `rail_review(post)`，审查内容**全部强制**：
  - **产物检查**：文件生成了吗？大小 > 0？是有效格式吗（SVG/PNG/PDF 头正确）？
  - **用户资产保护**：有没有动到用户已打开的文档？**默认必须不保存**（`SaveOptions.DONOTSAVECHANGES`）
  - **退出码**：非 0 / traceback → 必须记录 `skill_evolution(action="record_error")`
  - **JSON 可解析**：`--json` 输出必须能被 `json.loads` 解析（agent-native 的底线）
- 通过 → `skill_evolution(action="record_run")`；失败 → 记录错误 + 修复后重跑

### 规则6: 结果存储结构
```
results/<sid>/software_control/
  ├── cli_tests/      # Hub 装来的现成 CLI 的试跑产物
  ├── <软件>/agent-harness/   # 自建 harness 源码
  └── logs/           # 命令与返回
```

### 规则7: 脚本出错/成功 → 必须调 skill_evolution（自进化）
| 时机 | action | 调 | 不调 |
|------|--------|----|------|
| harness 报错+你找到根因并修复 | record_error | ✅ 如 `CMYK Red` 色板不存在（Error 1302） | ❌ 打字错误/路径不存在 |
| 命令成功+产物通过审查 | record_run | ✅ 真实产物落盘 | ❌ 只 `--help` 看一眼 |

---

# CLI-Anything：把软件变成 agent-native CLI

**官方仓库**：https://github.com/HKUDS/CLI-Anything （Apache-2.0，HKUDS）
**CLI-Hub 网页**：https://hkuds.github.io/CLI-Anything/ （`https://clianything.cc/`）

核心命题：GUI/后端软件没有 LLM 可用的接口；CLI-Anything 给每个软件造一个**结构化、可组合、JSON 输出、自带 REPL 与 undo/redo** 的 CLI harness，让 agent 能确定性操控软件（而不是靠截图点坐标）。

## When to Use

### ✅ 应该使用（触发场景）
| 用户说什么 | 走哪条路 |
|-----------|---------|
| 「帮我操控 XX 软件」「XX 软件能不能自动化」「批量控制桌面软件」 | → 先 `cli-hub search <software>` 看有没有现成 harness |
| 「批量改一批 Illustrator/Inkscape/Blender/GIMP 文件」 | → 现成 harness（inkscape/gimp/blender）或自建（Illustrator） |
| 「给 XX 软件做个 CLI / 包装成命令行」 | → 官方 Phase 3 自建 harness（Load `hermes-skill` 方法论） |
| 「有现成 CLI 吗 / 装一下 cli-hub / CLI-Anything 是什么」 | → 本 skill 直接答 |
| 「批量导出/转换/渲染/改字体/改尺寸」跨多文件 | → harness 优先于 computer_use 模拟点击 |
| 需要**可复现、可重跑、确定性**的软件操作 | → harness（脚本化）而非 UI 驱动 |

### ⛔ 不应该使用（不要触发）
| 情况 | 该走什么 |
|------|---------|
| 只是**看/点一两下**界面、临时改一处 | → `computer-use` skill（后台 UI 驱动，无需写 harness） |
| 纯生信分析（RNA/ATAC/空间/bulk） | → 对应生信 skill，**与 CLI-Anything 无关** |
| 出**科学数据图**（UMAP/火山图/热图/箱线图） | → `cns-visualization` / `nature-figure` / `academic-figure-skill`；`diagram-design` 才管示意图 |
| 目标软件**没有脚本接口且不在 registry** | → 先评估成本；没有 COM/API/批处理模式的软件造 harness 是空壳，改用 `computer-use` |
| 目标软件需要**许可证/账号/付费**（Adobe 全家桶外的商业软件） | → 先问用户授权情况，不擅自动 |
| 只需要**一次性的单文件转换** | → 直接用该软件自带的命令行（如 `inkscape --export-filename`），不必装 harness |

### 🔴 铁律：自建 harness 前必须先问用户
自建 harness 是**高代价任务**（官方 7 阶段：Analyze→Design→Implement→Plan Tests→Write Tests→Document→Publish）。
触发前必须 `ask_user` 确认：**目标软件**？**要哪些命令**？**输出到哪里**？**会不会动到我已有的文件**？

## Pipeline

### 路径 A：用现成 CLI（快，5 分钟）

```
Tool: terminal
1. 装包管理器（一次性）
   .venv/Scripts/python.exe -m pip install cli-anything-hub
2. 检索
   cli-hub search <software>        # 无则走路径 B
   cli-hub info <name>              # 看 Requires / Entry point / Source
   cli-hub list                     # 按类别浏览（3D/AI/AUDIO/AUTOMATION/diagrams/image/...）
3. 安装
   cli-hub install <name>           # → 注册 cli-anything-<name> 到 PATH
4. 先读 help（规则1 硬门禁）
   cli-anything-<name> --help
   cli-anything-<name> <子命令> --help
5. 真跑 + JSON
   cli-anything-<name> --json <子命令> ...
6. 验证产物真实落盘（ls + 文件头）
```

**⚠️ 实测两条硬约定（2026-10-04 验证）**
1. **`--json` 是 group 级选项，必须写在子命令之前**：
   `cli-anything-mermaid --json session status` ✅ ／ `cli-anything-mermaid session status --json` ❌ `No such option '--json'`
2. **session 状态不跨进程**：每个子命令是独立进程，`project new -o flow.json` 写盘了但下一次调用读到 `"project_open": false`。
   → 后续每条命令都要 `--project <文件>` 重开；或进 `repl` 做有状态序列。**不要假设上一条命令的 session 还在。**

### 路径 B：自建 harness（官方 7 阶段）

方法论源文件：仓库 `cli-anything-plugin/HARNESS.md`（progressive disclosure，guides/ 按需读）+ `hermes-skill/SKILL.md`（Hermes 版绑定）。

```
Tool: terminal + write_file
1. Analyze   — 克隆/定位源码，找脚本接口（COM / CLI / API / batch mode）
2. Design    — 命名命令组、状态模型、输出格式（必须支持 --json）
3. Implement — Click CLI + REPL 默认 + 后端封装
4. Plan Tests— 写 TEST.md（unit + E2E）
5. Write Tests— test_core.py + test_full_e2e.py（优先 subprocess 调 cli-anything-<x>）
6. Document  — README + SKILL.md
7. Publish   — setup.py + pip install -e .
```

**目录结构（官方强制）**
```text
<software>/
└── agent-harness/
    ├── <SOFTWARE>.md
    ├── setup.py                     # find_namespace_packages(include=["cli_anything.*"])
    └── cli_anything/                # ⚠️ 命名空间包：顶层不许有 __init__.py
        └── <software>/
            ├── __init__.py
            ├── __main__.py
            ├── <software>_cli.py
            ├── core/
            ├── utils/<software>_backend.py
            └── tests/
```

**Backend 铁律（官方）**：**优先包装真实软件**（真可执行文件/脚本接口），不要重新实现；只有在没有原生后端时才用合成实现。

## Parameters

| 参数 | 说明 | 实测取值 |
|------|------|---------|
| CLI-Hub 版本 | pip 包 | v0.4.1（2026-10-04 装） |
| 安装位置 | 项目 venv（铁律 29：禁止 --user / 系统 Python） | `E:/MemOmics-Agent/.venv` |
| harness 命名空间 | `cli_anything.<software>` | 顶层 `cli_anything/` 无 `__init__.py` |
| 入口点 | `console_scripts` | `cli-anything-<software>` |
| registry 规模 | 仓库内 canonical SKILL.md | 71 个（`skills/` 目录） |
| 仓库顶层软件目录 | 含源码的 harness | 83 个 |

### 已验证 harness 清单（本机实测）
| 软件 | 来源 | 状态 | 备注 |
|------|------|------|------|
| mermaid | `cli-hub install mermaid` | ✅ 实跑通 | 出 SVG 15,154 B；Requires: nothing |
| Illustrator | **本机自建**（registry 无） | ✅ 实跑通 | COM→ExtendScript；见下方实战范例 |
| inkscape | registry 有 | 未测 | 需本机装 Inkscape |
| gimp / blender / freecad / qgis / zotero / obsidian / krita / kdenlive / drawio / libreoffice / comfyui / ollama | registry 有 | 未测 | 多数需装上游软件本体 |

## 🔬 实战范例：自建 Illustrator harness（本机已验证）

`H:/MemOmics-Agent/results/<sid>/software_control/illustrator/agent-harness/`

**后端选择**：Windows 上 Illustrator 无官方 CLI，但有 **COM 自动化 + ExtendScript**。
调用链：`cscript.exe` → VBScript `CreateObject("Illustrator.Application")` → `app.DoJavaScriptFile(path)` → 返回 JSON 字符串。

**关键实现点（踩过的坑）**
1. **ExtendScript 是 ES3，没有 `JSON` 对象** → 必须在 JSX 里手写 `esc()` 转义函数拼 JSON。
2. **不要用 `swatches.getByName("CMYK Red")`**：RGB 色彩空间的文档里没有 CMYK 色板 → `Error 1302: No such element`。
   → 直接构造 `new RGBColor()` 设 r/g/b（**实测 bug，已修**）。
3. **默认绝不保存用户文档**：探测/演示一律新建独立文档 + `close(SaveOptions.DONOTSAVECHANGES)`。
4. `cscript` 用 `shutil.which` + `System32` fallback 动态探测（不硬编码盘符）。

**已验证命令与真实返回**
```bash
AI=E:/MemOmics-Agent/.venv/Scripts/cli-anything-illustrator.exe
$AI --json doctor      # {"bridge":true,"cscript":"C:\\WINDOWS\\system32\\cscript.EXE","illustrator":{"doc_count":0,"active_doc":null}}
$AI --json info        # {"doc_count":0,"active_doc":null}   ← 无文档时的诚实返回，不报错
$AI artboards          # active_doc: None  artboards: 0
$AI --json probe --text "MemOmics Illustrator CLI" --size 14
# {"pathitems":1,"textframes":1,"text":"MemOmics Illustrator CLI","size":14,
#  "png":"C:\\...\\Temp/memomics_cli_probe.png","png_exists":true,"png_bytes":2395}
```

## Proven Scripts

> 经实际运行验证成功的脚本记录。`skill_evolution(action="record_run")` 自动追加至此表。
>
> 🆕 评分规则：`auto` 来自 rail_review 技术审查，`user` 来自用户认可。`query_logs` 按 approved → recency → score 排序推荐。

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|:----|:----|:----|:----:|:-----|:----:|:----:|:-:|
| - | - | software_control | 2026-10-04 | cli-anything-mermaid (session 跨进程丢失) | 8 | - |  |
| - | - | software_control | 2026-10-04 | cli-anything-illustrator probe (CMYK Red 修复后) | 9 | - |  |

| - | - | - | 2026-10-04 | cli-anything-illustrator (self-built harness) | - | - |  |
| - | - | - | 2026-10-04 | cli-anything-mermaid | - | - |  |
| - | - | - | 2026-10-04 | cli-anything-illustrator gradient-probe | - | - |  |
## Common Issues

| 报错 | 根因 | 解决 |
|------|------|------|
| `No such option '--json'` | `--json` 是 group 级选项 | 移到子命令**之前**：`cli-anything-x --json <cmd>` |
| `Got unexpected extra argument (xxx)` | 该子命令只收选项不收位置参数 | 先 `<子命令> --help` 核实（如 `diagram set --text "..."`） |
| `{"project_open": false}` / `No project is open` | **session 不跨进程** | 每条命令带 `--project <file>`，或进 REPL |
| `export share` 抛 Traceback | harness 自身缺陷：无项目时未优雅报错 | 先开项目再 export；此为上游 bug（mermaid harness） |
| `Error 1302: No such element`（Illustrator） | RGB 文档里取 CMYK 色板 | 改 `new RGBColor()` 直接构造颜色 |
| `Internal error`（中文 locale 下显示为乱码）赋值 `fillColor = doc.gradients[0]` | ExtendScript **不能**把 Gradient 对象直接当颜色 | 用 `new GradientColor()`：`var gc=new GradientColor(); gc.gradient=doc.gradients[i]; gc.origin=[x,y]; gc.angle=45; rect.fillColor=gc;`（本机实测 applied=true, error=null） |
| 新建 RGB 文档 `swatches` 里找不到渐变色板（`typename` 只有 `"Swatch"`，渐变 count=0） | 新建文档的渐变**未注册进 `swatches`**，但 `doc.gradients` 有 5 个 | 走 `doc.gradients[i]`，**不要** `swatches.getByName(<渐变名>)`——那是必然失败的路径 |
| `COM_FAIL: ...` / `JS_FAIL: ...` | COM 桥不通 / JSX 语法错 | `doctor` 探活；检查 JSX 是否 ES3 兼容 |
| `cli-hub: command not found` | 没装到项目 venv | `.venv/Scripts/python.exe -m pip install cli-anything-hub` |
| registry 里搜不到目标软件 | 该软件无 harness | 走路径 B 自建，或改用 `computer-use` |
| **新建/注册技能后，真实 matcher 命中为空**（`_match_red_skill_triggers` 返回 `[]`） | 🔴 索引的触发词**优先取 `skill.json.trigger_keywords`**（`skills_registry.extract_keywords` 里 json 在 md 之前），而 `--build` 的回填会用**名称派生值**（`cli-anything, cli anything, cli`）覆盖手写值 → 手写关键词被静默清掉 | 把真关键词写进 **`skill.json.trigger_keywords`** + `trigger_level: "RED"`（frontmatter 里写**没用**，会被 json 盖过），再 `python -m webui.skills_registry --build`；用 `grep "\| <skill> \|" hermes_home/SKILLS_INDEX.md` 确认索引行显示自己的关键词 + `RED 必触发` |
| 新技能建在 `autonomous-ai-agents/` 等目录后 WebUI 看不到 | `server.list_skills()` 只扫 `skills/` + `hermes_home/skills/{bioinformatics,plotting}` | 技能放到**被扫描的根目录**（如 `hermes_home/skills/bioinformatics/`）；分类靠 frontmatter `category`，不靠目录名 |
| `rmdir` / `rm -rf` 被执行层拦下（"操作需确认"） | 平台安全层识别删除关键词 | 只移动用 `mv`（不删）；确实要删先向用户列出文件再确认 |
| 装完 harness 但 `cli-anything-<x>` 找不到 | 控制台脚本未进 PATH | 用 `.venv/Scripts/cli-anything-<x>.exe` 全路径 |

## References

**官方文档（Step 1 硬门禁留痕，2026-10-04 抓取）**
- 仓库主页 / README：https://github.com/HKUDS/CLI-Anything （1818 行，含 Quick Start / CLI-Hub / 7 阶段 / 各平台接入）
- Hermes 集成 skill：`hermes-skill/SKILL.md`（name=`cli-anything-hermes`）+ `hermes-skill/scripts/install.sh` + `hermes-skill/agents/hermes.yaml`
- 构建方法论：`cli-anything-plugin/HARNESS.md`、`QUICKSTART.md`、`guides/`、`skill_generator.py`
- CLI-Hub 包：`pip install cli-anything-hub`（v0.4.1）／网页 https://hkuds.github.io/CLI-Anything/
- canonical 技能集：仓库 `skills/` 目录 71 个 `cli-anything-*` SKILL.md
- Tech Report：arXiv:2606.03854
- 本机克隆：`E:/MemOmics-Agent/results/<sid>/data/cli_anything_repo`

**本机已装**
- `hermes_home/skills/cli-anything-hermes/`（官方 Hermes skill，`install.sh` 装）
- `.venv/Scripts/cli-anything-mermaid.exe`（Hub 装）
- `results/<sid>/software_control/illustrator/agent-harness/`（自建，`pip install -e .` 装）

---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(topic="{软件操控任务}", context="命令+返回+产物", knowledge_base_info=<KB>)
3. save_conclusions(module="software_control", topic="{任务名}", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```