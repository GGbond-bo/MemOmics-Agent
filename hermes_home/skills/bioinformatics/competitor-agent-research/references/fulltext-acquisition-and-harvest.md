# 全文获取阶梯 · 批量收割 · 筛选漏斗记账

> 来源：2026-10-02 会话（科研 AI agent 领域全景，6,079 → 734 → 45 → 31 篇）。
> 本文件管**拿到文本**这一段（模式 B 的前置步骤）；把文本读成竞品卡见模式 C / C7。

---

## 1. 全文获取阶梯（按顺序试，拿到就走）

| 阶 | 手段 | 实测结果（2026-10-02，45 篇） | 适用 |
|---|---|---|---|
| 1 | `download_pdf(url_or_pmid=DOI, doi=DOI)` | 出版社允许直连的能成功（本次 BioMaster / ChemGraph / CASSIA / DeepRare / ChemCrow 共 5 篇） | 先试，成本最低 |
| 2 | **Europe PMC fullTextXML**<br/>`https://www.ebi.ac.uk/europepmc/webservices/rest/PMC{pmcid}/fullTextXML` | **31/45 成功** —— 本次主力通道，EBI 主机未被拦 | **有 PMCID 就用它**；对精读比 PDF 更好（纯文本、可逐字 grep、可按字符区间切片） |
| 3 | PMC-OA `https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=PMC{id}` → 取 `format="pdf"` 的 `href`，`ftp://`→`https://` 再拉 | 本次多次 HTTPError | 仅在有 PMCID 且阶 2 拿不到时试 |
| 4 | 出版商 PDF 直连（如 `nature.com/articles/<id>.pdf`） | 被 Cloudflare JS 校验页拦截（返回 ~1816B HTML） | 期望值低，试一轮就走 |
| 5 | 只剩摘要 | 11/45（Nature 新闻/评论类、预印本，无 PMC） | 如实标「仅摘要」，**不要假装读全文** |

**判据与纪律**
- 拿到 200 但 `b[:4] != b"%PDF"` 或 `len(b) < 20000` → 判定失败，**换下一阶，不要原地重试同一 URL**。
- 下载成功即缓存到 `data/fulltext/PMC{id}.xml`；重跑先查缓存（`os.path.exists` + `size > 5000` 直接复用）。
- **一次脚本跑完所有篇目**（循环 + `time.sleep(0.4)`），不要一篇一次工具调用。
- 最终**必须如实报三个数**：拿到全文几篇 / 只拿 PDF 几篇 / 只有摘要几篇。
  本次 31 全文 + 5 PDF + 11 摘要，**这三个数字都要进交付文档的 Limitations**（审稿人会问覆盖率）。

---

## 2. 批量收割的检索式设计（避免 "agent" 撞 "治疗剂"）

宽 OR 查询（`agent OR agentic OR autonomous …`）会把 **therapeutic agent / contrast agent /
antimicrobial agent** 这类化学词一起捞进来（本次初版 6,079 条里高被引前排全是无关综述与医学 LLM 综述）。

**两步式，别一步到位：**

```python
# 第 1 步：宽召回（宁可多）
wide_q = ('("AI scientist" OR "co-scientist" OR agentic OR "multi-agent" '
          'OR "autonomous discovery" OR "self-driving lab" OR "LLM agent")')

# 第 2 步：硬门在本地做，不要靠把查询写得更长
HARD = re.compile(r"(ai scientist|co-?scientist|autonomous (ai|agent|scientific|discovery)|"
                  r"agentic (ai|workflow|system|framework|bioinformatics)|"
                  r"multi-?agent (system|framework|llm|large)|self-?driving lab|"
                  r"automated (scientific )?discovery|lab automation|"
                  r"large language model agent|llm[- ]based agent)", re.I)
CLIN = re.compile(r"(patient|clinical decision support|counsel|nurs|medical education|"
                  r"physician|hospital|mental health|nutrition coach|population health)", re.I)
SCI  = re.compile(r"(discovery|bioinformatic|omics|transcriptom|genom|chemistry|materials|"
                  r"protein|drug|hypothesis|scientific|research|robot|lab)", re.I)
```

**加权打分**（把有量化成绩/顶刊/高被引的排前，同时压掉临床服务类）：

```
score = 硬词命中(标题 +6 / 正文 +3) + 科学域词 +2 − 临床服务类 −4
        + min(cites, 400)/100 + 顶刊期刊名 +1.5
```

**地标强制纳入（关键）**：把必须收录的系统名做成 `(正则, 标签)` 列表逐条置顶，
否则纯打分会让关键系统掉出必读清单。本次 18 条：
`co-scientist | ai scientist | biomni | agentomics | biomaster | chemgraph | cassia |
mcp-native | genegenie | bioinformatics | spatial omics | materials | chemical kinetics |
earth science | drug discovery | hypothesis`。

**期刊字段**：部分源 `journal` 为空 → 写「未标注」，**不要留空列**（用户会问）。

⚠️ 地标匹配要**核对命中对象**：本次「co-scientist」正则先命中了
*A multi-agent system for automating scientific discovery*（其实是 **Robin**，FutureHouse），
真正的 Co-Scientist 是另一篇。**打完标签后回读标题确认，别把 A 的名字挂在 B 的卡上。**

---

## 3. 筛选漏斗要记账并写进交付

```
原始命中 6,079  →  硬门过滤后的核心集 734  →  必读精选 45  →  拿到全文 31
```

- 每一档的数量 + 过滤口径（正则 / 打分公式 / 人工复核）都要写进报告「检索与筛选方法」一节，
  **并声明精度控制手段**——否则会被质疑"宽 OR 捞进来一堆噪声也当证据用"。
- 主题分桶若用关键词正则，**显式自曝**「关键词正则，非人工标注，存在交叠与漏判」。
- 单篇 PDF 成功数与**通道被拦的事实**同样进 Limitations（本次 5/45）。

---

## 4. 与其它部分的接口

| 需要什么 | 去哪 |
|---|---|
| 文本 → 结构化竞品卡 | 模式 C，**尤其 C7（脚本预抽"含数字的结果句" + `<aff>` 机构，主代理落卡）** |
| 缺口论证 / 发文定位 | 模式 D + `references/gap-claim-and-positioning.md` |
| 引用库沉淀 | `save_reference(action="add", global_lib=true, ...)`；多篇可用脚本从元数据直接生成 `.bib` 更快，最后 `save_reference(action="export")` 确认路径 |
| 本地 PDF 入库 | `literature_import(paths=[...])`（自动标识期刊/DOI/年份并去重），**不要重复下载** |