# 论文 15 字段结构化总结模板

> 用于 paper-summary skill 的 **Tier 2 HTML 报告**生成。
> Tier 1 (交互框解读) 不需要此模板，直接在对话中按 SKILL.md 的 9 模块输出。

## 15 字段清单

| # | 字段 | 英文名 | 核心内容 | Tier 来源 |
|---|------|--------|----------|-----------|
| 1 | 标题 | Title | 论文完整标题 + 中文译名 | 新增 |
| 2 | 作者 | Authors | 全部作者 + 通讯作者标注 + 机构简称 | 新增 |
| 3 | 期刊/年份 | Journal/Year | 期刊名、年份、PMID | 新增 |
| 4 | DOI/数据 | DOI/Data | 正式DOI + 预印本DOI + GEO accession + 交互网站 | 新增 |
| 5 | 关键词 | Keywords | 8-10 个关键词 (badge 样式) | 新增 |
| 6 | 研究背景 | Background | 科学问题 + 填补的空白 (bullet list) | Tier1 复用 |
| 7 | 研究假设 | Hypothesis | 2-4 条核心假设 | 新增 |
| 8 | 实验设计 | Experimental Design | 受试者/方案/采样/技术/QC后数据 (表格) | Tier1 扩展 |
| 9 | 方法管线 | Methods | 步骤→工具→参数 (三列表格) | Tier1 扩展 |
| 10 | 核心发现 | Key Findings | 5-8 条核心发现，每条含 callout 高亮框 | Tier1 复用+扩展 |
| 11 | 图表解读 | Figures | Figure→内容→结论 (三列表格) | PDF 提取 |
| 12 | 讨论 | Discussion | 5-6 条关键讨论点 (bullet) | 新增 |
| 13 | 局限性 | Limitations | 局限→影响 (表格) | Tier1 复用 |
| 14 | 意义 | Significance | 4 条科学意义 (bullet) | 新增 |
| 15 | 与你的关联 | Relevance | 研究对比表 + 可操作的下一步建议 | Tier1 复用+扩展 |

## 格式约定

- 暗色主题 (bg: #0f172a, text: #e2e8f0)
- 数据统计面板 (inline stat-box，顶部)
- 字段用 field-card (bg: #1e293b, border-radius: 12px)
- 关键数字用 `.highlight` 标注
- 数据库 ID (GEO/PMID/DOI) 必须可追踪
- TOC 锚点导航
- Mermaid 技术路线图用 SVG 嵌入（字段 7.5）
- 响应式布局

## 交付物

- HTML 报告 ≥25KB
- 全部图表提取 (fitz/PyMuPDF)
- Mermaid 技术路线图 SVG
- 全文文本备份
- metadata.json

## 已验证案例

| 日期 | 论文 | 物种 | 组织 | 评分 |
|------|------|------|------|------|
| 2026-07-18 | Rubenstein 2025 Muscle Multiome | human | skeletal_muscle | 9/10 |
