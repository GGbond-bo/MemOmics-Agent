# 论文全文 → 汇报材料（大纲优先，2026-09-25 实测）

覆盖「把一篇论文做成组会/文献汇报材料」这一类任务的**取全**与**交付**两端：
先把 OA 全文拿到手（避免只凭摘要编大纲），再按用户口径交付（大纲优先 / 零文件）。

实证样本：Lai et al., *Multivariate cell atlas of the ageing human skeletal muscle* 实为
**Multimodal cell atlas of the ageing human skeletal muscle**, *Nature* 2024;629(8010):174–183
（DOI 10.1038/s41586-024-07348-6，PMID 38649488，PMCID PMC11062927，OA）→ 14 页资源型大纲。

---

## 1. 全文获取链（DOI → 可读全文）

按序执行，每步都便宜且可核实：

| 步 | 动作 | 拿到什么 |
|---|---|---|
| 0 | `search_files` 查 `hermes_home/papers/` 是否有该 PDF | 命中就别重复下载/导入 |
| 1 | `curl -s https://api.crossref.org/works/<DOI>` | 标题 / 期刊 / 年 / 完整作者表 / `type` |
| 2 | `query_ncbi(db='pubmed', query='<DOI>')` | PMID（引用行用） |
| 3 | Europe PMC core：`https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%22<DOI>%22&resultType=core&format=json` | `pmcid` / `isOpenAccess` / `inEPMC` / `hasSuppl` |
| 4 | `https://www.ebi.ac.uk/europepmc/webservices/rest/<PMCID>/fullTextXML` | 全文 XML（含全部图注 + Methods） |

失败分支：非 OA / 不在 EPMC → `download_pdf` → PDF 文本提取；Nature/Science/Cell 系 PDF 抓取失败 →
走本技能 §2 的 **Nature HTML fallback**（见 `references/nature-html-extraction.md`）。
XML 偶发 HTTP 500 → 重试 1-2 次，仍失败则如实说明「未核全文」，**不得用摘要补编数字**。

未拿到全文时，明确告诉用户只能按摘要级内容出大纲并标出缺口——**不要为了「大纲看起来完整」而编造
细胞数、百分比、图号或 panel 字母**。

## 2. XML 解析：两遍覆盖一次做完

```python
import re, xml.etree.ElementTree as ET
root = ET.parse(path).getroot()
txt = lambda e: re.sub(r'\s+', ' ', ''.join(e.itertext())).strip()

# ① 全部图注（含 a/b/c 分图字母）——直接就是可用的 slide 要点素材
for fig in root.iter('fig'):
    lab = fig.find('label'); cap = fig.find('caption')
    print('===', txt(lab) if lab is not None else '?')
    print(txt(cap)[:900] if cap is not None else '')

# ② 正文：先打印所有 <title> 建白名单，再按白名单取段落
for m in re.finditer(r'<title>(.*?)</title>', x, re.S): print(re.sub('<[^>]+>','',m.group(1)).strip())
```

要点：
- `<sec>` 里**混着全部 Methods 子节**，所以白名单必须先由 ① 的标题清单筛出来（Abstract/Main/
  Discussion + 本文各结果子节标题），否则会把 Methods 也灌进汇报用文本。
- 正文落盘后用 `read_file` 的 `offset`/`limit` 分段读（通常 30–60 KB），**不要整段进上下文**。
- **一次提取覆盖章节 + 全部图注即可**，不要再为「补一张 Extended Data 图」发起后续查询——材料已足够后
  继续查询会被平台判为**循环失控**并强制干预（见 SKILL.md Pitfalls 同名行）。

## 3. 大纲输出形状（每页四件套）

先前置一行说明判定出的 paper_type（用户纠正成本最低），再逐页给：

1. **结论式中文标题**——写论断，不写「结果一」「数据展示」这类主题标签。
2. **2–4 条要点**，每条带论文自己的数字：n、细胞/核数、百分比（前→后）、peak/基因数、基因符号、
   P/Q 阈值、年龄分层、亚群名。
3. **指定配图**：写到 `Fig. 3a` / `Extended Data Fig. 6c` 这一级，后续出 deck 时是机械照做。
4. **一句 takeaway / 口头讲点**——讲者真正说出口的那句话。

本用户（组会场景）额外期待的几件事：
- 留一页 **hero figure**（主图谱）：图占满页、文字 ≤2 行，讲者停留 ~60 秒不解读。
- 流程页给**整页横向图**，并**直接交付可粘贴的 Mermaid**，节点文本里嵌参数与数字。
- 标出哪几页信息密度高，并写明「哪些内容下沉到备注」。
- 末尾加一节 **「与本组工作的关联」**：① 哪些方法可直接借用 ② 哪些结果可作假设来源
  ③ 它验证/冲突了本组数据的哪一点。这是组会上真正会被追问的部分。
- 收尾给 **可用性（门户 URL / accession）→ 局限（作者自陈）→ 2–3 个备用提问**（Q&A 用）。

## 4. 交付纪律（用户说「不要生成文件」时）

- 触发语：只要大纲 / 只要每页要点 / 先给大纲我看 / 不要生成文件 / outline first。
- **不建 .pptx、不写报告文件、不导出**；`generate_report`/`add_to_report` 一类产物工具不要调用。
- 中间解析产物（XML、正文 txt）可以有，但：**不放进交付路径**（`output/`、`results/<sid>/reports/`），
  放会话 `data/` 或临时目录，并在结尾用一行说明「非交付物」；口径严格时直接在内存里解析或事后清理。
- 收尾一句话给出「确认后出 deck」的参数（页数、要裁哪几张图、中文备注），让下一轮只需一句确认。

## 5. 与 nature-paper2ppt 的交接

`nature-paper2ppt`（非 agent 创建，勿改）负责**真正生成 pptx**；本文件负责它前面的**取全 + 出大纲**。
交接时把大纲里的每页四件套直接映射到它的 Step 3–6（plan → figure selection → slide content），
paper_type 判定与叙事弧沿用（resource → workflow-to-validation，discovery → question-to-evidence 等）。