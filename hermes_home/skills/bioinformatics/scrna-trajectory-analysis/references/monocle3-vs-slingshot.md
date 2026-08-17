# Monocle3 vs Slingshot：方法对比与已核实事实（2026-08 调研）

调研产物。所有事实均经一手来源核实：Monocle3 官方文档 + learn_graph.R 源码、Slingshot Bioconductor 页面/vignette/参考手册 PDF、Cao 2019 论文全文（Europe PMC）、NCBI PubMed。完整中文对比报告示例见 work/monocle3_vs_slingshot/。

## 核心差异一句话
- **Monocle3** = 自包含框架：UMAP 降维 → Louvain 聚类 → PAGA 合并 partitions → learn_graph 学主图 → order_cells 拟时 → graph_test 差异检验。
- **Slingshot** = 即插即用模块：只需降维矩阵 + 聚类标签 → MST 定骨架 → simultaneous principal curves 拟合谱系。官方定位是"降维聚类之后的一步"。

## 算法要点（含出处）

### Monocle3（Cao 2019 Nature 方法原文 + learn_graph.R 源码头注释）
- 三段式（论文原文）：UMAP 投影 → Louvain 社区检测（igraph clustering_louvain）→ PAGA 统计检验合并 supergroups（=partitions，每个 partition 一条独立轨迹）→ 每 partition 内解析轨迹，**显式识别 branches AND convergences（汇聚）**。
- learn_graph = reversed graph embedding（论文：基于 SimplePPT 算法的改进版），主图与数据同低维空间。
- **闭环（loop）支持**：loop closure 参数 euclidean_distance_ratio=1、geodesic_distance_ratio=1/3（两条件同时满足才连边成环）；prune_graph=TRUE（minimal_branch_len=10 剪小分支）；nn.k=25（近邻图）。
- cluster_cells 同时产出 cluster + partition；resolution 控制 partition 粗细（经验值 1e-4~1e-5）。
- graph_test：**Moran's I 空间自相关**，morans_I∈[-1,1]（0=无效应），neighbor_graph="knn" 或 "principal_graph"，q_value 列取显著基因。
- find_gene_modules：对**基因**跑 UMAP + Louvain 聚共表达模块（不是对细胞）。
- 官方 helper：get_earliest_principal_node（取目标早期细胞群投影命中最多的主图节点作 root，配合 order_cells(root_pr_nodes=...)）。
- 规模：论文实测 ~200 万细胞（MOCA、56 条轨迹）；但 learn_graph 社区经验 >6 万细胞明显变慢。

### Slingshot（Street 2018 + Bioconductor manual/vignette）
- getLineages：聚类中心距离构建 MST。默认 dist.method="slingshot"（联合协方差归一化的马氏型距离；小聚类自动退化为对角协方差）。**人工聚类 .OMEGA.** 与每个真实聚类固定距离 → 限制 MST 最大边长 → 不相连部分切成多树（森林，支持多轨迹）；omega/omega_scale（默认 1.5）控制。
- start.clus：**不影响 MST 构建**（vignette 原文），只影响分支曲线构建方向；end.clus 强制叶节点；不指定 start.clus 时启发式自动选，**官方明确 "not recommended"**。
- getCurves：simultaneous principal curves（princurve 包）；shrink（分支向共享平均曲线收缩）、extend（'y'/'n'/'pc1'）、reweight/reassign（共享细胞迭代重分配）、allow.breaks（早期分叉允许不同起点）。
- 性能：MST 在聚类层面与细胞数弱相关；曲线迭代投影 dense 时 O(n²)；**approx_points 默认 150**（取 min(150, 细胞数)），不限制拟时值唯一性。
- 谱系 = 起点→叶节点路径（每条 lineage 一列）；输出 slingPseudotime（矩阵，不在该谱系为 NA）、slingCurveWeights、slingBranchID/slingBranchGraph（分支归属）。
- 聚类数：太小漏分支、太大假分支；GMM（mclust/BIC 自动选 k）或 k-means；**即使单谱系也建议聚类**以发现新分支。

### tradeSeq（Van den Berge 2020，与 Slingshot 配合）
fitGAM（负二项 GAM，nknots=6）→ associationTest（全局）/ startVsEndTest（起终）/ diffEndTest（谱系终点差异=终态基因）/ patternTest（分叉依赖基因）/ earlyDETest（分叉早期差异）。

### ⚠️ 拟时计算（源码级验证 — 2026-08 二轮调研补充）
- **Monocle3 伪时间 = 沿主图 ψ 到最近根节点的测地距离**（Cao 2019 方法学原文："Each cell's pseudotime is taken as the geodesic distance along ψ to the closest of these root nodes"）。order_cells.R 的 extract_general_graph_ordering() 实证：细胞投影到主图最近节点 → 构建细胞级图 `pr_graph_cell_proj_tree` → `igraph::distances(..., v=root)` 最短路径 → 多根时逐细胞取 min；根用 root_pr_nodes（图节点名 "Y_xx"）或 root_cells（自动映射最近节点），都不给则弹 GUI。**从根不可达的细胞伪时间 = infinite（plot_cells 显示灰色）**。
- **Slingshot 伪时间 = 正交投影 + 弧长**：细胞正交投影到主曲线，伪时间 = 投影点沿曲线的弧长 λ（单位速度参数化 ||c′(t)||=1 保证弧长≡拟时）。输出 n×L 伪时间矩阵 + 每谱系权重 + slingAvgPseudotime（按权重跨谱系加权平均）。
- 写对比报告/方法学章节直接引这两条定义即可，无需再抓源码。

### ⚠️ BEAM 归属修正（2026-08 核实）
"Monocle3 自带 BEAM"是**错误假设**：BEAM（branched expression analysis modeling）是 **Monocle 2** 的函数（Qiu 2017, PMID 28825705）；Monocle3 官方文档检索 BEAM 为 0 命中。Monocle3 的分支分析 = `graph_test(neighbor_graph="principal_graph")` + `choose_graph_segments()`（交互选分支区段，再对其子集跑 graph_test 找分支特异基因）。

### Saelens 2019 基准框架（引用时用）
45 方法 × 110 真实 + 229 合成数据集，四大评估标准：细胞排序 / 拓扑 / 可扩展性 / 易用性；结论 = 方法选择取决于**数据维度与轨迹拓扑**（指南 guidelines.dynverse.org）。写报告可引用此框架与结论，勿凭记忆断言具体名次（方法名只出现在补充材料的图中，PDF 抽不到文本）。

## 文献（PMID/DOI 均经 PubMed 核实，可直接引用）
| 文献 | PMID | DOI |
|---|---|---|
| Trapnell 2014 Nat Biotechnol（Monocle v1） | 24658644 | 10.1038/nbt.2859 |
| Qiu 2017 Nat Methods（Monocle2 DDRTree） | 28825705 | 10.1038/nmeth.4402 |
| Cao 2019 Nature（Monocle3） | 30787437 | 10.1038/s41586-019-0969-x |
| Street 2018 BMC Genomics（Slingshot） | 29914354 | 10.1186/s12864-018-4772-0 |
| Van den Berge 2020 Nat Commun（tradeSeq） | 32139671 | 10.1038/s41467-020-14766-3 |
| Saelens 2019 Nat Biotechnol（45 工具 benchmark） | 30936559 | 10.1038/s41587-019-0071-9 |

## 调研核实路径（可复用）
- Monocle3 官方文档（新站）：`https://cole-trapnell-lab.github.io/monocle3/docs/{trajectories,clustering,differential,getting_started,alignment}/`（**旧 `/monocle3/reference/*.html` 已 404**）
- Monocle3 源码：`https://raw.githubusercontent.com/cole-trapnell-lab/monocle3/master/R/learn_graph.R`（roxygen 头注释含算法说明）
- Slingshot：`https://bioconductor.org/packages/release/bioc/html/slingshot.html`；vignette：`.../vignettes/slingshot/inst/doc/vignette.html`；manual PDF：`.../manuals/slingshot/man/slingshot.pdf`（pypdf 提取文本后按函数名定位）
- 论文方法原文：Europe PMC REST `https://www.ebi.ac.uk/europepmc/webservices/rest/PMC<id>/fullTextXML` → strip XML tags 后搜关键词（如 "principal graph"、"Louvain"）
- PMID/摘要核实：NCBI efetch `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=<PMID>&rettype=abstract&retmode=text`

## 抓取坑（Windows 主机实测）
- **curl（Schannel）抓 GitHub Pages 报 SSL error 35**：`-k`、`--tlsv1.2` 均无效；bioconductor.org 正常。修复：用 Python urllib + 不校验的 SSL context（OpenSSL 栈）可成功：
  ```python
  ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
  urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60, context=ctx)
  ```
- HTML 转文本：去 `<script>/<style>` → 去标签 → html.unescape → 折叠空白；顺带 `re.findall(r'href="..."')` 可发现站点导航结构（找新 URL 路径）。
- **raw.githubusercontent.com 不可达时**：用 jsdelivr CDN 镜像 `https://cdn.jsdelivr.net/gh/<user>/<repo>@<branch>/<path>`（实测抓 monocle3 R/order_cells.R 成功）。❌ Bioconductor git raw（`git.bioconductor.org/packages/<pkg>/raw/master/...`）返回 gitolite 错误，不可用。
- 开放获取 PDF 直链：BMC 系 = `https://<journal>.biomedcentral.com/counter/pdf/<DOI>`（Slingshot BMC Genomics 2018 实测可行）；Nature 系走 PMC（Cao 2019 = PMC6434952）。download_pdf 的 PMC 策略失败时可走此直链。
- PDF 文本提取：`python3 -m pip install pymupdf` 后 `import fitz`（execute_python 默认环境未装）；PDF 是补充材料时方法名常在图中（无文本层），别指望 grep 到。
