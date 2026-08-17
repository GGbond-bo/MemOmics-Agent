# Case Study: 人类海马 ATAC-seq 数据搜索

## 请求
"帮我下载人类海马的ATAC数据"

## 搜索回退链（实际执行路径）

### Step 1: ENCODE
- 查询: `query_ncbi(db="gds", query="hippocampus ATAC-seq human")` → 0 结果
- 放宽到 "hippocampus" → 246 个实验，其中 4 个 snATAC-seq 全是**小鼠**，无人类
- 结论: ENCODE 人类海马 ATAC 数据稀缺 → 立刻回退到 GEO

### Step 2: GEO
- 首次尝试 API 连接失败 → 换 HTTPS URL 重试
- `search_geo("human hippocampus ATAC-seq single cell")` → 17 个候选
- 关键发现: GSE278576 — "Epigenetic and 3D genome reprogramming during the aging of human hippocampus" (Science 2026)
  - 40 ATAC + 40 RNA 样本，40 个独立供体
  - 数据格式: Fragment 文件 (.tsv.gz + .tbi.gz) → 可直接喂 ArchR `createArrowFiles()`
  - 衰老方向 — 与猕猴海马衰老 ATAC 完美匹配

### Step 3: 验证
- `get_geo_details("GSE278576")` 确认物种/组织/样本数
- PubMed: PMID 42490474 确认发表信息

## 备选数据集

| GSE ID | 样本 | 说明 |
|--------|:---:|------|
| GSE147672 | 162 (26 hippocampus) | AD/PD 表观基因组，多数 bulk |
| GSE226529 | 6 | AD vs Control 海马 bulk ATAC |
| GSE131256 | 3 | 胎脑海马 ATAC（发育，非衰老） |

## 经验教训

1. ENCODE 对组织器官特异性强的数据不一定全 → 无人类结果就立刻跳 GEO，别反复尝试
2. GEO API 可能连接失败 → 备选 HTTPS eutils URL 要准备好
3. 第一轮搜索结果中混入了 GSE278576 — 如果不是人工识别出这是人类海马，很容易漏掉
4. 搜索时用 "aging" 作为方向关键词可以同时命中和衰老相关的研究
