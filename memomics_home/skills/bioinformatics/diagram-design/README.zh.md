# diagram-design — 编辑级示意图（MemOmics 本地化版）

来源: [cathrynlavery/diagram-design](https://github.com/cathrynlavery/diagram-design) (MIT, v2.3)
上游描述: 29 editorial diagram types for Claude Code. Self-contained HTML + SVG. No shadows, no Mermaid-slop.

## MemOmics 适配说明

1. **分工**: 本 skill 管**示意图/流程图/架构图/路线图/专利方案图**（审美与信息设计）；
   科学数据图（箱线图/UMAP/火山图等）仍走 matplotlib/R + nature-figure / scipilot-figure。
2. **输出位置**: `results/<sid>/diagrams/`（HTML + 内联 SVG）。
3. **PNG 转换**: 用 svglib（`from svglib.svglib import svg2rlg; from reportlab.graphics import renderPM`），
   或 reportlab；SVG 中的 CSS 变量需先替换为字面值。
4. **无任何绘图 API/服务**: 纯文本生成 HTML+SVG，浏览器打开即看。
5. 上游的 Claude 专属工具名（Read/Write/Glob 等）在 MemOmics 中对应 read_file / write_file / search_files。
6. 27 种版式明细见 SKILL.md §3 与 references/type-*.md；语义模式见 references/semantic-patterns.md。
7. 首次为项目出图时按 SKILL.md §0 走风格闸门（品牌色定制，默认纸白+珊瑚橙）。

## 常用流程

```
用户要示意图 → 选 semantic pattern（如需）→ 选 visual type（27 选 1）
→ 读 references/type-*.md 的版式语法 → 写 HTML（内联 SVG+CSS，遵循 style-guide.md 令牌）
→ self_check.py 自检（对比 output-spec.md）
→ 保存到 results/<sid>/diagrams/<name>.html → 按需 svglib 转 PNG
```
