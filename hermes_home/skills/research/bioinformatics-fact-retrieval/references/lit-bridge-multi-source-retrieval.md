# lit_bridge.py 多源文献检索（无 MCP CLI 桥）—— 配方与实测

> 2026-09-25 实测沉淀。适用场景：用户说「多源检索 XX 文献，PubMed / Crossref 各 N 篇，附 DOI，只要清单」。
> 本文件是本 skill 的**检索执行层**（怎么把清单真的取回来）；事实核查纪律见 SKILL.md 正文。

## 1. 这是什么 / 在哪

`nature-academic-search` skill 上游把检索包在 `mcp-server/`（MCP 协议 + requests/defusedxml/toml/pybliometrics），
MemOmics 进程里没有 MCP 客户端 ⇒ 工具名调不到。仓库自带 CLI 桥把它重写成标准库实现（零 pip 依赖、零 API key）：

```
E:/MemOmics-Agent/hermes_home/skills/bioinformatics/nature-academic-search/scripts/lit_bridge.py
```

四个子命令：`search <query>` / `paper <id>` / `cite <id>`（APA / GB-T 7714 / BibTeX / RIS）/ `mesh <term>`。
`search` 支持 `--sources pubmed,crossref,arxiv,openalex`、`--limit N`、`--year-from`、`--json`。

## 2. 调用模板（Windows / MSYS）

```bash
cd /e/MemOmics-Agent
export HTTP_PROXY=http://127.0.0.1:6478 && export HTTPS_PROXY=http://127.0.0.1:6478   # 本机出口需代理
S=hermes_home/skills/bioinformatics/nature-academic-search/scripts/lit_bridge.py
.venv/Scripts/python.exe "$S" search "<query>" --sources pubmed --limit 8 --json
```

- 退出码：`0` = 至少一源返回结果；`2` = 全部源失败/无结果。**单源失败不影响其它源**，错误逐源收集在 `errors` 字段。
- 只读检索**不落任何文件**（用户常明确要求）；要落盘才落，落盘也进 `results/<sid>/`。

## 3. JSON schema（🔴 先看这条，别猜）

顶层键固定 5 个：

```json
{"query": "...", "count": 8, "sources_used": ["pubmed"], "errors": [], "records": [ {...}, ... ]}
```

**结果数组的键是 `records`，不是 `results`。** 每条 record：`source / pmid / doi / title / authors[] / year / venue / volume / issue / pages / url / citations / type`。

⛔ **踩过的坑**：我只看到 `tail -c 6000` 的片段（末尾是条目 JSON + `}`），凭直觉写成 `d.get("results")` → 解析后**零输出且不报错**（`json.load` 成功、键不存在、循环不执行），白烧一轮。**正确做法是一次调用内自适应探测**：

```python
d = json.loads(raw)
print("TOPKEYS:", list(d.keys()))          # ← 先打印键名，再写解析
for p, lst in walk(d): ...                 # walk() 递归找出所有 dict-list
```

同族纪律：**别用被截断的回执片段推断 schema**——先打印顶层键，一次就定。

## 4. Crossref 检索式策略（🔴 与 PubMed 的查询写法不同）

| 事实（2026-09-25 实测） | 证据 |
|---|---|
| Crossref 对「一组并列名词」的**字面短语匹配很弱** | 检索式 `skeletal muscle aging single-cell RNA sequencing` + `--limit 3` → **仅 2 条**，且都是 *Innovation in Aging* 会议摘要（`10.1093/geroni/igaf122.*`） |
| 换成领域惯用词后命中数翻数倍 | `skeletal muscle aging single-cell transcriptomics` → **9 条**；`human skeletal muscle aging single-nucleus atlas` → **6 条**（同批里出现高质量 journal-article、综述、预印本） |
| Crossref **混入非正式类型** | 实测同批含 `book-chapter`（2019 Single-Cell Omics 书籍章节）、`posted-content`（bioRxiv 预印本）、`peer-review`（`10.1111/febs.70659/v1/review1` 审稿意见）、`grant`（`10.55762/...pc.gr...`）——**交付前必须按 `type` 过滤或标注** |
| Crossref 条目**无 PMID** | `pmid` 字段为 `-`；要 PMID 就回 PubMed 侧或被引文献的 EuropePMC 反查 |

**可复用套路**：Crossref 侧不要只跑一条检索式——用 2 条**领域术语变体**（`single-cell transcriptomics` / `single-nucleus atlas` / `snRNA-seq` / `scRNA-seq`）各跑一次，再跨源去重、按 `type` 过滤，最后挑主题最贴合的 N 篇。若首版命中 < N，**换检索式重跑比调 `--limit` 有效**。

## 5. 只读检索的交付口径（用户偏好，2026-09-25 确认）

用户原话：「**附 DOI，只要清单；不用再问，需要 terminal 就直接跑 … 不做分析、不入库、不生成文件**」。

- ✅ 交付 = **Markdown 管道表格**（铁律 29）：标题 / 期刊或平台 / 年 / DOI（PubMed 侧再附 PMID）/ 类型；正文列出**实际检索式 + 命中数**。
- ✅ **失败源照实报**（哪源失败、报什么错、有没有替代通道），不要静默吞掉或编造条目。
- ✅ 交叉源重复时**标注重复**（例：`10.1186/s13395-020-00236-3` 两源都命中）或换一篇拉高不重复率。
- ⛔ **不落文件**（不导出 .bib/.ris）、**不入库**（不 `save_reference` / `save_knowledge`）、**不跑分析**、**不建 task_plan**。
- ⛔ **不要弹意图确认表单、不要追问「要不要顺带导出/入库」**——用户已经在上一轮为此重复发了一遍请求。
  「高代价任务」门禁（铁律 35）覆盖的是真实分析/集群投递/入库/出报告，**只读文献检索不在其中**；用户说「不用再问」就一个字都别问。
- ⛔ **不强行辩论**：清单类议题无候选参数 ⇒ L0 跳过（详见 `platform-execution-pitfalls` 使用要点 §13）。
- ⛔ **不为通过 rail_review(post) 而制造产物**：审查器按分析级标准判（代码过短/必须有图），与只读口径天然不匹配，如实说明即可（同上 §13）。

## 6. 本次实测证据（2026-09-25）

主题：骨骼肌衰老 × 单细胞。

| 源 | 检索式 | 命中 | 交付选取 |
|---|---|---|---|
| PubMed | `skeletal muscle aging single-cell RNA sequencing`（`--limit 8`） | 8 | `10.1038/s43587-022-00250-8`（Nature Aging 2022，PMID 36147777）/ `10.1093/procel/pwac061`（Protein & Cell 2023，PMID 36921027）/ `10.1038/s43587-024-00756-3`（Nature Aging 2024，PMID 39578558） |
| Crossref | `skeletal muscle aging single-cell transcriptomics` | 9 | `10.14336/ad.2025.0701`（Aging and Disease 2025 综述）/ `10.1101/2025.07.28.667277`（bioRxiv SkeletAge 预印本） |
| Crossref | `human skeletal muscle aging single-nucleus atlas` | 6 | `10.1093/geroni/igaf122.235`（Innovation in Aging 2025，会议摘要，需标注类型） |

两源均连通，无失败源。PubMed `--limit 3` 时返回的是 *J Cachexia Sarcopenia Muscle* 三篇相关性偏低条目 ⇒ **要选主题最贴合者，取 `--limit 8~10` 再人工挑，不要只看前 3 条**。

## 7. 把 JSON 变成清单：不要用 `tail`（2026-09-25 二次实测）

`tail -c 5000` 看 `--json` 输出是**从尾部截断**——头部 `query / count / sources_used` 与靠前记录先被切掉，回执看着"就这些"，实则清单少项、命中数也报不出来（本次 PubMed 首跑 tail 后只剩 7 条、`count` 完全看不到）。

正确写法：管道进 python 打印精简字段，一次拿全。git-bash 下多行 `-c` 用 **ANSI-C 引用 `$'…\n…'`**（免嵌套转义引号，也避开 heredoc 被守卫误读）：

```bash
cd /e/MemOmics-Agent
export HTTP_PROXY=http://127.0.0.1:6478 && export HTTPS_PROXY=http://127.0.0.1:6478
S=hermes_home/skills/bioinformatics/nature-academic-search/scripts/lit_bridge.py
P=.venv/Scripts/python.exe
for src in pubmed crossref; do
  echo "=== $src ==="
  $P "$S" search "skeletal muscle aging single-cell RNA sequencing" --sources $src --limit 8 --json 2>/dev/null \
  | $P -c $'import sys,json\nd=json.load(sys.stdin)\nprint("count=",d.get("count"),"errors=",d.get("errors"))\nfor r in (d.get("records") or []):\n    print("-",r.get("year"),"|",(r.get("venue") or "")[:36],"|",(r.get("title") or "")[:92],"|",r.get("doi"),"|",r.get("pmid"),"|",r.get("type"))'
done
```

要点：① 两源**一次循环跑完**（同一 terminal 调用，别一源一轮）；② `count` + `errors` 必须打印——这就是"命中数"和"失败源照实报"的证据；③ 字段一律 `.get()` + 截断，避免 `None` / 超长标题炸输出。

## 8. 二次实测补录（2026-09-25，同主题同式）

| 源 | 检索式 | 命中 | 说明 |
|---|---|---|---|
| PubMed | 同 §6 | 8 | 元数据完整（含 PMID / 卷期页），`errors` 空 |
| Crossref | **字面长句同式** | **6** | 与 §4 结论一致：字面式命中少且脏 —— 3 条不切题（鸡骨骼肌**发育**补充材料 `component` 且 `year=None`、骨骼肌**发育**综述 `10.1016/j.biopha.2023.114631`、**卒中 microglia** `10.14336/ad.2026.0803`），仅 3 条切题（两篇 `igaf122.*` 会议摘要 + Nature Aging 评论 `10.1038/s43587-024-00629-9`） |

⇒ **Crossref 交付前必须逐条按标题切题度筛**（不止按 `type`）：`component` 没有 `year`、且常属**别的物种 / 别的发育阶段**；清单里写明"命中 6 条、取最贴合 3 条"，并在源状态说明里把被剔除条目的 DOI 点名列出来——让用户看得到剔除动作。
⇒ 反面教训：本次若用 `tail` 解读，会连"Crossref 到底命中几条"都说不准，只能给出一个看似完整实则截断的表。