---
name: interactive-html-deliverables
description: "构建自包含交互式 HTML 交付物（汇报展示页 / 数据看板 / 成果介绍页）：浅色主题设计令牌、10+ 类交互组件、分段落盘拼接、浏览器实测验收、数字可溯源、演讲者模式。触发：做成 html / 展示页 / 汇报页 / 介绍页 / 数据看板 / dashboard / 主题不要太暗 / 多一些交互 / 丰富专业有未来感 / 给老师同学展示。"
when_to_use: "用户要一个**给人看**的交互式网页交付物（汇报、展示、介绍、看板、评审演示），而不是分析报告的结论页时。若目标是「把分析结果写成报告」→ 用 bioinformatics-html-report。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [html, visualization, dashboard, showcase, interactive, deliverable]
    difficulty: medium
    language: Python+JS
    category: bioinformatics
---

# 自包含交互式 HTML 交付物

面向「给人汇报/展示」的网页交付物：**单文件、无外部依赖、浅色主题、10+ 类交互**。
与 `bioinformatics-html-report` 的分工：那个产出**分析报告**（结论 + 图 + 表 + 日志溯源）；
本 skill 产出**展示页 / 看板 / 介绍页**（叙事 + 交互 + 视觉层次）。

🔧 组件级代码配方（CSS 令牌、每个交互的成品实现、验收断言）见
**`references/component-recipes.md`** —— 动手前先读它，别从零写。

## 一、用户偏好（默认形态，2026-09-16 用户原话定稿）

> 「做成 html，主题**不要太暗**，可以多一些**交互设计**，各种交互展示，丰富，专业，也有一定的未来感」

| 维度 | 默认做法 |
|------|---------|
| 主题 | **浅色**（底 `#f5f8fd` + 白卡片 `#fff`），深色只作可选开关，**不要默认深底** |
| 依赖 | **零外部依赖**：无 CDN、无网络字体；打开即用（现场投屏最怕断网/404） |
| 交互 | ≥10 类：主题切换、导航高亮+进度条、数字滚动、标签页、分层/步骤点击、卡片展开、筛选、表格排序、canvas 图表、粒子/网格动效、键盘快捷键 |
| 专业感 | 每个数字可溯源、来源标注 DOI/PMID、**显式写出「边界/做不到什么」章节** |
| 未来感 | 渐变主色（蓝→青→紫）、网格底纹、发光点缀、等宽字体数字，别堆阴影 |

> 🔴 **第二轮修正（2026-09-16，优先级高于上表）**：
> 用户看完 v1 后提出「字太多了，不直观，很多时候可以用流程动画展示，**很多东西不需要讲那么细**」；
> 随后又要求「**去掉展示 memomics 跟别的对比**，重点在展示未来自主科研，和未来 AI 发展上，
> **这些用更多流动的过程图展示细节**」。
>
> 由此固化的现行标准：**正文 ≤2000 字**；每页 = 1 标题 + 1 个**持续运动**的视觉重心 + 2–4 个短标签；
> 交互不求多，而求**动效一直在跑**；**不做「我和别人比」的对比页**（用户要的是往前看）。
> 上表「≥10 类交互」是 v1 的目标形态，v2 起以「一页一个流动视觉」优先。
> 动画叙事密度、五种流动过程图配方、改版工作流 → 见 **`animation-first-showcase`**。

**汇报场景标配 = 演讲者模式**：每章节内嵌讲稿块，一键切换显示（用户次日就要脱稿讲）。快捷键：`←/→` 切章节、`S` 讲稿、`D` 深浅色。

## 二、构建流程

1. **先盘数据，再写文案**：页面上的所有规模数字由脚本现场扫描生成（`collect_stats.py → _stats.json`），
   页脚标注扫描时间。⛔ 禁止手写死数字（用户必查）。
2. **分段落盘**：`write_file` 分 8–10 段到 `reports/parts/p1_head … p9_script`（绕开单次输出长度上限），
   再一次性拼接成单文件：
   ```python
   parts = ["p1_head.html", ..., "p9_script.html"]
   html = "".join(open(os.path.join(base,"parts",p), encoding="utf-8").read()+"\n" for p in parts)
   open(os.path.join(base,"MemOmics_Showcase.html"),"w",encoding="utf-8").write(html)
   ```
3. **配套一张静态总览图**（300 dpi PNG，资产条形 + 能力雷达这类）：既能过 `rail_review(post)`
   （`output_dir` 传会话根目录，见 §四），也直接给用户一张能拷进幻灯片的图。
4. **浏览器实测验收**（§三）——**不是可选项**。
5. **沉淀**：`skill_evolution(action='record_run')` + 把扫描脚本/绘图脚本留在 `scripts/`。

## 三、浏览器实测验收（只看文件大小 = 交付风险）

```
browser_navigate("file:///<绝对路径>")     # ① 结构崩没崩
browser_console()                          # ② js_errors 必须 = 0
browser_console(expression="JSON.stringify(...)")   # ③ 断言
```
断言至少覆盖：canvas 尺寸与**非空白像素采样**、交互点击后的类切换、筛选后的元素计数、图片 `naturalWidth`、
主题背景色（确认真的是浅色）、`scrollWidth - innerWidth == 0`（无横向溢出）。

> 本次实测抓到两个**静默缺陷**（文件大小、文本内容都看不出来）：CSS 半失效、canvas 只有 300px 宽。
> 只回「已生成」而不实测，等于把坏页交给用户。

## 四、rail_review(post) 对 HTML 交付物的正确传参

- `output_dir` 传**会话根目录**（同时含 `figures/` 与 `reports/`），并在同轮产出 300 dpi 静态图 ⇒ `figure_count ≥ 1` 通过。
- 只传 `reports/` 必被判「未生成任何图片」。
- `code_executed` 传**构建与验证的真实过程**（分段清单 + 拼接 + 浏览器断言结果 + 修复过的缺陷），不要只写一句摘要。

## 五、高频坑（都实际踩过）

| 现象 | 根因 | 处置 |
|------|------|------|
| 半段 CSS 不生效、页面顶部出现一堆 CSS 文本 | 多段拼接时 **`</style>` 写了两次**（第 1 段顺手闭合了），第 2 段 CSS 变成正文 | 全文件 `</style>` 只允许 1 个；验收 `[...styleSheets[0].cssRules].some(r=>r.selectorText==='canvas')` |
| canvas 图挤成 300px 宽 | CSS 只写 `max-width:100%` → 布局宽度仍是 canvas 内置 300px，`clientWidth` 量到 300 | 写 `canvas{width:100%;display:block}`；并在 `load` 与 `document.fonts.ready` 后再 `drawAll()` 一次 |
| `patch` 改数字把标签吃掉，产出裸文本行 | old_string 从标签中间起手（如 `;color:transparent">189</h4>`），模糊匹配命中残缺跨度，仍返回 `success:true` | old_string 以整行/完整标签为锚；同常量多处 → `replace_all=true`；**每次 patch 后读 diff**，专查「有 `-` 无 `+`」与「新增行以 `;`/`>` 开头」；打歪就用整行+上下文重打一次 |
| 数字被质疑 | 手写死/过期数字 | 脚本现场扫描 + 页脚扫描时间 + 原始 JSON 落盘；说明「随使用持续增长」 |
| 主观评分被当成绩 | 雷达图/评分表未声明 | 页面上显式标注「定性评估，**非基准成绩**」 |
| HTML 模板走 `%` 格式化时抛 `ValueError: unsupported format character ';' (0x3b)` | 模板里有裸 `%`（典型：CSS 的 `width:100%;`），`%`-formatting 把它当格式符 | ① CSS 里写 `%%`；② **改用 `str.replace("__KEY__", …)` 占位符（推荐，CSS 免改）**。定位用 `search_files(pattern="%[^s(]")`。见 `references/deck-and-html-twin.md` |
| deck/PPT 交付被判「未生成任何图片」（`figure_count=0`） | rail_review(post) 用「数据图」标准判 deck；且 `output_dir` 只含 `reports/` | **真渲染逐页预览 PNG**（HTML → Edge 无头截图），`output_dir` 传含 `figures/` 的目录。⛔ 不要凑一张占位图。脚本：`scripts/render_slide_previews.py` |

## 六、内容结构模板（汇报页 10–12 节）

> ⚠️ **2026-09-16 第二版已按用户要求改写第 2 / 8 / 9 节**：用户明确说「去掉展示 memomics 跟别的对比」，
> 因此**竞品卡、能力对比表、雷达图这三节全部删除，不要自作主张加回来**。
> 行业时间线可以留（那是**发展进程**，不是对比）；未来章节必须做成**持续运动的流动过程图**。
> ⛔ 若沿用旧模板把「竞品对比」重新加回去，等于直接违反用户已下达的指令。

1. Hero（一句话定位 + 数字条 + 粒子背景 + 流动带）
2. 它是什么（标签页：底线原则 · 能对它说什么）——**不做同类对比，不放竞品卡**
3. 架构分层（点层出详情面板）
4. 完整流程（点步骤看命令与产出）
5. 核心机制（可展开卡片 + 一个「现场演示」交互器——本次是 7 角色辩论逐步揭示）
6. 数据看板（canvas 条形/环形 + 资产表 + 静态总览图）
7. 实战战绩（4 张真实项目卡：规模 / 做了什么 / 踩过的坑）
8. 行业全景（**时间轴**——发展进程保留，竞品卡删掉）
9. 未来·循环流（科研闭环：6 节点环 + 旋转臂 + 顺序点亮 + 三股流）
10. 未来·阶梯流（能力演进逐级爬升 + 双汇流带）
11. 诚实的边界（做不到什么 —— **必须有**）
12. 路线图（三阶段）+ 来源（DOI/PMID 列表 + 页脚路径与生成时间）

### 本目录两个 skill 的分工（做展示页时一起加载）

| skill | 管什么 |
|-------|--------|
| `interactive-html-deliverables`（本 skill） | 构建骨架：设计令牌、组件配方、分段落盘拼接、浏览器验收、rail_review 传参 |
| `animation-first-showcase` | 动画优先的叙事密度（正文 ≤2000 字）、**五种流动过程图配方**、改版工作流与 6 个坑 |

## 七、PPTX + HTML 双交付（deck 场景）

用户在同一次需求里常同时要 **`.pptx`（可编辑，现场讲）+ `.html`（自包含，转发/离线看）**。
做这类交付时，本 skill 与 `pptx-generation`（**手工编写、策展不可改**）一起看。

**内容单源、两路渲染**：标题 / 表格 / 流程卡先写成数据（list / dict），再分别喂给 pptx 渲染函数
与 HTML 渲染函数 —— 不要写两遍内容，否则必然漂移。

**中文汇报 deck 的结构偏好（用户原话级，2026-10 固化）**

| 偏好 | 做法 |
|------|------|
| 表格优先（「可以做成一个表格」，两次） | 凡有 ≥2 条可比信息（多项目 / 多方法 / 前后对照）→ 一律表格，不写段落 |
| 对比页只说优点（「**不要说缺点，说优点**」） | 只列设计初衷 / 解法 / 工作量规模；缺点另设边界页或收在总结页末尾 |
| 出发点页只讲问题（「**不要说太多，直接说问题**」） | ≤3 条，每条一行，一句话收尾 |
| 逐页指定结构（「剩下几页，你自己补充一下」） | 严格按指定页序；补充页排在指定页之后；不加多余封面页 |
| 「**不够简洁**」的真实含义 | 说的是**每页字太多 + 缺表格**，不是页数多 → 压单元格文字，别砍页数 |

- **流线页**（分析流程 / 机制链路）：pptx 原生形状画环节卡 + `MSOSHAPE.RIGHT_ARROW` 连接，
  ≤8 个环节排两行四列；闭环回流单独做一条居中浅色条。
  ⛔ **不要贴 Mermaid 截图**（PPTX 渲染不了 Mermaid）。
- **中文字体**：显式设 `font.name = "Microsoft YaHei"`（**每个 run 都设**，python-pptx 不继承）。

### 幻灯片预览图（deck 交付的必做收尾）

`rail_review(post)` 会用「数据图」标准判 deck（`figure_count=0` → 「未生成任何图片」）；
**正确修法是真渲染逐页预览 PNG**，不是凑占位图。本机无 LibreOffice / 无 POWERPNT
（用户办公套件是 **WPS**）时，走 **HTML → Edge 无头截图**：

```bash
python scripts/render_slide_previews.py <deck.html> <out_dir>/figures
```

出图后用 `vision_describe` OCR 断言（表头列齐全 / 关键数字都在 / 无裁切）。
`output_dir` 传**含 `figures/` 的目录**。交付时说明 python-pptx 是标准 OOXML、**WPS 可直接编辑**。

📖 完整细节（`%` 坑的报错与两种修法、三条渲染路径实测对比、rail_review 传参、交付话术）→
**`references/deck-and-html-twin.md`**

## Support Files
- `references/component-recipes.md` — 浅色设计令牌 + 14 类交互的成品 CSS/JS + 浏览器验收断言 + 拼接脚本
- `references/deck-and-html-twin.md` — PPTX+HTML 双交付、**中文 deck 结构偏好**、`%`-formatting 坑、幻灯片预览图渲染与验收
- `scripts/render_slide_previews.py` — HTML 幻灯片 → 逐页 PNG 预览图（Edge/Chrome 无头截图 + 自动裁白边）
