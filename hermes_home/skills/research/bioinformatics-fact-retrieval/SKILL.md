---
name: "bioinformatics-fact-retrieval"
description: "从官方文档与文献中获取并核实生信事实（方法对比、PMID/DOI 核验、docs 404 兜底链、摘要锚定）"
when_to_use: "[bioinformatics-fact-retrieval] 需要调研/对比生信方法并引用真实文献（PMID/DOI）或官方文档时；官方文档页面 404 或需要源文件（vignette Rmd/函数签名）时；需要把性能/结论声明锚定到论文摘要原文（防编造）时；**用户给一句结论要「找引用/看看能引哪几篇」（论断→引用匹配 + 支撑分级）时**；文献检索工具漏检需要兜底时；用户要「多源检索，PubMed/Crossref 各 N 篇，附 DOI，只要清单」这类只读清单式检索时（走 lit_bridge.py，见 §1 步 4-5）；需要拿到某篇论文的**开放获取全文**（要论文里的真实细胞数/百分比/图注来出组会汇报大纲，而不只是摘要）时（见 §1 步 7 + `references/paper-fulltext-to-deliverable-material.md`）；**用户要「怎么跟合作方说 / 给我中英文说辞 / 也算是给他的解释」时**（见 §5 交付形态：中英各一版、各 ≤3 点、不堆图表文献，短版优先）；**涉及反义 lncRNA / 重叠基因座的 read 归属（\"how can we distinguish A vs A-AS1 reads\"）时**（见 §1.5 步 5-7）；**用户带一个来自别处的心智模型来求确认（「2500 篇论文整理出来的东西是不是就是它的 skill？」「我用过它，它就是先触发 skill 再调工具，对吧？」）时**（见 §2.7，先核原文再表态，⛔ 不许顺着点头）"
display-name: "Bioinformatics Fact Retrieval & Verification"
category: research
short-description: "Retrieve and verify bioinformatics facts from official docs and literature with fallback chains, real PMIDs/DOIs, and abstract-grounded claims."
---

# Bioinformatics Fact Retrieval（生信事实检索与核实）

调研类任务（方法对比、工具选型、文献支撑）的事实获取与核实规程。核心原则：**所有事实必须来自真实查询（官网文档、GitHub 源文件、PubMed/EuropePMC），不能凭记忆编造；拿不到就标注推断或缺失**。

## When to Use
- 方法/工具对比调研（如 Seurat vs Scanpy 批次整合），需要引用真实 PMID/DOI
- 官方文档页面 404，或需要比渲染网页更权威的源文件（vignette Rmd、函数签名、docstring）
- 需要把性能/结论声明锚定到论文摘要原文（例：Harmony 摘要 "~10^6 cells on a personal computer"）
- 文献检索工具漏检时需要兜底通道

### 🔴 第一判据：要文献就检索文献，别先去探本地（2026-09-26 用户严厉纠正）

**用户原话**：「我要你去网上找 DEG 的方法呀，文章，mast，什么鬼呀你」——触发场景：用户问「哪个 DEG
方法更适合我们 / 运动转录组用什么方法」，我却先花了多轮做**本地探测**（`ls` 数据目录、`readRDS` 本地 rds、
`check_env` 查包、试装包、拷文件到英文路径），迟迟没去检索文献。

**判据（回答前先分类）**：

| 用户说法 | 任务性质 | 第一个动作 | 交付物 |
|---|---|---|---|
| 「哪个方法更适合 / 有文章这么做吗 / 为什么用这个 / 去找 XX 的方法文献」 | **方法选型（调研）** | **文献检索**（§1 链路） | 文献清单 + PMID/DOI + 结论口径 |
| 「帮我跑 XX 分析 / 用这个方法跑我的数据」 | 执行 | 探数据 + 环境 + 跑 | 结果表 + 图 |

**规则**：方法选型问题里，本地的数据/环境信息只作**参数背景**（物种、组织、设计、样本量），
**排在文献之后**；⛔ 不要用 `ls` / `check_env` / 试装包刷轮次 —— 既不改结论，又会累计触发循环检测。
⚠️ 例外：执行类任务里**缺包/缺数据**必须查（那是真阻塞）；调研类任务里它们不是阻塞。
**自检句式**：如果这一轮的动作不产出 PMID/DOI/官方文档链接，那它在调研任务里就是在跑偏。

## Workflow（按序执行）

### 1. 文献检索链（防漏检）
1. `search_papers(关键词)` — 混合 Europe PMC/Semantic Scholar，**会漏检**（例：BBKNN 论文关键词搜索未命中）
2. 漏检 → `query_ncbi(db='pubmed', query='<论文精确标题>')` 直查（例：BBKNN 靠此拿到 PMID 31400197）
3. 摘要核实/锚定声明 → Europe PMC REST：
   `https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:<PMID>&resultType=core&format=json`（取 `abstractText` 字段，用于引用性能/结论数字）
4. **多源清单式检索（用户要「PubMed / Crossref 各 N 篇，附 DOI，只要清单」）→ 走仓库自带的 CLI 桥 `lit_bridge.py`**（上游 MCP 服务在本平台不可达，这个桥是标准库实现、零 API key）：
   `hermes_home/skills/bioinformatics/nature-academic-search/scripts/lit_bridge.py search "<query>" --sources pubmed,crossref --limit 8 --json`
   先 `export HTTP_PROXY=http://127.0.0.1:6478 && export HTTPS_PROXY=http://127.0.0.1:6478`。**JSON 结果数组的键是 `records`**（顶层 = `query/count/sources_used/errors/records`）——⛔ 别凭被截断的回执片段猜 schema，先 `print(list(d.keys()))`；两源查询写法不同、Crossref 需换检索式并过滤 `type`，完整配方 + 实测证据见 `references/lit-bridge-multi-source-retrieval.md`
5. **只读检索的交付口径（用户已明确，2026-09-25）**：只要清单 ⇒ 输出 Markdown 表格（标题/期刊/年/DOI，PubMed 附 PMID）+ 实际检索式与命中数，**失败源照实报**；**不落文件、不入库、不跑分析、不弹意图表单、不追问「要不要导出」、不强行辩论**（清单类无候选参数 ⇒ L0 跳过）
6. **「给这个结论找引用」类请求（论断→引用匹配）**：先**拆成 2-4 个子论断**再逐条配文献 + **保守支撑分级**（strong/partial/background/limiting/metadata-only）；综述只作 context；某半句查不到摘要级原始证据 ⇒ **如实报缺口并建议改写措辞**，不得用"标题相关"凑数。`search_papers`/`query_ncbi` **都不回摘要**，定级前必须用 §1-步3 的 Europe PMC `resultType=core` 批量取 `abstractText`。完整流程、批量模板、接口坑、可复用工作示例（卫星细胞衰老论断 7 篇）见 `references/claim-to-citation-support-grading.md`

7. **开放获取全文获取链（要给论文里的真实数字/图注、而非摘要时）→ DOI 直链**：① `curl -s https://api.crossref.org/works/<DOI>` 取标题/期刊/年/作者/`type`；② `query_ncbi(db='pubmed', query='<DOI>')` 取 PMID；③ Europe PMC core 检索同一 DOI 取 `pmcid`/`isOpenAccess`/`inEPMC`；④ `https://www.ebi.ac.uk/europepmc/webservices/rest/<PMCID>/fullTextXML` 取全文 XML（OA 才可用；非 OA 退回 `download_pdf` → 文本提取，Nature 系再走 §2 的 HTML 兜底）。⚠️ 先 `search_files` 查本地 `hermes_home/papers/` 是否已有该 PDF，有就别重复下载。XML 的两遍解析（`<fig>` 图注含分图字母 / `<sec>` 白名单取正文）与「全文→组会汇报大纲」的每页形状、零文件交付口径，见 `references/paper-fulltext-to-deliverable-material.md`

### 1.5 注释类事实：**源文件优先于 API 转述**（2026-10-01 用户纠正）

**用户原话**：「GRCh38 这个 gtf 文件，**你下载下来，真实查看一下**，它在这里到底代表什么」——
此前我已用 Ensembl REST / NCBI Gene / UniProt 三处 API 给过完整答复（坐标 / biotype / 链 / 产物），
用户仍要求看**文件本身**。⇒ 判据：凡问题形如「**我这份注释文件里它代表什么**」，**源文件是唯一权威**；
API 返回的是数据库视图，答不了「你手上这份 GTF 里它长什么样」。

1. **先查本机是否已有该参考文件**，再决定下不下（`ls -la <参考目录>` + **`gzip -t` 校验 CRC**：
   通过就直接复用，残缺才重下）——实测 `E:/Human_gene_reference/` 已有 GENCODE v32 GTF
   （43,107,903 B、可 zcat 统计），**无需重复下载**。
2. 未命中再走官方 FTP（GENCODE/Ensembl 的 EBI ftp 路径常年稳定）。
3. **真实打开统计**，不要 grep 一两条就下结论：行类型分布（`gene/transcript/exon` 计数）+ 目标基因的
   链与 biotype。实测 v32：`MEF2C-AS1` = **1 gene + 15 transcript + 62 exon（+ 链，lncRNA）**，
   `MEF2C` = **1 gene + 56 transcript（− 链，protein_coding）**。重叠加叠要**取 exon 区间实算交集**。
4. **GTF vs FASTA 的判据**（用户问「我需要哪个」时一句话答）：要**位置 / read 归属 / 基因座关系** →
   **只需 GTF**；只有要**真实碱基序列**（切 lncRNA 序列、设计引物、motif）才需要 FASTA（≈1 GB gz）
   ⇒ 别默认让用户下 1 GB。
5. **`-AS1` 家族先按「宿主基因的反义 lncRNA」假设，再核对坐标**：同一基因座的正义/反义配对
   （head-to-head、区间重叠）**不构成两条独立证据** —— DEG 里两者同时出现宜合并表述为
   「**X 基因座（含反义 lncRNA X-AS1）**」；区间重叠 ⇒ 重叠区 read/UMI 归属有歧义，自查 =
   两者在 pseudobulk 矩阵中的表达相关性（>0.9 ⇒ 同一信号）。

6. **染色质侧（ATAC）归属：整段不能拆，但两端能拆**（2026-10-02 实测，MEF2C / MEF2C-AS1）：
   重叠区在 ATAC 里**不是一个可归属的单位**——同一段 DNA、片段无链信息，所谓「A 的重合区 vs B 的重合区」
   物理上不存在，一个片段只有一个数；⛔ 别顺着「分别统计两个基因的重合区」这种口径答应下来。
   **但两个基因的 5′ 端若分别落在重叠区两端，重叠区就能按 TSS 拆成两个功能不同的子区间**
   （实测：MEF2C-AS1 TSS 在左界 88,883,328、MEF2C TSS 在右界 88,904,257，相距 20,930 bp）⇒
   左端 = 反义 lncRNA 启动子、**右端 = 宿主基因启动子**。据此统计「宿主基因 TSS 近端可及性 Post−Pre」，
   才答得上用户真正想问的「运动是否也影响宿主基因」。
   ⛔ 三条不可越界的推论：① **可及性 ≠ 转录**（染色质开放是必要不充分条件，只支持「该位点被重塑」）；
   ② **变化方向不可先验假定**（人骨骼肌耐力训练的 ATAC 证据是往**闭合**走：PMID 40623475，标题级核实）；
   ③ **基因边界 ≠ 在用的启动子**（MEF2C 有 56 个转录本、多个替代启动子 ⇒ 先看 ATAC 峰 / RNA 覆盖落在哪个 TSS）。
   配对结构必须按**供体配对**（同人 Pre vs Post），⛔ 不能把 Pre 组与 Post 组当独立样本比。
   ⚠️ 交付口径：**「能统计，但对象要换」比一口否定（"ATAC 无法归属"）更准确**——过度否定与过度断言
   同样会被合作方当场驳回（本轮我先说了前一句，随后必须自我修正；见 reference §2.5 的问法纠偏表）。

7. **RNA 侧「重合区 read 怎么区分」的五层判据**（2026-10-02；合作方原话 *"If we are counting them in
   the overlapping region, how can we distinguish MEF2C vs MEF2C-AS1 reads?"*）——**判据是链，而真正可能
   竞争的窗口远小于区间重叠量**，逐层收窄（可直接复用的答法）：
   | 层 | 判据 | 把窗口缩到 | 依据 |
   |---|---|---|---|
   | ① 链 | 两基因反向链 ⇒ read 按来源链归属，反义 read 不计入正义基因 | 类别上分开 | 链特异性定量；**PMID 26334759**（Zhao 2015, BMC Genomics：无链信息时**反向链重叠位点**的表达量难以甚至无法准确定量） |
   | ② 外显子 / 内含子 | 默认按外显子计数 ⇒ 内含子部分（本例 20,508 bp）不进计数 | 20,930 → **422 bp**（3 段 139/17/266，占 2.02%） | 两基因 **exon 区间实算交集**，不能只看「区间有交叠」 |
   | ③ UMI 锚点 | 3′ 化学 UMI 锚在转录本 3′ 端；本例两 3′ 端相距 ~749 kb **且都不在重叠区内**（重叠区里只有两个 5′ 端） | **→ 0** | ⚠️ 依赖建库化学：**5′ 建库逻辑反转**（两个 5′ 端恰落在重叠区两界）⇒ 未确认前只能说「3′ 情形下归零」 |
   | ④ 唯一外显子重定量 | 剔除 422 bp 共享 exon，只用各自独有 exon 重算 → 系数/显著性变不变 | 实证 | 最直接的自证（无需 BAM / 无需 ATAC） |
   | ⑤ 参数自检 + 结果独立性 | RSeQC `infer_experiment.py` 验链特异真生效；两基因 counts 是否同向同幅 | 实证 | 本例一升（AS1 最大 coef 0.81）一平（MEF2C 全部对比不显著）⇒ **反证 counts 未被混计** |
   ⛔ 两处必须自报的口径：**③ 依赖建库化学**、**④⑤ 未跑前不得声称已做**。
   ⛔ 禁止单点断言（「区间重叠 ⇒ 一定混」或「链特异 ⇒ 一定没问题」）——按上表逐层给；
   并说明该问题问的是 **read 归属 = 定量步骤 = RNA 侧**；ATAC 片段归属单位是基因组区间、无链感知的基因归属
   （ATAC 能答的是「该位点是否被重塑」，见 §1.5-6）。

> 完整实测记录（zcat 统计命令、MEF2C vs MEF2C-AS1 坐标对照表、重叠区 ATAC 归属规则与 R1–R4 区间设计、
> 术语表述纪律、PMID 36198203 / 40623475 等证据链、报告口径）
> 见 `references/annotation-file-verification-and-antisense-loci.md`。

### 2. 官方文档链（404 兜底）
1. 官网页面（satijalab.org / scanpy.readthedocs.io / docs.scvi-tools.org）
2. 页面 404 → GitHub API 列目录确认源文件存在：
   `https://api.github.com/repos/<org>/<repo>/contents/<dir>?ref=<branch>`（例：`satijalab/seurat` 的 `vignettes/` 目录，返回文件列表含 default_branch）
3. 拉源文件用 jsdelivr CDN（raw.githubusercontent.com 可能被网络屏蔽）：
   `https://cdn.jsdelivr.net/gh/<org>/<repo>@<branch>/<path>`（例：`cdn.jsdelivr.net/gh/satijalab/seurat@main/vignettes/seurat5_integration_rpca.Rmd`）
4. 版本化文档 URL 可救回部分 404（如 scanpy `en/1.9.1/...`）

### 2.5 「论文实际怎么做的」核实链：代码优先于正文（2026-09-26 实测）

用户问「某篇论文怎么就能用某方法 / 别人怎么做」时，**去读它的代码**，不要凭方法学常识推断，
也不要因为它发在顶刊就假定它做法更严格。付费正文、预印本被 WAF 拦截（bioRxiv 走 Cloudflare 时
curl 与真实浏览器双双被挡）都拦不住这条链：

1. **先查本地历史抽取的方法学文本** —— `search_files` 找 `results/*/data/*methods*.txt`、`*doc*.txt`。
   之前读过该论文 PDF 时，正文+methods 往往已抽成文本落盘，**命中率比想象的高**（本例 67 页 PDF 的
   methods 段落本地就有，一步到位）。⚠️ 这类文本常**按行截断** —— 用 `sed -n`/python 按**行号逐行**取
   全文，别满足于 `grep` 的片段（片段会停在句子中间，看不出模型公式）。
2. **读 Data and code availability 段 → GitHub 仓库 → 直接读 `.R` / `.py`**
   - 列目录 `https://api.github.com/repos/<org>/<repo>/contents/<dir>`（未认证 60/h 限流；
     路径含空格/括号时做 URL 编码）
   - 取文件 `https://raw.githubusercontent.com/<org>/<repo>/main/<path>`
   - **读核心函数体**（formula / contrasts / 聚合 / 阈值），⛔ 别只看 README —— 本例 DEG 目录的
     README 只有 **1 字节**
   - 脚本比正文更权威：本轮方法学结论**全部来自脚本**（两阶段 RUV+MAST、`k=10` 取前 5、
     `Q<0.05`、`|log2FC|>0.25`、`pctcut=0.1`）
3. 补充材料仓库（Zenodo / 期刊图库）：`https://zenodo.org/api/records/<id>`（取 Content notes、
   Supplementary Tables 的文件名与直链）
4. OA 副本兜底：`https://api.openalex.org/works/doi:<DOI>` 看 `locations`（可能指向 Zenodo / 机构库；
   `best_oa_location` 里 `pdf_url` 可能为 null，别只信它）

**反面清单**：⛔ 不要用"顶刊应该做得更严格"推断它的做法；⛔ 被拦截后不要反复换代理重试同一页面
（bioRxiv Cloudflare、corsproxy keyless 403、allorigins 空响应 —— 各试一次即收手），**转到代码仓库**。

⚠️ **「grep 一两个脚本 → 断言上游没有这个参数」是假阴性高危动作（2026-09-28 实测）**：
同一参数（`|log2FC|>0.25`）在本技能的既有核实记录里**确实从该 repo 脚本读到过**，
而本轮只 grep `RUV_MAST_pDEG_MBA.R` + `RUV-seq_sDEGs.R` 却零命中 —— 因为阈值可能在下游
pre-computed 列表（该脚本第 35 行 `read.csv('~/Revise_DEG_LIST/Revised_DEG_all_filter.csv')`，
过滤发生在本仓库之外）、snATAC 同族目录（`Filter_correlation_with_coefficient.R`）或补充材料里。
**纪律**：① `recursive=1` 列全树，grep **同族目录全部脚本**（别只取 1–2 个文件）；
② 措辞只能写「在这 N 个脚本里没找到」，⛔ 不得写"官方没有该阈值"；
③ 与既有 references 里的抽取记录**对不上时，先报冲突、不下定论**（可能两次 grep 范围不同）。

⛔ **路径含括号/空格时必须 `curl --globoff`**：`.../04.Identification_of_differentially_expressed_genes(DEGs)/README.md`
不加 `--globoff` 会被 curl 的 glob 解析吞掉 → 取到空内容（本轮 README 返回 0 字节、同前缀的脚本却正常，
差异只在文件名的括号上下文，**别据此判断"README 是空的"**）。
**交付时说明证据层级**：正文本体没读到就如实说，同时给出「本地 methods 抽取文本 + 作者公开脚本」
两条独立来源，比只报一个"我没权限"有用得多。

### 2.7 用户前提核验：把「是不是就是 X？」核到原文（2026-10-04 实测，Biomni）

**触发**：用户**带着一个来自别处的心智模型**来求确认（表面是 yes/no，实质是「请核原文」）——
「2500 篇论文整理出来的东西，**是不是就是它的 skill 呢**？我用过 biomni，它就是典型的触发
对应的 skill，然后调用里面的工具，然后完成任务。是不是？」同类：「XX 是不是就是 YY？」
「它是不是靠提示词？」
⚠️ 比普通提问**更危险**：用户自己用过那个工具 ⇒ 有强直觉，顺着点头就把错概念固化进后续讨论。
**纠正必须给他能自己复核的原文**，否则等于用权威压他的经验。

1. ⛔ **不顺着用户假设点头**；结论可以是"不完全是 / 恰恰相反"。
2. **先定位前提依赖的具体数字与术语，逐个做命中探针 —— 命中次数本身就是证据**。
   用 `scripts/pdf_probe.py`（抽取 + 计数 + 上下文一次到位，全文落盘免重抽）：
   本例 88 页 / 166,776 字符 ⇒ `skill` **全文只 1 次**（且是 Discussion 的 "coding **skills**"），
   `2,500` 1 次、`knowledge base` 1 次（落在参考文献区）⇒ 根本不存在"2500 篇 → skill"这回事。
   探针词 = 用户前提里的词 + 论文自己的核心架构词（本例 `action space` 9 / `retriev*` 27）。
3. **引用逐字原句 + 标明出处段落**（Abstract / 图注 / Methods 小节），不自造转述。
4. **给「用户词汇 → 论文实际概念」映射表**收束；用户在评估我们自己的平台时，再补一张
   **与本平台设计的对照表**（这轮给的是「Biomni 把论文榨成工具箱 / 我们把经验榨成菜谱」）。
5. **论文内部口径不一致要主动自报，不替它抹平**（本例图 1 图注/正文 = 2,500 篇 bioRxiv，
   Methods 初始迭代 = 100 篇；不矛盾但口径不同，用一行 italic 提醒）。
6. **有过程性内容就配 Mermaid**（本例 CodeAct 循环：计划 → 检索器挑资源 → LLM 写代码 →
   容器执行 → observation 回灌 → 收敛/迭代），用户的措辞里出现"先 A 再 B"就是流程类。

**可借鉴的结论形状**：开门见山否定 → 用原文证明被榨出来的是什么（314 个资源：150 专用工具 +
105 软件 + 59 数据库）→ 承认他直觉对的那半步（确有 `prompt-based retriever` 这层"触发"）→
指出单位不对（检索出的是工具，不是打包流程）→ 对照表 + 一句话收束。
完整证据链（6 处逐字原文锚点、命中计数、对照表、口径不一致）见
`references/paper-premise-verification.md`。

### 3. HTML→文本提取（批量抓文档时）
python 正则：去 `<script>/<style>` → 去标签 → `html.unescape` → `\s+` 折叠成单行 → 按关键词窗口（±250 字符）打印上下文。避免整页输出浪费 token。

### 3.5 未知软件/API 术语识别的搜索兜底链（通用，2026-08-29 验证）
当用户问一个不认识的软件名/API 组件/术语（如 "acme-gateway"），且生物文献检索无意义时，按此链兜底：
1. `search_knowledge`（本地 KB，几乎必空）→ `search_papers`（生物文献，若该词是纯 IT 概念也必空，跳过不纠结）
2. **先 grep 本仓库**（`search_files pattern=术语 path=项目根`）——术语可能是本地组件、配置项或测试 mock 数据；并检查出现上下文（agent.log / state.db 里可能是上轮工具调用痕迹，别误判为真实组件）
3. `session_search` 查历史会话是否有讨论（注意现网 FTS 可能 0 命中 = 无历史）
4. 搜索引擎（Google 常弹验证码 → Bing 结果空洞 → DuckDuckGo html 也可能被 JS 验证码挡）→ **最终可靠通道：GitHub API**
   - 找项目：`curl -s "https://api.github.com/search/repositories?q=<术语>&per_page=10"` → python 解析 `full_name | description`（描述即定义，几秒出结果）
   - 读定义：`curl -s "https://raw.githubusercontent.com/<org>/<repo>/master/README.md"`（分支 main 404 就试 master；也可能 README 不在根目录）
5. **占位名歧义必须读真实项目确证**：`Acme`（如 Acme Corporation）是经典虚构占位名，很多内部 demo 用 acme-* 当前缀；而 ACME（RFC 8555）是真实协议（自动证书管理环境，Let's Encrypt 所用）——同一个词两种含义，定论前必须看 README 的工作方式/架构图，不能凭名字猜

### 4. 核实与诚实规则（不可违反）
- **只引用真实查询返回的 PMID/DOI**；检索接口可能不回传 DOI 字段（例：ComBat, PMID 16632515）→ 引用期刊标准 DOI 并在报告"注记"中标注，不静默编造
- 🔴 **引用必须自报「核到哪一层」**（2026-10-02，用户「查证原文再答」要求的落点）——三级，
  低层级可用但**必须显式声明**：
  | 层级 | 拿到什么 | 能说什么 |
  |---|---|---|
  | **检索层** | 标题/期刊/年/DOI **逐字比对**（`query_ncbi` / `search_papers` 回执） | 可说「已核实」，**必须补一句「未读正文数据」**；⛔ 不得引用文中的具体数值 |
  | **摘要层** | 读过 `abstractText`（Europe PMC `resultType=core`，§1 步 3） | 可引用摘要里出现的数字/结论 |
  | **全文层** | 读过正文/图注（§1 步 7 / §2.5） | 才可引用细胞数/百分比/图号 |
  实际句式（可直接照抄）：「已核实（PubMed 逐字标题）：> "标题"（刊, 年, DOI）；**没读它的正文数据**，
  按标题层面的结论用」。⚠️ 引用**支撑方向/因果**的文献时尤其必写 —— 读者据此判断该结论能不能反着用
  （例：把「训练后染色质闭合」当方向依据时，必须让人看到我只到检索层）
- 基于原理的推断（如"跨物种需 ortholog 化"）必须在报告中标注为推断，不得写成官方原文
- 性能/规模声明优先引用论文摘要原文（如 Harmony "~10^6 cells on a personal computer"、Luecken 2022 ">1.2 million cells / 68 method combinations"）
- 报告末尾附"诚实性注记"段落，列明推断项与缺失字段

### 5. 交付形态：给合作方/外部方的说辞（2026-10-02 用户连续两轮纠正）

**触发**：用户说「我要怎么跟合作方说 / 给我**中文和英文版本的**说辞 / 也算是我要给他的解释」。

**用户原话（同一诉求连纠两轮）**：「不要把事情搞复杂」「**不要太复杂，简单点**」——
此前我给了五层判据表 + Mermaid 流程 + dsh-ui 卡片 + 9–11 条参考来源，被连否两轮；
最终被接受的形状 = **3 点、中英各一版、纯文字、可直接复制**。

**硬性形状（默认照做）**：
1. **中英各一版，各自独立完整**（不是「中文段落 + 英文摘要」），包在引用块里**可直接复制粘贴**。
2. **每版 ≤3 点**，每点 1–3 句；每版首句先给结论（本例：「靠链分开的。」）。
3. ⛔ **说辞里不堆 Mermaid / 表格 / dsh-ui / 参考文献清单** —— 给合作方的那封信没有这些东西的位置；
   文献与推导留在本会话的分析记录、报告、文件里，⛔ 不要塞进说辞。
4. **诚实边界写进说辞本身**，但只占 1 句（本例：3′/5′ 建库与链特异参数待确认），不展开成清单。
5. 说辞之外**另用中文给用户一段「要点/前提」导读**（可稍详）——用户要的是「两封信 + 给他的导读」，
   不是三封信。
6. 只读交付：**不落文件、不弹意图表单**（除非用户要存成 md）。

**升级规则**：默认先给短版；用户说「再详细点 / 我要完整推导 / 我要能自己复核的证据」才展开长版。
⛔ 不要在同一轮既给长版又给短版（等于没简化）；⛔ 被说「太复杂」后不要只删几个词，要换形状
（表格 → 三点、Mermaid → 一句话）。

## Pitfalls（真实踩坑记录）
| 现象 | 原因/处理 |
|---|---|
| satijalab.org 部分文章页 404（如 integrate_rpca.html、harmony 教程） | 文章未发布但 GitHub `vignettes/` 目录有源 Rmd（已确认：seurat5_integration.Rmd / seurat5_integration_rpca.Rmd / seurat5_integration_large_datasets.Rmd / seurat5_integration_bridge.Rmd / seurat5_weighted_nearest_neighbor_analysis.Rmd）→ 走 jsdelivr |
| raw.githubusercontent.com 拉取失败 | 网络屏蔽 → 换 jsdelivr CDN（同一路径格式） |
| github.io 站点页面 curl 报 SSL error 35（如 smorabit.github.io） | 不是重试能解决的 → 改拉 `raw.githubusercontent.com/<org>/<repo>/<branch>/<path>` 源码/vignette Rmd（raw 失败再换 jsdelivr） |
| web_extract 报 "search-only backend and cannot extract URL content" | 后端是 ddgs（仅搜索）→ 用 curl 下载 HTML 后 python 正则提取正文（去 script/style → 去标签 → html.unescape → 关键词窗口打印） |
| download_pdf 的 pmc_fulltext 策略失败 | 手动 curl `europepmc.org/articles/PMC<id>?pdf=render` 直接拿 PDF（开放获取可用） |
| 任务/需求描述中的期刊名/标题与实际不符（例："hdWGCNA 是 Nature Methods 2023"实为 Cell Reports Methods 2023;3(6):100498） | 引用前用 query_ncbi(pubmed, 作者+关键词) 核实卷期；查无此文就在报告"更正"段落如实标注，不顺着任务说法写 |
| 大文件 write_file 流超时 | 内容拆 3 部分分别 write_file 再 `cat` 合并，单次调用控制在 ~8K token 内 |
| scanpy readthedocs 个别生成页 404（scanpy.pp.combat 等） | 用已抓取页面的导航/API 索引确认函数确实存在；新版函数可能移位（pp.combat 曾属 external） |
| search_papers 关键词搜索无结果 | 混合源漏检 → query_ncbi 按精确标题直查。⚠️ **`query_ncbi` 自身对长句/多关键词组合同样常常静默返 0**（2026-09-28 实测：`"choosing log fold change threshold cutoff differential expression arbitrary"`、`MAST Finak differential expression single-cell hurdle`、`Risso factor analysis control genes samples normalization` 全 0 命中；改成带引号的精确标题 `"Bias, robustness and scalability in single-cell differential expression analysis"` 或 2–4 个短核心词 `Finak MAST transcriptional changes heterogeneity` 立刻命中）⇒ **查询控制在 2–4 个核心词，或整句标题加引号**；连试 2 次仍 0 就换短词，⛔ 别持续改写长句（会触发循环检测）。0 命中 = 检索式问题，**不是"该文献不存在"** |
| terminal 连续 404 触发工具失败计数 | 每次换新 URL/新命令串，用 GitHub API/版本化 URL 换方案，不要原样重试 |
| download_pdf 对 Nature/Science/Cell 系列失败（无 PMC 全文 + Unpaywall 抓取失败） | **Nature HTML fallback**：`curl -sL -H "User-Agent: ..." "https://www.nature.com/articles/<DOI>"` → python 去 script/style → 去标签 → html.unescape → 可提取完整 Methods/Results/Figure descriptions（已验证 Nature Medicine 2026）。不需要 JavaScript 渲染。正文通常在 HTML 6000-15000 字符位置。详见 `references/nature-html-extraction.md` |
| `search_papers` 每条结果的 `abstract` 都是 `""` | 该工具**只回元数据**（标题/作者/期刊/年/DOI/PMID），无摘要 ⇒ 不能据此判支撑等级；必须补一次 Europe PMC `resultType=core` 批量取 `abstractText`（模板见 `references/claim-to-citation-support-grading.md` §3） |
| Europe PMC 全文检索 `FULL_TEXT:"..."` **固定 0 命中**（换 3 种写法仍 0） | 该服务**没有 `FULL_TEXT:` 字段** ⇒ 全文检索用 **`body:"..."`**（同义查询立刻 42 命中）。零命中的新写法**不要反复改写续命**，换字段/换通道一次，仍空就转交付 |
| 同一轮连发 7 次近似的换词检索 → 触发平台**循环检测强制干预**（要求停止重复动作） | 检索轮数上限 **2-3 轮**：宽搜拿候选 → 批量取摘要定级 → 转交付；多查询/多 PMID **合并到一次脚本**（列表 + for），不要"一次调用一个查询"。某子论断无直接证据 ⇒ 产出就是如实报缺口。**同一原则适用于「取材料」阶段**：全文 XML 已解析完（章节 + 全部图注一次到位）后，再为「补一张 Extended Data 图」发起查询同样被判循环（2026-09-25 实测）⇒ 一次提取覆盖全部所需，然后直接写产出 |
| Semantic Scholar `graph/v1/paper/search` 连续 **429** | 公共端点限流 ⇒ 主力用 Europe PMC/PubMed，别在同一轮反复重试 S2 |
| `.../rest/PMC<id>/fullTextXML` 偶发 **HTTP 500** | 重试 1-2 次；仍失败退回摘要级证据并在交付里注明"未核全文" |
| 问未知软件/API 术语（纯 IT 概念），search_knowledge/search_papers 全空 | 该术语不是生物概念，文献检索跳过 → 走 §3.5 兜底链：grep 本仓库 → session_search → GitHub API repo search 拿定义（见 `references/unknown-term-identification.md`，acme-gateway 实证） |
| Google 搜索弹 sorry/captcha 验证码、Bing 结果只有无关公司页、DuckDuckGo html 被 JS 验证码挡 | 搜索引擎不可靠是常态 → **直接走 GitHub API** `api.github.com/search/repositories?q=...`（结构化 JSON，无 JS，几秒出描述即定义）；raw.githubusercontent.com 此刻可用（本会话验证），若被网络屏蔽再换 jsdelivr |

| 用 `lit_bridge.py ... --json` 检索后解析**零输出、也不报错**（`json.load` 成功、循环不执行） | 结果数组键是 **`records`**，我按惯例写成 `results` ⇒ 取到空列表、静默跳过；根因是**只用 `tail` 看被截断的回执片段就推断 schema**（2026-09-25 实测，白烧 1 轮） | 解析前先 `print(list(d.keys()))` 打印顶层键（或写递归 `walk()` 自动找 dict-list），**一次定 schema**；⛔ 下次遇到任何新 CLI/API 的 JSON，都别凭片段猜键名 |
| 把 `tail -c 5000` 看 `lit_bridge.py --json` 的输出当成"完整结果" → **`count` 字段与前 1–2 条记录被静默吃掉**，交付清单凭空少项（2026-09-25 实测：PubMed 首跑 tail 只剩 7 条、`count` 完全看不到，据此汇报就会漏报命中数） | `tail` 从**尾部**截断，JSON 头部的 `query/count/sources_used` 与靠前记录先被切掉；回执看着"就是这些"，实则截断 | 报"命中几条 / 交付清单"时**一律管道进 python 解析 JSON，绝不看 tail 片段**：`... --json | <py> -c $'…'`（git-bash 下多行 `-c` 用 **ANSI-C 引用 `$'…\n…'`**，免去嵌套转义引号——比 `\n` 手拼与 heredoc 都稳）；只打印 年 / 期刊 / 标题 / DOI / PMID / type 六个字段。完整可粘命令见 `references/lit-bridge-multi-source-retrieval.md` §解析 |
| Crossref 同一条字面检索式**每次都混入明显不切题的条目**（2026-09-25 实测：`skeletal muscle aging single-cell RNA sequencing` → `count=6`，其中 3 条是鸡骨骼肌发育的补充材料 `component`（`year=None`）、骨骼肌**发育**综述、**卒中 microglia**——与骨骼肌衰老无关） | Crossref 是全学科全类型索引，字面词命中即返回；`component`（论文补充材料）连 `year` 都缺 ⇒ 不能按年份排序/筛选，排序结果会莫名把 None 排头 | 交付前**逐条按标题切题度筛**（不只是按 `type` 过滤）：剔 `component` / 跨物种跨疾病条目；清单里**标注真实类型**（会议摘要/预印本/评论/期刊论文）并写明"命中 N 条、取最贴合 M 条"，被剔除的条目在"源状态说明"里点名列 DOI——**让用户看得到剔除动作，而不是只看到 3 行表** |
| Crossref 侧命中数远低于预期（`--limit 3` 只回 2 条，且全是会议摘要） | Crossref 对**并列名词的字面短语**匹配弱；换领域惯用词后命中翻数倍（实测 `single-cell RNA sequencing` → 2 条 vs `single-cell transcriptomics` → 9 条、`single-nucleus atlas` → 6 条）。另：Crossref 条目**无 PMID**，且混入 `book-chapter` / `posted-content`(预印本) / `peer-review` / `grant` 等非正式类型 | 一条检索式命中不足就**换词重跑**（比调 `--limit` 有效）；交付前按 `type` 过滤或**逐条标注类型**（会议摘要/预印本要写清）；要 PMID 回 PubMed 侧查 |
| 只读文献检索收尾时被门禁连环点名：rail_review(post) 判 `代码过短` / `使用 &&` failed，debate 门控要求升级 L2 | 审查器与辩论门控都按**分析级任务**标定，与「只读检索、零文件产出」口径天然不匹配（用户本轮明令"不生成文件"） | **如实说明口径不匹配 + 给真实证据（命令 + 命中数），不补假产物、不硬凑辩论**；处置细节与判据见 `platform-execution-pitfalls` 使用要点 §13 |

## References
- `references/paper-fulltext-to-deliverable-material.md` — **论文全文 → 组会汇报大纲（2026-09-25 实测）**：DOI→Crossref→PMID→PMCID→Europe PMC `fullTextXML` 全文获取链、XML 两遍解析（`<fig>` 图注直接当 slide 素材 / `<sec>` 白名单取正文、避开 Methods）、每页四件套（结论式标题+带真实数字要点+指定 `Fig. Na` 图号+讲点）、hero figure/流程 Mermaid/「与本组工作的关联」等组会节式、**零文件交付纪律**（不要生成文件时连中间产物都要移出交付路径并声明非交付物）、与 nature-paper2ppt 的交接
- `references/claim-to-citation-support-grading.md` — **论断→引用匹配与支撑分级（2026-09-25）**：拆子论断、保守分级口径（综述只作 context）、Europe PMC 批量取摘要模板、接口坑（`FULL_TEXT:` 无效须用 `body:` / `search_papers` 无摘要 / S2 429 / fullTextXML 500）、检索轮数上限与循环检测规避、可复用工作示例（卫星细胞衰老论断 7 篇核验文献 + 缺口说明）
- `references/lit-bridge-multi-source-retrieval.md` — **lit_bridge.py 多源检索配方（PubMed + Crossref，2026-09-25 实测）**：调用模板与代理、JSON schema（`records` 键）、Crossref 检索式策略与 `type` 过滤、只读检索交付口径（不落文件/不入库/不问/不辩）、本次 6 篇清单与命中数证据
- `references/unknown-term-identification.md` — 未知软件/API 术语识别实证（acme-gateway 2026-08-29）：完整兜底链、GitHub API 命令、Amce 占位名 vs ACME 协议判别（RFC 8555 定义）
- `references/nature-html-extraction.md` — Nature/Science/Cell 系列 HTML 页面提取技巧（PDF 下载失败时的 fallback，含 curl 命令和提取模式）
- `references/seurat-vs-scanpy-batch-integration.md` — Seurat vs Scanpy 批次整合对比知识库：快速选型表、方法原理速查、v5/scanpy API 要点、11 篇核验文献（PMID/DOI）、官方文档获取技巧（本次调研沉淀）
- `references/hdwgcna-vs-wgcna-methodology.md` — hdWGCNA vs 经典 WGCNA 方法学要点（2026-08 核实）：文献引用更正（CRM 2023 非 Nature Methods）、metacell bagging+kNN 算法细节与聚合方式（仅 average/sum）、流程对比、eigengene/TOM 数学差异、论文 PDF/源码获取技巧
- `references/annotation-file-verification-and-antisense-loci.md` — **注释文件核实 + 反义基因座判读（2026-10-01/02 实测，GRCh38 / GENCODE v32）**：源文件优先于 API 转述的判据、`gzip -t`/zcat 统计命令、GTF vs FASTA 选择表、`-AS1` 家族命名与坐标对照（MEF2C / MEF2C-AS1）、**§2.5 重叠区的 ATAC 可及性归属**（问法纠偏表、R1–R4 区间设计、供体配对统计、四条判定分支、替代启动子核查命令、三条不可越界推论）、术语表述纪律（5′-5′ 最近 vs 转录方向的混称陷阱）、坐标随版本重 grep 纪律
- `references/paper-premise-verification.md` — **用户前提核验（2026-10-04 实测，Biomni）**：用户带心智模型来求确认时的铁律（不许顺着点头 / 命中次数即证据 / 逐字引用 / 映射表 / 主动自报口径不一致）、6 处逐字原文锚点（Abstract「without relying on predefined templates or rigid task flows」、Fig.1a 图注 2,500→150+105+59、Methods *Action Discovery* / *Biomni-A1* CodeAct、Discussion 局限）、被接受的四段式结论形状与 Biomni↔MemOmics 对照表
- `scripts/pdf_probe.py` — **PDF 全文抽取 + 关键词命中探针**（一次调用：pymupdf/pypdf 抽取 → 落盘 → 按词给命中计数（降序）+ 有限上下文窗口）。用于 §2.7 前提核验与任何「先看哪些说法有原文支撑」的场合；`--kw` 传用户前提里的词 + 论文核心词，`--n/--w` 控制窗口数量与大小
