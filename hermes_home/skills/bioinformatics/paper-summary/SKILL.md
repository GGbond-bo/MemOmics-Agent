---
name: paper-summary
description: "两级文献解读：Tier1交互框展示(含Mermaid技术路线图+关键图表) → Tier2深度HTML报告(15字段+全部图表)"
when_to_use: "[paper-summary] 已有PDF或论文链接，需要解读论文内容。默认 Tier1 在交互框展示；用户追加说html/报告时触发 Tier2 深度HTML报告。"
version: 2.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: []
    difficulty: basic
    language: Python
    category: General Utility
prerequisites:
  r_packages: []
  python_packages: [pymupdf, markitdown]
  external_repos: [https://github.com/caj2pdf/caj2pdf.git]  # for CAJ/KDH conversion
---

## 🎯 两级触发模型

```
用户说"解读/精读/讲一下这篇..."
        │
        ▼
  ┌──────────────────────────────────────────────┐
  │  🔵 Tier 1: 轻量级解读 (默认)                  │
  │  触发词: 解读/精读/论文要点/讲一下这篇/...      │
  │  输出位置: 交互框内直接展示 (不写文件)           │
  │  耗时: ~30-60秒                                │
  └────────────────────┬─────────────────────────┘
                       │
  用户追加说 "做成html" / "html总结" / "导出报告"
                       │
                       ▼
  ┌──────────────────────────────────────────────┐
  │  🟠 Tier 2: 深度HTML报告 (按需触发)            │
  │  触发词: html/报告/总结/导出                    │
  │  输出位置: results/.../paper_summary.html      │
  │  耗时: ~2-3分钟                                │
  └──────────────────────────────────────────────┘
```

---

## Triggers

### Tier 1 触发词 (默认，交互框展示)
- `解读` / `解读论文` / `论文解读` / `全文解读`
- `精读` / `讲一下这篇` / `帮我看看这篇`
- `解读文献` / `文献解读`
- `summarize paper` / `interpret paper` / `interpret`
- `总结论文` / `概括文献` / `论文要点` / `速读`

### Tier 2 触发词 (按需，HTML报告)
- `做成html` / `html总结` / `导出报告`
- `html` / `报告` / `report`

---

## 🔵 Tier 1: 轻量级解读（交互框内展示）

### 执行流程

```
Step 1: 文本提取 → python scripts/run.py extract --tier1 {pdf_path}
         ├── 提取全文文本 (pymupdf)
         └── 提取 1-3 张关键图表 (pymupdf)

Step 2: LLM 结构化解读 → 在交互框中输出以下 8 个模块
```

### Tier 1 输出模板（必须在交互框中按此顺序展示）

#### ① 基本信息表 (Markdown 表格)
```
| 字段 | 内容 |
|------|------|
| 标题 | 完整标题 + 中文译名 |
| 作者 | 全部作者 + 通讯标注 |
| 期刊/年份 | 期刊名, 年份 |
| DOI/数据 | DOI + GEO/数据库 accession |
| PMID | PMID |
```

#### ② 研究背景与核心问题 (2-4句)
- 科学问题
- 填补的空白
- 研究假设

#### ③ 🔥 技术路线图 (Mermaid Flowchart TD) — 必出
**强制要求**：必须生成 Mermaid Flowchart TD 图，展示论文的实验设计 + 分析管线。

**样式约定**：
- 色彩分区：实验设计(蓝色系) / 分析管线(绿色系) / 关键发现(橙色系)
- 参数/数字嵌入节点文本中
- 使用 `classDef` 添加样式
- 分支清晰，不超过 25 个节点

**节点命名规范**：
```
实验设计: subj[N=6 受试者<br/>2M+2F运动 2对照]
分组:     ex[运动组 n=4<br/>40min骑行 70%VO₂max]
技术:     tech[10x snMultiome<br/>RNA+ATAC 同核]
分析:     qc[QC过滤<br/>37K细胞核]
```

#### ④ 核心发现 (5-8 条)
每条格式：
```
**发现N: 标题**
- 证据：具体数据 (P值/log2FC/效应量)
- 方法：用到的具体分析手段
- 意义：生物学/临床意义
```

#### ⑤ 关键图表展示
从 PDF 提取 1-3 张 Figure，标注 Figure 编号 + 标题 + 解读。

如果 `run.py` 提取成功 → 展示图片路径 + 解读
如果提取失败 → 从全文提取 Figure Legends 做文字解读

#### ⑥ 方法管线亮点
步骤→工具→参数 (三列表格)，只列关键方法。

#### ⑦ 局限性与创新点

| 局限 | 影响 |
|------|------|
| ... | ... |

| 创新点 | 价值 |
|--------|------|
| ... | ... |

#### ⑧ 与你的研究关联 (3-5 条)
- 每条含：关联点 + 可借鉴的方法/参数 + 下一步建议

#### ⑨ 结尾提示
> 📄 需要导出为 **HTML 完整报告**（含全部图表 + 15 字段详细解读）吗？回复「**做成 html**」即可。

---

## 🟠 Tier 2: 深度 HTML 报告（按需触发）

### 触发条件
用户说了 "做成html" / "html总结" / "导出报告" / "report" → 且当前会话已有 Tier 1 的论文内容。

### 执行流程
```
Step 1: 调用 python scripts/run.py extract --tier2 {pdf_path} --out {results_dir}
         └── 提取全部图表 + 全文文本

Step 2: LLM 生成 15 字段结构化 HTML
         └── 模板参考 references/15_fields_template.md

Step 3: 保存 HTML → 告知用户文件路径
```

### HTML 报告内容

| 模块 | 内容 | 来源 |
|------|------|------|
| 顶部面板 | 标题/作者/期刊/DOI/PMID 统计卡片 | LLM |
| TOC 导航 | 15 字段锚点导航 | 模板 |
| ① 基本信息 | 标题/作者/期刊/DOI/数据 | LLM |
| ② 关键词 | 8-10 个关键词 badge | LLM |
| ③ 研究背景 | 科学问题 + 填补空白 | Tier 1 复用 |
| ④ 研究假设 | 2-4 条 | LLM |
| ⑤ 实验设计 | 受试者/方案/采样/技术表格 | Tier 1 复用+扩展 |
| ⑥ 方法管线 | 步骤→工具→参数表格 | Tier 1 扩展 |
| ⑦ 🔥 技术路线图 | Mermaid → SVG 嵌入 | Tier 1 的图再渲染 |
| ⑧ 核心发现 | 5-8 条 + 关键数据 callout | Tier 1 复用+扩展 |
| ⑨ 图表解读 | 全部 Figure→内容→结论表格 | PDF 提取 |
| ⑩ 讨论 | 5-6 条关键讨论 | LLM |
| ⑪ 局限性 | 局限→影响表格 | Tier 1 复用 |
| ⑫ 意义 | 科学/转化意义 | LLM |
| ⑬ 与你的关联 | 研究对比表 + 可操作建议 | Tier 1 复用+扩展 |
| ⑭ 参考文献 | 主要引用列表 | PDF 提取 |

### 样式约定
- 暗色主题：bg `#0f172a`, text `#e2e8f0`
- 卡片：bg `#1e293b`, border-radius `12px`
- 数据面板：顶部 inline stat-box
- 图表：`max-width: 100%`, `border-radius: 8px`
- TOC：sticky 左侧导航
- 响应式：移动端适配
- 报告大小 ≥25KB

### 交付物
```
results/{date}_paper-summary_{title_short}/
├── paper_summary.html          # 主报告 (≥25KB)
├── figures/
│   ├── fig1.png, fig2.png, ...
│   └── roadmap.svg            # Mermaid 技术路线图
├── fulltext.txt               # 全文备份
└── metadata.json              # 元数据
```

---

## 🔍 Tier 2 HTML 质量审查（强制规则）

> ⛔ **Tier 2 HTML 写入磁盘后，LLM 必须执行以下 6 项审查。任何一项不通过 → 修复后重新审查。**

### 审查清单

#### ✅ 1. 内容齐全性检查 (15 字段)

| 字段 | 检查要点 |
|------|----------|
| ① 基本信息 | 标题/作者/期刊/DOI/PMID/数据 accession 六要素齐全 |
| ② 关键词 | 8-10 个 badge，覆盖方法/组织/方向 |
| ③ 研究背景 | 科学问题 + 填补空白，≥3 句 |
| ④ 研究假设 | 2-4 条具体假设 |
| ⑤ 实验设计 | 受试者数/分组/方案/采样时间点/技术平台，表格形式 |
| ⑥ 方法管线 | 步骤→工具→参数，≥5 行的完整表格 |
| ⑦ 技术路线图 | Mermaid SVG 嵌入，必须有，不可跳过 |
| ⑧ 核心发现 | 5-8 条，每条含证据+数据+意义 |
| ⑨ 图表解读 | PDF 中每张 Figure 都有解读，不可只列图不加解读 |
| ⑩ 讨论 | 5-6 条关键讨论点 |
| ⑪ 局限性 | 局限→影响表格，≥3 条 |
| ⑫ 研究意义 | 科学意义 + 转化意义 |
| ⑬ 与你的关联 | 关联点 + 可借鉴 + 操作建议，≥3 条 |
| ⑭ 参考文献 | 主要引用列表，≥5 篇 |

**判定**：任一项为空或明显敷衍（如只写"待补充"），→ ❌ 不通过。

---

#### ✅ 2. 图表完整性检查（重点！）

**规则**：
- 🔥 **除非 PDF 中确实没有任何 Figure，否则必须把所有 Figure 嵌入 HTML**
- 🔥 **必须是整张 Figure 截取，不是把一张 Figure 拆成多张小图拼凑**
- 每张 Figure 必须附带：Figure 编号 + 原标题 (caption) + 解读 (2-4 句)
- Figure 根数 = PDF 中实际 Figure 数（或 ≥ min(实际数, 5) 张）

**检查方法**：
```
1. 检查 <img> 标签数量
2. 对比 run.py 提取的 figures/ 目录中的图片数
3. 如果 <img> 数 < figures/ 中的图片数 → ❌ 偷懒了，不漏图
```

**判定**：
| 情况 | 判定 |
|------|------|
| PDF 有 Figure，HTML 中 0 张图 | ❌ 严重偷懒 |
| PDF 有 N 张 Figure，HTML 中 < N 张 | ❌ 未全部展示 (除非 N>8 可精选前 8 张) |
| PDF 有 Figure，HTML 全部展示 | ✅ 通过 |
| PDF 确实是纯文字无图 | ✅ 通过（但需在 HTML 中注明"原文献不含图表"） |

---

#### ✅ 3. 结论深度检查（防敷衍）

**规则**：每个模块的结论必须 ≥ 这句话的深度，否则视为敷衍。

**检查方法**：逐模块扫描，如果结论是以下模式 → ❌ 不通过

| 敷衍模式 | 示例 | 判定 |
|----------|------|------|
| 一句话概括 | "本文研究了运动对肌肉的影响" | ❌ |
| 重复标题 | "核心发现1: PPARδ 调控回路" 不加解释 | ❌ |
| 无数据支撑 | "运动改变了基因表达" 无具体基因/数值 | ❌ |
| 照搬摘要 | 直接把 PDF 摘要拆成几段 | ❌ |
| 只有图没有解读 | 贴了 Figure 但解读栏空白 | ❌ |

**合格标准**：
- 核心发现每条 ≥4 句（发现+证据+方法+意义）
- 讨论每条 ≥3 句
- 图表解读每条 ≥2 句

---

#### ✅ 4. Figure 截取规则（整张优先）

**规则**：
- 🔥 **截取单位是「整张 Figure」，不是 Figure 内部的 panel**
- 例如 Fig 1 有 panel A/B/C/D → 截取整张 Fig 1，而不是单独截 A、B、C、D
- 如果 PDF 中 Fig 1 占了 2 页 → 截取 2 张，标注 Fig 1 (part 1/2) 和 Fig 1 (part 2/2)

**禁止行为**：
| 禁止 | 原因 |
|------|------|
| 把 Fig 1 的 A/B/C/D 拆成 4 张独立图 | 破坏原文逻辑，读者无法对照原图的 panel 标注 |
| 用 Figure Legend 文字替代图片 | 文字不能替代视觉信息 |
| 只截图表不截标题 | 读者不知道这是原文的哪张图 |

---

#### ✅ 5. 防偷懒检查

**规则**：以下行为视为偷懒，一律 ❌ 不通过。

| 偷懒行为 | 说明 |
|----------|------|
| 用文字描述替代图表 | "图 1 展示了 UMAP..." — 没贴图 |
| Tier 2 直接复用 Tier 1 的简短内容 | 把 Tier 1 的 2 句总结搬进 Tier 2 的详细字段 |
| 方法管线只有工具名无参数 | "聚类: Seurat" — 缺版本/参数 |
| 参考文献只列 1-2 篇 | 敷衍了事 |
| HTML 文件 < 15KB | 内容太少，可能大面积空白 |
| 技术路线图缺失 | Mermaid 图是 Tier 2 必出项 |

---

#### ✅ 6. HTML 技术检查

| 检查项 | 标准 |
|--------|------|
| `<html>/<head>/<body>` 完整闭合 | ✅ |
| `<title>` 非空 | ✅ |
| 暗色主题 (bg `#0f172a`) | ✅ |
| 响应式 viewport meta | ✅ |
| 所有 `<img>` 的 `src` 路径存在 | ✅ 用 read_file 确认文件存在 |
| 文件大小 ≥ 25KB | ✅ |

---

### 审查流程图

```
Tier 2 HTML 写入磁盘
        │
        ▼
  ┌──────────────────────────────────────────┐
  │ 1. 内容齐全性 (15字段全覆盖)               │
  │    ↓ 通过                                 │
  │ 2. 图表完整性 (N张Figure全嵌入)            │
  │    ↓ 通过                                 │
  │ 3. 结论深度 (每模块≥2-4句+数据支撑)        │
  │    ↓ 通过                                 │
  │ 4. Figure截取 (整张优先，不拆panel)         │
  │    ↓ 通过                                 │
  │ 5. 防偷懒 (无文字替图/无空白字段/≥25KB)     │
  │    ↓ 通过                                 │
  │ 6. HTML技术检查 (闭合/暗色/响应式/图片路径)  │
  │    ↓ 通过                                 │
  └──────────────────────────────────────────┘
        │
        ▼
   ✅ 审查通过 → 告知用户文件路径
```

### 审查不通过处理

```
❌ 第N项不通过
  → LLM 修复该问题
  → 重新生成 HTML
  → 重新执行全部 6 项审查
  → 最多重试 2 次
  → 第 3 次仍不通过 → 告知用户具体哪项不通过，让用户决定是否接受
```

---

## 🔧 run.py 工具

`scripts/run.py` 是本 skill 的核心执行工具。提供两种模式：

### Tier 1 提取
```bash
python scripts/run.py extract --tier1 --pdf {pdf_path} --out {results_dir}
```
输出：
- `fulltext.txt` — 全文文本
- `figures/` — 1-3 张关键图表 (PNG)
- `metadata.json` — 标题/作者/DOI 等

### Tier 2 提取
```bash
python scripts/run.py extract --tier2 --pdf {pdf_path} --out {results_dir}
```
输出：
- 全部 Figures + Captions
- 完整全文文本
- 结构化 metadata

---

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `tier` | `1` (default) | Tier 1 (in-chat) or Tier 2 (HTML) |
| `pdf` | required | PDF 文件路径或 URL |
| `extract_all_figures` | `false` (tier1), `true` (tier2) | 是否提取全部图表 |

---

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| PDF 文本提取为空 | PDF 为扫描版/图片格式 | 使用 OCR 兜底 (pytesseract) |
| Mermaid 渲染失败 | 语法规格不兼容 | 降级为纯 HTML+CSS 流程图 |
| 图表提取为空白 | PDF 主图多为矢量嵌入 | 正常，用 Figure Legends 文字解读替代 |
| rail_review(post) 误报 | 本 skill 是知识工作管线 | 检查实际交付物通过即可 |
| markitdown 未安装 | 缺包 | `pip install markitdown pymupdf` |
| .caj 文件打不开 (二进制) | CNKI CAJ/KDH 专有格式 | 见 `references/caj-kdh-conversion.md` — 用 caj2pdf 解密后 pymupdf 读取 |

---

## 📄 Non-PDF Input Formats

### CAJ/KDH (CNKI 知网专利/论文)

CNKI `.caj` 文件内部是加密的 KDH 格式。转换方法详见 `references/caj-kdh-conversion.md`。

**快速步骤：**
1. `git clone https://github.com/caj2pdf/caj2pdf.git`
2. Python 端用 `KDH_PASSPHRASE` XOR 解密（跳过 254 字节头）
3. 解密后数据可直接用 pymupdf 打开（无需 mutool！.tmp 文件就是有效 PDF）

### 专利文档解读模式（Patent Mode）

当输入为**专利文献**（CNKI .caj 专利文件）时，Tier 1 输出模板调整如下：

**① 专利基本信息表**
```
| 字段 | 内容 |
|------|------|
| 专利名称 | ... |
| 申请人/专利权人 | ... |
| 专利号 | CNxxxxxxA/B |
| 申请日/授权日 | ... |
| IPC分类号 | G16B... |
| 法律状态 | 审中/已授权 |
```

**② 技术领域与解决的问题** (专利说明书"背景技术"段)

**③ 🔥 技术路线图** (Mermaid Flowchart TD — 必须展示 S1→S2→... 步骤流)

**④ 权利要求分析表** (核心！)
```
| 权项 | 保护内容 | 对你是否构成障碍 |
|------|---------|:---:|
| 权1 | ... | ⚠️/✅ |
```

**⑤ 创新点与差异化空间**

**⑥ 与你的专利策略关联** — 含规避建议 + 可借鉴要素

---

## References

- `references/15_fields_template.md` — HTML 报告模板 + 格式约定
- `references/caj-kdh-conversion.md` — CNKI CAJ/KDH 格式转换完整方法
- `scripts/run.py` — PDF 提取工具 (文本+图表+元数据)
- `templates/report_template.html` — HTML 报告 Jinja2 模板 (Tier 2)
