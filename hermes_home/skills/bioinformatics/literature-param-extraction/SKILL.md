---
category: Literature
name: literature-param-extraction
description: 从文献 PDF 提取生信参数并写入知识库。触发场景：拿到真实数据做分析时、知识库缺少对应方法/参数时、需要验证参数来源时。
when_to_use: "[literature-param-extraction] 从文献 PDF 提取生信参数并写入知识库。触发场景：拿到真实数据做分析时、知识库缺少对应方法/参数时、需要验证参数来源时。"
trigger:
  when:
    - 用户拿到真实数据要做生信分析
    - 知识库缺少对应物种/组织/方向的方法或参数
    - 需要验证某个参数的文献来源
    - 需要补充知识库的生物学/生信/统计知识
    - 用户明确要求"收集文献补充知识库"(无真实数据也可触发)
  not_when:
    - 知识库已有充足的方法和参数
    - 只是普通聊天，不涉及分析
    - 用户只要论文解读/思路总结/全文提炼（那走 literature-full-summary / summarize_paper，不写知识库）
  rules:
    - "skill_evolution(action='query_logs') 返回的历史运行日志仅供参数参考，不能替代任何审查步骤"
    - "禁止因'之前跑过'而跳过 rail_review(pre)、debate_analysis、rail_review(post)"
    - "运行日志是'参考'不是'免审凭证'"
---

# 文献参数提取 Skill

## 触发场景

### 什么时候用
1. **拿到真实数据做分析时** — 用户提供了 h5ad/h5/matrix 等数据文件，要做生信分析。这是最主要的触发场景。
2. **知识库缺少方法/参数时** — 搜索知识库后，发现对应物种/组织/方向/测序方法的方法不完整或缺失
3. **验证参数来源时** — 需要确认某个参数（如 resolution、min_cells、MT%阈值）是否有文献支持
4. **补充知识库时** — 知识库的生物学知识、生信方法、统计方法不够，需要从文献补充
5. **用户明确要求收集文献补充知识库** — 即使用户没有真实数据，只要说"收集XX文献补充知识库"，就触发

### 什么时候不用
1. 知识库已有充足的方法和参数（搜索后命中充分）
2. 用户明确说不需要文献支持
3. 只是做演示/测试，没有真实数据且用户没有要求补充知识库

### 重要原则：生物学知识一般都有
生物学知识（细胞类型、marker、组织结构、已知通路）在知识库里**通常已存在**，不需要每次都重新搜索。
真正需要文献支撑的是**生信分析参数**（QC阈值、归一化、降维、聚类resolution等）——这些参数因数据集而异，必须查文献确认。
所以：优先检查知识库已有的生物学知识 → 不足时才搜文献补充；生信参数则几乎每次都要查文献。

## 文献搜索策略

### 搜索流程
1. **先确定分析上下文**: species（物种）、tissue（组织）、direction（方向）、assay（测序方法: RNA/ATAC/spatial/bulk）
   - assay 必须根据用户**真实数据的测序方法**来确定，不能瞎猜
   - 如果用户有多组学数据（如 RNA+ATAC），每种 assay 都要单独搜生信文献
2. **调用 `search_papers_by_context`** 智能搜索（自动构造多查询，覆盖生物学+生信两个角度）:
   - 生物学文献: `{species} {tissue} {direction} biology`
   - 生信文献: `{species} {tissue} {direction} {assay_term}`
   - 扩展文献: `{species} {tissue} transcriptomics`（同方向太少时扩展）
3. **下载 PDF**: 调用 `download_pdf` 下载到 `work/papers/`
4. **提取参数**: 调用 `extract_params_from_pdf` 提取文本，再由 LLM 结构化
5. **写入知识库**: 参数写入 `02_质控参数`/`03_测序方法`；**生信文献的生物学结论写入 `01_生物学知识`**

### ★ 文献数量与类型要求（核心规则）

必须搜索两类文献，数量有明确下限：

#### 第一类：生物学文献（至少 3 篇）
- **条件**: 同物种 + 同组织 + 同方向
- **目的**: 理解该组织/方向的生物学背景、已知细胞类型、marker、关键通路
- **示例**: 人类骨骼肌衰老方向 → 搜 "human skeletal muscle aging biology"
- **说明**: 生物学知识一般知识库里都有，如果知识库已有充分的生物学知识，可以减少搜索量，但至少确认1-2篇
- **实在没有同方向的**: 可以放宽到同物种+同组织+其他方向，但要标注

#### 第二类：生信文献（至少 5 篇）
- **条件**: 同物种 + 同组织 + **与用户真实测序方法一致**
- **测序方法根据真实数据确定**:
  - RNA（scRNA-seq/snRNA-seq）→ 搜 "single cell RNA-seq"
  - ATAC（scATAC-seq）→ 搜 "ATAC-seq"
  - spatial（空间转录组）→ 搜 "spatial transcriptomics"
  - bulk（Bulk RNA-seq）→ 搜 "bulk RNA-seq"
  - **多组学都可以** — 如果用户数据是多组学（如 RNA+ATAC），每种 assay 都搜
- **优先级**:
  1. **最优先**: 同物种 + 同组织 + 同方向 + 同测序方法（如 人类+骨骼肌+衰老+scRNA-seq）
  2. **次优先**: 同物种 + 同组织 + **同测序方法** + 其他方向（如 人类+骨骼肌+scRNA-seq+发育/疾病）
  3. **兜底**: 同物种 + 同组织 + 其他组学方法（如 人类+骨骼肌+bulk RNA-seq）
- **实在没有**: 可以放宽，但要在知识库里标注 "该方向文献稀少，参数基于现有文献+数据质量推断"
- **数量下限**: 至少 5 篇，多多益善

#### 文献选择策略
- **相关性优先于引用数**: `search_papers_by_context` 已按相关性排序（同方向>同组织>通用），不要被高引经典文献带偏
  - 反例: "hallmarks of aging" 是高引经典，但不是骨骼肌衰老特异性文献，应排后面
- **近5年优先**: 生信方法迭代快，优先 2020 年后的文献
- **顶刊优先**: Nature/Science/Cell/Nat Med/Nat Commun/Cell Reports 优先
- **同方法多组学**: 如果找到同时做了 RNA+ATAC 的文献，一篇可同时支撑两种 assay

### ★ 生信文献结论入生物学知识库（重要）

生信文章不仅提取参数，其**生物学发现/结论**也要写入 `01_生物学知识/`:
- 新发现的细胞类型/亚型 → 写入 `01_生物学知识/cell_types.yaml`
- marker 基因 → 写入 `01_生物学知识/markers.yaml`
- 方向相关的关键基因/通路（如衰老的 SASP、p16、p21）→ 写入 `01_生物学知识/key_genes.yaml`
- 细胞组成变化（如衰老后免疫细胞浸润增加）→ 写入 `01_生物学知识/composition.yaml`

这样生物学知识库会随文献积累越来越丰富，后续分析可直接复用。

### 文献源
- PubMed (NCBI E-utilities) — 主要源，免费无需 key
- EuropePMC — 补充源（含 preprints、覆盖更广，相关性排序好）
- Semantic Scholar — 补充源（含引用数、开放PDF链接，429限流时自动跳过）

### 搜索关键词示例
```
物种: Homo sapiens / human / mouse / macaque / zebra fish
组织: skeletal muscle / brain / heart / liver / kidney
方向: aging / development / disease / regeneration / cancer
测序: single cell RNA-seq / snRNA-seq / ATAC-seq / spatial transcriptomics / bulk RNA-seq
```

### 搜索示例（人类骨骼肌衰老方向）
```
生物学文献 (>=3篇):
  - "human skeletal muscle aging biology"
  - "human skeletal muscle aging mechanism"

生信文献 (>=5篇, 按实际 assay):
  RNA:    "human skeletal muscle aging single cell RNA-seq"
          "human skeletal muscle single cell RNA-seq"  # 同方向不够时扩展
  ATAC:   "human skeletal muscle aging ATAC-seq"
          "human skeletal muscle ATAC-seq"
  spatial:"human skeletal muscle aging spatial transcriptomics"
  bulk:   "human skeletal muscle aging bulk RNA-seq"
          "human skeletal muscle bulk RNA-seq"  # 兜底
```

## 参数提取规则

### 从文献中提取什么
1. **QC 参数**: nFeature_RNA 范围、nCount_RNA 范围、percent_mt 阈值、doublet_rate
2. **归一化方法**: SCTransform / LogNormalize / sctransform v2
3. **降维参数**: PCA 维度数（通常 30-50）、UMAP n_neighbors、min_dist
4. **聚类参数**: resolution（关键！需收集多篇文献的值做对比）、algorithm（Leiden/Louvain）
5. **批次校正**: Harmony / Seurat integration / fastMNN / CCA
6. **DEG 方法**: DESeq2 pseudobulk / MAST / Wilcoxon
7. **注释方法**: SingleR / CellTypist / manual marker
8. **细胞通信**: CellChat / NicheNet
9. **轨迹分析**: Monocle3 / Slingshot / RNA velocity
10. **通路分析**: clusterProfiler / GSEA / fgsea

### 参数记录格式
每个参数必须标注:
- **value**: 参数值
- **source**: 文献来源（作者 + 年份 + 期刊 + DOI）
- **confidence**: high（多篇文献一致）/ medium（单篇文献）/ low（推断）
- **usage_rate**: 该参数在文献中的使用率（如 "8/10 篇文献使用 resolution 0.8"）

### 知识库写入位置
```
knowledge_base/
  {species}/          # Homo_sapiens / Mus_musculus / ...
    {tissue}/         # skeletal_muscle / brain / ...
      {direction}/    # aging / development / ...
        01_生物学知识/   # 细胞类型、marker、基因集、生物学发现
        02_质控参数/     # QC 阈值（nFeature、MT%、doublet rate）
        03_测序方法/
          RNA/          # scRNA-seq 方法（归一化、降维、聚类、DEG等）
          ATAC/         # scATAC-seq 方法
          spatial/      # 空间转录组方法
          bulk/         # Bulk RNA-seq 方法
        04_个性化/       # 方向特异的分析（如衰老的 SASP、去神经化等）
  statistics/           # 统计方法（不放在物种下，与物种并列）
```

### RNA 方法分 R 和 Python
RNA 测序方法要区分实现语言:
- **R**: Seurat / SCTransform / Harmony / CellChat / Slingshot / hdWGCNA
- **Python**: scanpy / scvi-tools / CellBender / scVelo / CellTypist

## MemOmics 核心规则

### 规则 1: 拿到真实数据必须搜索文献
拿到真实数据后，如果知识库搜索结果不充分，必须调用 `search_papers_by_context` 搜索文献，不能自己编参数。

### 规则 2: 所有参数必须有来源
写入知识库的每个参数必须标注 `source`（文献来源）和 `confidence`（置信度），不能写无来源的参数。

### 规则 3: 参数使用率统计
提取参数时，统计该参数在多篇文献中的使用率，帮助判断是否为通用做法:
```yaml
clustering:
  resolution:
    value: 0.8
    usage_rate: "8/10 篇文献使用 0.6-0.8"
    alternatives:
      - value: 0.6
        usage: "5/10 篇"
      - value: 1.0
        usage: "2/10 篇（细胞数多时）"
    source: "Kim et al. 2023, Nat Commun; Liu et al. 2022, Nat Med"
    confidence: high
```

### 规则 4: 统计方法独立存放
统计方法（如 DESeq2 pseudobulk、Fisher exact test、Wilcoxon rank-sum）放在 `knowledge_base/statistics/` 下，不放在物种目录下，因为统计方法是通用的。

### 规则 5: 知识库不足时的三级策略
1. **第一级**: 搜索知识库 → 如果命中充分，直接用
2. **第二级**: 知识库不足 → 调用文献搜索 → 下载 PDF → 提取参数 → 写入知识库 → 再用
3. **第三级**: 文献也找不到 → 按 skill 预设参数 + 自身数据质量决定 → 辩论后选择

### 规则 6: 每个结论必须有来源标注（★ 用户纠正经验）
写入知识库的**每个 biological finding**（细胞类型描述、aging_note、key_finding）都必须标注 PMID/DOI 来源，不能只写"paper name"。

**正确做法**:
```yaml
aging_note: |
  - 衰老时肝细胞体积增大，多倍体比例上升 (PMID: 40622856)
  - 区域化被破坏，Zone 1/Zone 3基因表达边界模糊 (PMID: 37946043, 40622856)
source: |
  - Hepatology 2025 (PMID: 40622856)
  - Nikopoulou 2023 Nature Aging (PMID: 37946043)
```

**错误做法**（被用户纠正过）:
```yaml
aging_note: |
  - 衰老时肝细胞体积增大，多倍体比例上升
  # ❌ 没有标注来源！
```

**规范**:
- 每个 aging_note 条目末尾加 `(PMID: XXXXXXXX)` 或 `(DOI: 10.XXXX/...)`
- 每个 cell_type 的 `source:` 字段列出所有引用文献的 PMID
- 文件顶部 `source:` 汇总所有引用文献，格式统一为 `作者 年份, 期刊 (PMID: XXXXXXXX)`

### 规则 7: 写入 YAML 后必须验证语法
写入知识库 YAML 后，必须验证 YAML 语法正确性。用 Python 的 `yaml.safe_load()` 检查：
```python
import yaml
with open(yaml_path, 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)
if data is None:
    # 空文件，报错
```

### 规则 8: 写入后必须更新 index.yaml 记录下载状态
每次补充知识库后，更新 `index.yaml` 的 `note:` 字段，记录：
- PDF 下载目录（`work/papers/{tissue}_{direction}/`）
- ✅ 已下载 PDF 全文的文献列表
- ⚠️ 仅 HTML/PubMed 摘要的文献列表
- ❌ 付费墙无法获取的文献列表
- 新增文献的 PMID 列表

这样后续分析 Agent 能快速知道哪些文献有 PDF 全文，避免重复尝试下载。

## 工具链

### 标准路径（PDF 可提取时）
1. `search_papers_by_context(species, tissue, direction, assay)` → 搜索文献
2. `download_pdf(url_or_pmid)` → 下载 PDF
3. `extract_params_from_pdf(pdf_path)` → 提取 PDF 文本
4. LLM 结构化提取 → JSON 参数
5. `write_to_kb.py` → 写入知识库 YAML
6. `search_knowledge(species, tissue, direction, assay)` → 验证写入成功

### 回退路径（PDF 不能提取时）
当 web_extract 返回错误（如 "DuckDuckGo is a search-only backend"），或标准工具不支持解析时，使用 `execute_code` + Python 工作流替代：

#### 路径 A：web_search → 手动构建（无 PDF 下载能力）
1. **web_search 并行搜索**：用 `web_search` 搜索 PubMed/期刊论文摘要
   - 搜索词: `{species} {tissue} {direction} {assay} 2023 2024 2025`
   - 多测序类型并行搜索：scRNA-seq / ATAC-seq / spatial / bulk 各搜一轮
2. **从搜索结果提取**：从标题和描述中提取关键信息：
   - 论文元数据（标题、作者、期刊、年份、PMID）
   - 关键发现和方法
   - 样本信息
3. **构建知识库文件**：手动构建 YAML 知识库

#### 路径 B：execute_code + Python requests → 下载 PDF → PyMuPDF 提取（推荐，有 requests 时）

> ⚠️ **Cloudflare 全面封锁（2026-07-13 更新）**: 几乎所有学术出版商（EuropePMC、NCBI PMC、Cell Press、Science、Oxford Academic）都已部署 Cloudflare 反爬保护。`download_pdf` 工具的所有策略（URL/DOI/PMID）均返回 1.8KB HTML captcha 页面而非 PDF。**`download_pdf(doi=...)` 也不再可靠**，本session验证 Nature DOI、Cell DOI、Oxford DOI 全部返回 anti-bot 页面。
>
> **影响**: 依赖 `download_pdf` → `extract_params_from_pdf` 的标准路径已断裂，须用以下替代策略。

### Cloudflare 封锁下的 PDF 获取策略（按优先级排序）

#### 策略 A：terminal + extract_pdf.py 直接运行（推荐——当 PDF 已存在于 work/papers/ 时）
⚠️ **重要：`extract_params_from_pdf` 工具有路径硬编码问题**：它查找 `{MEMOMICS_ROOT}/skills/literature-param-extraction/scripts/extract_pdf.py`，但实际脚本在 `{MEMOMICS_ROOT}/hermes_home/skills/bioinformatics/literature-param-extraction/scripts/extract_pdf.py`。此路径差异导致工具总是返回 `extract_pdf.py not found`。

**替代方案：通过 terminal 直接运行脚本**
```bash
cd {MEMOMICS_ROOT}
python hermes_home/skills/bioinformatics/literature-param-extraction/scripts/extract_pdf.py "work/papers/<文件名>.pdf" --method pymupdf
```
⚠️ **PyMuPDF 可用性**：PyMuPDF (fitz) 安装在 conda 环境中，但**不在 `execute_code` 的沙箱环境中**。在 `execute_code` 中 `import fitz` 会报 `ModuleNotFoundError`。应改用 `terminal` 来运行提取脚本。

#### 策略 B：手动下载（唯一可靠路径——当用户有权限时）
由于所有自动下载策略均被 Cloudflare 拦截，PDF 需要**用户手动下载**。下载后放入 `work/papers/`，然后用策略 A 提取。
```text
请求用户: "请手动从 <期刊官网链接> 下载 PDF 放到 work/papers/ 下"
```

#### 策略 C：EuropePMC HTML 全文提取（当 PDF 不可用时回退）
`https://europepmc.org/articles/{PMCID}` 的 HTML 页面通常可通过 `requests` 获取（即使 PDF 被 Cloudflare 拦截）：
```python
import requests
resp = requests.get(f"https://europepmc.org/articles/{PMCID}", 
    headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
if len(resp.text) > 10000 and "europepmc" in resp.text.lower():
    # 保存 HTML 并从中提取方法段落
    with open("work/papers/{name}.html", "w") as f:
        f.write(resp.text)
```
从 HTML 中提取 Methods 和 Results 章节，整理参数。

#### 策略 D：PubMed XML 摘要（兜底）
```python
import requests
resp = requests.get(
    f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={PMID}&retmode=xml&rettype=abstract")
```
返回 ~20KB PubMed XML 摘要，至少可提取关键结论和样本信息。

### 已知出版商 PDF 可访问性矩阵（2026-07-13 实测）

| 出版商 | URL 模式 | 状态 | 说明 |
|--------|---------|------|------|
| **PLOS ONE** | `https://journals.plos.org/plosone/article/file?id={doi}&type=printable` | ✅ **可用** | 开放获取，直接返回 PDF（已验证 4.2MB） |
| **Nature/Springer**（已有 PDF） | 从 work/papers/ 读取 | ✅ **可用** | 如用户已手动下载到目录，直接 terminal 提取 |
| **EuropePMC**（PDF） | `https://europepmc.org/articles/{PMCID}?pdf=render` | ❌ **Cloudflare** | 返回 1.8KB HTML captcha |
| **EuropePMC**（HTML） | `https://europepmc.org/articles/{PMCID}` | ✅ **有时可用** | HTML 全文可通过 requests 获取（本 session 成功获取 Franjic 2022 的 28KB HTML） |
| **NCBI PMC**（PDF） | `https://www.ncbi.nlm.nih.gov/pmc/articles/{PMCID}/pdf/` | ❌ **Cloudflare** | 所有子路径均被拦截 |
| **Cell Press (Neuron)** | `https://www.cell.com/neuron/pdf/{S...}.pdf` | ❌ **Cloudflare** | 返回 5.8KB HTML captcha |
| **Science** | `https://www.science.org/doi/pdf/10.1126/science.xxx` | ❌ **Cloudflare** | 返回 5.8KB HTML captcha |
| **Oxford Academic** | `https://academic.oup.com/{journal}/article-pdf/{doi}` | ❌ **Cloudflare** | 返回 5.8KB HTML captcha |
| **Wiley** | `https://onlinelibrary.wiley.com/doi/pdf/{doi}` | ❌ **403 paywall** | 付费墙，非 Cloudflare |
| **MDPI** | `https://www.mdpi.com/{journal}/{vol}/{article}/pdf` | ❌ | 返回 ~2KB HTML 占位页 |
| **BMC** | `https://link.springer.com/content/pdf/{doi}.pdf` | ❌ | 返回 ~120KB HTML 而非 PDF |
| **Sci-Hub** | `https://sci-hub.se/{doi}` | ❌ | 不再可靠 |

### 图片式 PDF（Image-based）检测
部分期刊（如 Cell Research 的 Wang 2022 PDF）的正文是扫描图像而非文本，PyMuPDF 提取后只有 500+ 字节（仅附图说明）。
**检测方法**：提取后检查字符数 < 5,000 → 判定为图片式 PDF → 回退到 EuropePMC HTML 提取或策略 D。

### 提取 PDF 文本（仅当 PDF 为真文本格式时）
```python
import fitz  # 用 terminal 而非 execute_code 运行
doc = fitz.open(pdf_path)
text = ""
for page in doc:
    text += page.get_text()
doc.close()
```
注意：**fitz 模块在 `execute_code` 沙箱中不可用**（输出：`ModuleNotFoundError: No module named 'fitz'`），但在 conda 环境中已安装。始终通过 `terminal` 运行提取。

5. **从文本中提取方法参数**：搜索 Methods 节（通常在正文末尾），提取：
   - 测序平台、分析工具、版本号、基因组版本
   - QC 参数、归一化方法、降维维度、聚类参数
   - DEG 工具、通路分析工具
6. **写入知识库 YAML**：用 Python 的 `yaml` 库或将 YAML 格式写为字符串后 `write_file`
7. **验证**：用 `search_knowledge` 验证写入成功

### 多物种同步更新
构建知识库时，如果文献同时涉及人类和小鼠，建议**同步构建两个物种**的知识库：
- 生物学知识部分：marker 基因名大小写不同（人全大写，鼠首字母大写）
- 关键发现和基因集部分：大部分可共享，仅基因名大小写需转换

### 多物种同步更新
构建知识库时，如果文献同时涉及人类和小鼠，建议**同步构建两个物种**的知识库：
- 生物学知识部分：marker 基因名大小写不同（人全大写，鼠首字母大写）
- 关键发现和基因集部分：大部分可共享，仅基因名大小写需转换

> 参考文件 1：`references/liver_aging_literature_collection_2026-07-07.md` 记录了具体的 PDF 下载 URL 模式、PyMuPDF 提取流程和多物种同步更新示例。
> 参考文件 2：`references/hippocampus_aging_literature_collection_2026-07-13.md` 记录了跨物种（猴vs人）海马体衰老 snRNA-seq 文献收集和 DOI 直链下载策略。

---

## 🗣️ 辩论机制（debate_analysis）

本 skill 在执行后，如果涉及**参数选择、方法决策、结果判断**等不确定环节，**必须**调用工具进行多角色辩论。

### 辩论规则
- **正方 3 位专业编辑**（各自独立，互相看不到）：生物学编辑 / 统计学编辑 / 生信编辑
- **反方 4 位专业编辑**（各自独立，互相看不到，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
- **裁判**：看到所有 7 方论点后给出裁决 + 置信度（高/中/低）
- **上下文隔离**：每个编辑是独立的 LLM API 调用，messages 只包含自己的 prompt
- **分科知识库**：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
- **辩论结果自动归档**到 results/.../log/debate_*.json

### 触发场景
- 参数选择有多个合理选项时（如分辨率 0.4 vs 0.6 vs 0.8）
- 结果可能受方法选择影响时（如不同注释方法给出不同结果）
- 生物结论需要验证可靠性时
- QC 阈值不确定时（如 MT% 阈值 10% vs 15% vs 20%）

### 不触发场景
- 参数有明确知识库推荐且无争议时
- 纯计算步骤（如保存文件、读取数据）

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| human | hippocampus | aging | 2026-08-12 | - | - | - |  |
