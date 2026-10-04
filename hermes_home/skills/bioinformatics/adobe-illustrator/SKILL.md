---
name: adobe-illustrator
description: Adobe Illustrator（AI）全链路操控手册 — 16 个 cli 命令、画→导出→看图→调整闭环、版本沉淀、自带脚本库
trigger_level: RED
trigger_keywords: ["Illustrator", "操控AI", "操作AI", "AI里", "AI文件", "AI脚本", "AI画板", "画板", "ExtendScript", "JSX脚本"]
category: system
---

# Adobe Illustrator 操控手册（全链路闭环 · 自包含）

> 一句话：用 `cli-anything-illustrator` harness（COM → ExtendScript）**确定性**操控 Adobe Illustrator，
> 支持 **画 → 导出 → 看图 → 调整 → 复看** 完整闭环。本技能 = 命令大全 + 配方 + 脚本 + 版本沉淀规程，
> 新用户 5 分钟上手，老用户按版本持续沉淀经验。

**阅读顺序**：`🔒 铁律` → `🚀 快速开始` → 按任务查 `📖 命令大全` / `🔁 闭环配方` / `🧰 批量配方`。

---

## 🔒 铁律（不许违背）

1. **绝不保存用户文档**：harness 全程 `DONOTSAVECHANGES`；禁止 save / saveAs / 另存为。
2. **只动自己新建的「未标题-*」**：收尾必须 `close-untitled` 清场（先 `--dry-run` 看，再实关）。
3. **不碰用户文件**：当前 harness 只操作**活动文档**，不打开/不覆盖用户 .ai 文件；要读用户文件内容先问用户。
4. **分步执行**：一次一条命令；写操作后核对返回 JSON（`changed` / `ok` / `bounds` / `fill`），不要静默连招。
5. **证据格式**：动作给「命令 + 原始 JSON 关键字段 + 产物路径」；看图给「OCR 列表 + 主色列表」；收尾给 `doctor` 的 `doc_count=0`。
6. **先看版本**：开工先跑 `doctor`（返回里有 `version`）→ 与下方「版本适配表」对账，无则补一行。

## 🚀 快速开始（新用户 5 分钟）

> `<SKILL>` = 本技能目录（本机：`E:\MemOmics-Agent\hermes_home\skills\bioinformatics\adobe-illustrator`）。
> 统一入口 `scripts/ai.py` 自动找已装 harness；找不到就用**自带快照**（零安装）。`--json` 必须写在子命令**之前**。

```bash
# 0) 桥检查（顺带拿 Illustrator 版本）
python "<SKILL>/scripts/ai.py" --json doctor
# → {"bridge":true,"cscript":"...","illustrator":{"version":"30.0.0","doc_count":0,...}}

# 1) 冒烟（隔离文档：矩形+文字 → PNG → 自动关闭）
python "<SKILL>/scripts/ai.py" --json probe --text "hello" --size 20

# 2) 第一轮：画（x=距左，y=距顶）
python "<SKILL>/scripts/ai.py" --json new-doc --width 800 --height 600
python "<SKILL>/scripts/ai.py" --json rect --x 60 --y 60 --w 300 --h 180 --color "#e04040"
python "<SKILL>/scripts/ai.py" --json text-add --content "第1轮：红色标题" --x 70 --y 300 --size 40
python "<SKILL>/scripts/ai.py" --json export "<OUT>/r1.png" -f png --bg white

# 3) 看图（MemOmics 内置工具，不是 CLI）
#    vision_describe(image_path="<OUT>/r1.png", question="OCR 读出什么？主色有哪些？")

# 4) 按所见调整（示例：矩形变绿 + 字号 60）
python "<SKILL>/scripts/ai.py" --json recolor --color "#00aa55" --index 0
python "<SKILL>/scripts/ai.py" --json text-set --size 60
python "<SKILL>/scripts/ai.py" --json export "<OUT>/r2.png" -f png --bg white

# 5) 复看 + 数字核对
#    vision_describe r2 → 与第 4 步预期对账；再 items 核对 bounds/fill/size
python "<SKILL>/scripts/ai.py" --json items

# 6) 清场（必须）
python "<SKILL>/scripts/ai.py" --json close-untitled --dry-run
python "<SKILL>/scripts/ai.py" --json close-untitled
python "<SKILL>/scripts/ai.py" --json doctor        # 确认 doc_count=0
```

一键演示整条链（画/导出/清场 + sha256 摘要，另附看图提示）：`python "<SKILL>/scripts/loop_demo.py" --out <OUT>`。

本机已装 harness 全路径（直接用亦可）：`E:\MemOmics-Agent\.venv\Scripts\cli-anything-illustrator.exe`。

## 🎯 触发场景表（用户说什么 → 怎么走）

| 用户说 | 走法 |
|--------|------|
| "用 AI / Illustrator 画个…" | 快速开始 → 闭环配方 |
| "在 AI 里改个字 / 统一字号" | `text-list` → `text-set --size N` → `text-list` 复验 |
| "把矩形/颜色换一下" | `items` → `recolor --color … [--index i] [--target path\|text]` |
| "挪个位置 / 排整齐" | `move --index i --dx … --dy …`（dy 正=向下） |
| "导出 PNG/PDF/SVG" | `export <path> -f png\|pdf\|svg`（看图必须 `--bg white`） |
| "画得对不对 / 帮我看看" | 导出 → `vision_describe` 看图 → 报告 OCR+主色 |
| "来一轮完整测试" | 闭环配方（≥3 轮：画→看→调→看） |
| "AI 里现在有什么" | `info` + `items` + `text-list`（只读三件套） |
| "清掉刚开的东西" | `close-untitled --dry-run` → `close-untitled` |

> 与 `cli-anything`、`windows-com-app-automation` 可**同时命中**（互补：框架/桥建设 vs 本操作手册）。

## 📖 命令大全（16 条）

### 只读类

| 命令 | 用途 | 关键返回 |
|------|------|---------|
| `doctor` | 桥检查（顺带版本） | `bridge` / `cscript` / `illustrator.version` / `doc_count` |
| `info` | 活动文档概况 | `version` `doc_count` `active_doc` `saved` `path` `artboard_count` `active_artboard` `artboard_rect` `layer_count` `text_frame_count` `path_item_count` |
| `artboards` | 画板清单 | 每项 `index/name/rect(原生坐标)/active` |
| `text-list` | 文字清单 | 每项 `index/contents/font/size/bounds` |
| `items` | 对象清单（矩形+文字） | `pathitems[]`（`index/fill/bounds`）+ `textframes[]`（`index/size/fill/contents`），各 ≤40 |
| `probe [--text T --size N]` | 冒烟：隔离文档画+导出+关闭 | 导出路径与字节 |
| `gradient-probe` | 渐变工作流探测（复用现有渐变） | `applied_via_gradientcolor` 等 |

### 写入类（全部不保存；需先 `new-doc` 或已有活动文档）

| 命令 | 参数 | 示例 / 注意 |
|------|------|------------|
| `new-doc` | `--width 800 --height 600` | 新建**未标题**文档；返回 `created/doc_count/artboard_rect` |
| `rect` | `--x --y --w --h --color "#RRGGBB"` | x=距左、y=距顶；返回 `bounds`（原生坐标） |
| `text-add` | `--content T --x --y --size --color --font` | `--font` 用 PostScript 名（如 `ArialMT`） |
| `recolor` | `--color C [--index -1\|i] [--target path\|text]` | `-1`=全部；返回 `changed/total/fill` |
| `move` | `--index i --dx --dy [--target]` | dx 正=右，dy 正=**下**；返回移动后 `bounds` |
| `text-set` | `--size N` / `--font PS名` | 作用于**全部**文字帧；返回 `changed/skipped` |
| `export` | `<输出路径> -f pdf\|svg\|png [--bg transparent\|white]` | 看图必加 `--bg white`；返回 `exists/bytes/format` |
| `close-untitled` | `[--dry-run]` | 关未保存「未标题-*」（含空文档）；返回 `closed/kept/docs_after` |

### 交互

`repl`（无子命令时默认进入）：`:h` 帮助、`:info`、`:artboards`、`:textlist`、`:set <pt>`、`:probe`、`:q` 退出。

## 📐 坐标、颜色与导出约定

- **屏幕语义坐标**（-`rect`/`text-add`/`move`）：`x`=距画板**左**、`y`=距画板**顶**；`move` 的 `dy` 正=向下。
- **原生坐标**（`items`/`artboards` 返回的 `bounds/rect`）：Illustrator 口径，y **向上**——两套坐标不要混读，用 `items` 复核。
- **颜色**：`#RRGGBB`（支持 `#RGB`）；非法颜色干净报错 `{"error":"bad color: ..."}` exit 2。
- **透明底坑**：PNG 默认透明，像素统计会读成**黑色** → 看图前一律 `--bg white` 拍平白底。
- **只读 vs 写入**：任何写操作都不会落盘（`saved:false` 属正常）。

## 🔁 全链路闭环配方（画 → 导出 → 看图 → 调整 → 复看）

```
第1轮  画     new-doc → rect → text-add → export r1.png --bg white
        看     vision_describe(r1)  → 断言：OCR 读到文字 + 主色含目标色
第2轮  调整   recolor / text-set / move   → export r2.png
        再看   vision_describe(r2)  → 断言：红色消失、主色变绿、文字仍在
第3轮  扩写   move + text-add            → export r3.png
        再看   断言：≥2 段 OCR、目标色像素级存在
收尾   items 数字核对 → close-untitled → doctor doc_count=0
```

**验收证据三重交叉**（缺一不可）：
1. 命令原始 JSON（`changed/ok/bounds/fill`）；
2. 产物 PNG 路径 + 字节数 + `sha256`；
3. 看图证据（OCR 列表 + 主色列表），必要时**像素级复核**。

**复现性**（2026-10-04 实测）：同一命令序列重跑 → PNG **逐字节一致**（可当回归基线）。

**看图口径注意**：`vision_describe` 的主色榜是 top-5，**<0.5% 的细笔画会被漏**（如小号蓝字）——判"某色是否存在"用像素级核验（PIL 统计目标色像素数），不要仅凭 top-5 榜下结论。

## 🧰 批量与进阶配方

- **统一字号**：`text-list`（先看基线）→ `text-set --size 28` → `text-list`（复验全变）。
- **批量换色**：`recolor --color "#111111" --index -1 --target text` 一次改全部文字；矩形同理 `--target path`。
- **多格式交付**：同文档连发 `export out.pdf` / `export out.svg` / `export out.png --bg white`。
- **快速迭代**：进 `repl` 用 `:set 28` 这类短命令做手感调试，正式留痕再走完整命令行。
- **当前覆盖边界（诚实版）**：仅"当前活动文档 + 新建文档"；**未实现**打开/另存副本/圆形/图层/嵌入图片（见下方路线图）。
  需要这些能力时按「经验沉淀规程」扩展 harness，不要假装支持。

## 🧪 版本适配与经验沉淀（本技能的核心机制）

**版本适配表**（每次任务对账；新版本实测后追加）：

| Illustrator 版本 | 环境 | 状态 | 备注 |
|---|---|---|---|
| 30.0.0 | Windows 11 | ✅ 全量验证（2026-10-04） | 16 命令全通；会话 A（3轮）/B（2轮）+ 复现哈希一致 |

**沉淀规程（遇到差异/新需求时四步走）**：
1. **留痕**：`skill_evolution(action="record_run"/"record_error", …)` 记录命令、版本、现象、结论。
2. **回填本文件**：版本表补行；坑表补行（症状→根因→解法）；Proven Scripts 补已验证脚本。
3. **缺能力 → 扩展 harness**（3 步）：
   a. 在 `illustrator_backend.py` 加 JSX 函数（ES3！手拼 JSON、写操作 `DONOTSAVECHANGES`）；
   b. 在 `illustrator_cli.py` 加 click 子命令（`--json` 从 group 继承）；
   c. 实测（probe/新命令）→ 回填本文件。
   > harness 源码位置：`results/memomics-ad6fdb02/software_control/illustrator/agent-harness/`（editable 安装，改完即生效）；自包含快照在 `scripts/harness_bundle/`（改完记得同步快照）。
4. **改了触发词/元数据才需要**：`python -m webui.skills_registry --build` → `python scripts/check_skills_gate.py --quiet` → 路由矩阵 `webui/tests/fixtures/skill_routing_matrix.json` 补用例（每个 RED 技能必须有 case）。

## 📦 脚本库（scripts/）

| 脚本 | 用途 | 用法 |
|------|------|------|
| `ai.py` | 统一入口：自动找已装 exe（env → 仓库 venv → PATH），找不到用自带快照 | `python ai.py --json <子命令> …`；`--which` 看选用路径；`--bundled` 强制快照 |
| `loop_demo.py` | 全链路演示（画→导出×3→清场；含 sha256 摘要与看图提示） | `python loop_demo.py --out <OUT>` |
| `harness_bundle/` | harness 自包含快照（零安装回退；与已装版同步维护） | 由 `ai.py` 自动使用 |

## ⚠️ 坑表（Common Issues）

| 症状 | 根因 | 解决 |
|------|------|------|
| 导出 PNG 看图主色 `#000000 88%`（明明白底） | PNG 默认**透明底**，像素统计把 alpha 当黑 | 导出加 `--bg white`（2026-10-04 实测修复口径） |
| 看图 top-5 主色漏了刚画的细笔画颜色 | 主色榜按面积占比截断，<0.5% 不进榜 | 像素级复核（PIL 统计目标色像素数）再下结论 |
| `artboard_rect` 出现 `[(0),(300)…]` 这种非法 JSON | 旧版 JSX 数组元素带括号 | ✅ 已修（2026-10-04，三处） |
| 中文文档名/画板名乱码 | cscript 控制台 GBK 输出 vs Python UTF-8 解码 | ✅ 已修（UTF-8→GBK→replace 兜底解码） |
| gradient-probe 报 `viaCollection 未定义` 并遗留「未标题-1」 | ES3 未声明变量直接抛 Error 2；失败路径走不到 close | ✅ 已修（补 `var viaCollection=false;`）；遗留文档用 `close-untitled` 清 |
| `rect/text-add` 位置不对 | 坐标是屏幕语义（y 距顶）；`items` 返回的是原生坐标（y 向上） | 两套坐标别混读；用 `items` 复核 |
| `recolor` 报 `bad color: 'zzz'` | 颜色格式非法（exit 2 防呆） | 用 `#RRGGBB` |
| `No such option '--json'` | `--json` 是 group 级选项 | 移到子命令**之前** |
| `Error 1302: No such element` | RGB 文档里取 CMYK 色板 | 直接构造 `new RGBColor()` |
| `Internal error`（赋值 `fillColor = doc.gradients[0]`） | ExtendScript 不能把 Gradient 对象当颜色 | 用 `new GradientColor()`：`gc.gradient=doc.gradients[i]; gc.origin=[x,y]; gc.angle=45` |
| 新建 RGB 文档找不到渐变色板 | 新建文档渐变未注册进 `swatches`（`doc.gradients` 有） | 走 `doc.gradients[i]`，别 `swatches.getByName` |
| `COM_FAIL` / `JS_FAIL` | 桥不通 / JSX 语法错（ES3!） | `doctor` 探活；检查 JSX 是否 ES3 兼容 |
| `new-doc` 后 `saved=true` 和直觉不符 | 新建文档在首次修改前 AI 报告 saved=true | 无影响；`close-untitled` 同时覆盖「空文档」与「未保存」 |
| rail_review(post) 对 **before/after 对照图**报「图片太小，必须重新生成」 | 旧版门禁 `<5KB` 一律当疑似空白，缺对照图维度 | ✅ 已修（先验像素证据；空白/损坏仍阻断）。⚠️ 服务器旧进程重启后生效；对照图用 `artifact_manifest.json` 标注 role |
| 平台把 `xxx.png` 文件名当"技能名"去解析（`skill_invoke unknown`） | 平台解析器把消息里的文件名误判为技能引用（无害） | 无动作；知道即可 |

## ✅ Proven Scripts

| 日期 | 场景 | 结论 |
|------|------|------|
| 2026-10-04 | 3 轮闭环（红→绿+字号60→位移+加蓝字，每轮 vision 复看） | ✅ 会话 A 实测通过；每轮命令 JSON+PNG+OCR/主色三重证据 |
| 2026-10-04 | 白字白底缺陷 → 看图发现 → recolor 黑 → 复看 | ✅ 会话 B 实测通过（OCR 0→1 条，暗像素 0→8.54%） |
| 2026-10-04 | 同序列重跑复现性 | ✅ 3 张 PNG sha256 与首跑**逐字节一致** |

## 🔗 相关技能

- `cli-anything`：CLI-Anything 框架总纲（装 cli-hub / 自建 harness 7 阶段规范）。
- `windows-com-app-automation`：COM→VBScript→ExtendScript 桥的建设细节（本技能的底座）。
- `skill-registration-and-routing`：触发词/注册/索引排障（本技能元数据变更时用）。