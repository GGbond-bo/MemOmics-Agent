# PPTX + HTML 双交付，与幻灯片预览图

固化自 2026-10「五个科研 Agent 对比 + 平台机制」deck 的两轮用户反馈。

> ⚠️ **归属说明 / 重叠提示**：PPTX 生成的主技能是 `pptx-generation`（**手工编写，策展不可改**），
> 且其正文是 Phylo/英文品牌规范。本文件承载 **中文汇报 deck** 侧的增量偏好与「pptx + HTML 双交付」
> 这条链路 —— 做中文 deck 时两个 skill 一起看。策展若要归并，目标宿主是 `pptx-generation`。

---

## 一、为什么会有「双交付」

用户在这个场景下的确认答复是：**「输出 .pptx 文件（可编辑）；同时出一份 HTML 网页版；
页数 6 页紧凑版；MemOmics 部分只讲机制不讲代码；风格浅色学术风」**。

即：**pptx 给人编辑/现场讲，HTML 给人转发/离线看**。两者必须内容一致。

## 二、内容单源、两路渲染（关键做法）

不要写两遍内容。把标题 / 表格 / 流程卡先写成**数据**（list / dict），再分别喂给两个渲染函数：

```python
TITLES   = [("01", "四篇文献一览", "副标题…"), ...]   # 页序 + 标题
P1_ROWS  = [["项目", "来源 / 团队", "期刊 · 时间", "产品形式"], [...], ...]   # 表格即数据
FLOW     = [("用户", "数据路径 + 科学问题", BLUE), ...]                       # 流线页即数据

# 渲染 1：pptx（位置式布局，Inches/Pt）
for i, (num, title, sub) in enumerate(TITLES):
    s = prs.slides.add_slide(BLANK); header(s, num, title, sub)
    ...
# 渲染 2：HTML（同一份 TITLES / P1_ROWS / FLOW → table / flex 流程）
```

好处：改一处内容，两边同时生效，不会漂移。

## 三、用户对**中文汇报 deck** 的结构偏好（原话级）

> 第一版 6 页被否：「**不是很好，不够简洁**」，随后用户逐页指定结构。

| 偏好 | 用户原话 / 表现 | 做法 |
|------|----------------|------|
| **表格优先** | 「可以做成一个表格」出现两次 | 凡有 ≥2 条可比信息（多项目对比 / 多方法对比 / 前后对照）→ 一律表格，不写段落 |
| **对比页只说优点** | 「**不要说缺点，说优点**，他们怎么解决这些问题，工作量，内容等等」 | 对比他人方案的页面只列 设计初衷 / 解法 / 工作量规模；缺点另设边界页或收在总结页末尾 |
| **出发点页只讲问题** | 「**不要说太多，直接说问题**」 | ≤3 条，每条一行，结论一句话收尾 |
| **逐页指定结构** | 「第一页…第二页…第三页…第四页…剩下几页，你自己补充一下，我看看」 | 严格按指定页序；agent 的补充页**排在指定页之后**；不要额外加封面页 |
| **"不够简洁"的真实含义** | 页数没说多，说的是**每页字太多 + 缺表格** | 压缩单元格文字，不是砍页数 |

**流线页（分析流程 / 机制链路）**：用 pptx **原生形状**画环节卡 + `MSO_SHAPE.RIGHT_ARROW` 连接；
环节 ≤8 排两行四列；闭环回流单独做一条居中浅色条。
⛔ **不要贴 Mermaid 截图**（PPTX 渲染不了 Mermaid），也不要在 deck 工作流里调 Mermaid。

**中文 deck 字体**：必须显式设 `font.name = "Microsoft YaHei"`（**每个 run 都设**，
python-pptx 不继承），否则中文可能回落成方框/字形不一致。
图内说明文字仍守既有偏好「图内英文、正文中文」；deck 正文跟随用户语言。

## 四、`%`-formatting 撞上 CSS 的坑（实测报错）

HTML 模板习惯写成 `HTML = """…%s…""" % {...}`，但 CSS 里有裸 `%` 时会炸：

```
ValueError: unsupported format character ';' (0x3b) at index 1865
```

罪魁就是 `table.t{width:100%;...}` —— `%;` 被当成格式符。定位方法：

```
search_files(pattern="%[^s(]", path="<脚本>")   # 列出所有非 %s/%( 的百分号
```

两种修法：

1. CSS 里写 `width:100%%;`（有效但丑，且以后每加一个 `%` 都要记得）；
2. **改用占位符替换（推荐）**：模板里写 `__S1__` / `__T1__`，最后
   ```python
   for k, v in SUBS.items():
       HTML_TPL = HTML_TPL.replace("__%s__" % k, v)
   ```
   CSS 一个字都不用改。

## 五、幻灯片预览图（deck 交付的必做收尾）

**动机有两个，第二个是硬门禁：**

1. 用户无法在对话里预览 `.pptx` 版式 —— 逐页 PNG 让他能直接扫、直接指页号提意见；
2. `rail_review(post)` 会用「数据图」标准判 deck：`figure_count=0` → 报
   **「未生成任何图片 — 每步至少 1 张图，必须重新执行」**，并附带
   「No result files found in output directory」。
   ⛔ **正确修法是真渲染预览图，不是凑一张占位图。**

**渲染路径选择（实测）**：

| 路径 | 本机实测 | 说明 |
|------|---------|------|
| LibreOffice `soffice --headless` | ✗ 未安装 | 装了就走 `--convert-to pdf` + pymupdf 逐页转 PNG |
| PowerPoint COM | ✗ `Dispatch('PowerPoint.Application')` → `com_error 服务器运行失败 (-2146959355)` | 用户办公套件是 **WPS**，本机无 `POWERPNT.EXE` |
| **HTML → Edge 无头截图** | ✅ **可用** | 与 HTML 双交付天然配套，本文件采用的路径 |

**现成脚本**：`scripts/render_slide_previews.py`

```bash
python scripts/render_slide_previews.py <deck.html> <out_dir>/figures
# → slide_00.png（封面）, slide_01.png … slide_NN.png
```

原理：把 HTML 每个 `<section>` 拆成独立 HTML → `msedge --headless=new --screenshot`
（`--window-size=1600,3000`）→ PIL 从右下角裁掉空白，让每页高度贴合内容。

**出图后必须核验**（否则等于把坏页交给用户）：`vision_describe` 对最复杂的一两页做 OCR，
断言 ①表头/列齐全 ②关键数字都在 ③无裁切。实测这一步真的能确认四列表格完整
（如 `+402.3% / US$14 / 91.2% / 2500 / 314 / 599–593` 全部命中）。

## 六、`rail_review(post)` 传参（deck 场景）

- `output_dir` 传**含 `figures/` 的目录**；只传 `reports/` 必判「未生成任何图片」。
- `code_executed` 传**真实构建 + 渲染 + 核验过程**（表格数据定义、两路渲染、Edge 截图、
  OCR 断言结果），不要只写一句摘要 —— 过短会被判无效审查。
- 预览图就位后 `figure_count ≥ 1`，审查通过。

## 七、交付话术

- 明确告诉用户：python-pptx 输出的是**标准 OOXML**，**WPS 可直接打开编辑**
  （本机没有 Microsoft Office 也不影响）。
- 一并给出：`.pptx`（可编辑）+ `.html`（自包含零 CDN，可离线/转发）+ `figures/slide_*.png`（预览）。
- 收尾一句「哪页要再压或改结构，指一下页号就行」比再问一轮更省事。