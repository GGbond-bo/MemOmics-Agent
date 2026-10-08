# NCBI E-utilities 批量基因查询模式（全量 ortholog + hg38 坐标）

> 来源：2026-08-31 猴侧全量锚定 `P3_L1_data/gene_anchor_ortholog_full.py`（53.8万 monkey peaks → 基因锚定 → human ortholog → hg38 坐标）。
> 解决了旧版"逐 id 串行 efetch（0.3-0.4s sleep）"在 **53.8 万 peaks 全量**下不可行的瓶颈：全量唯一猴 GeneID 数万 → 逐 id = 数小时；批量 200/批 = 约 200 次请求，10-30 分钟完成。

## 1. 批量 efetch 查 gene ortholog（200 id/批）

```python
url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?' + urlencode({
    'db': 'gene', 'id': ','.join(map(str, batch)), 'retmode': 'xml',
    'tool': 'MemOmics', 'email': 'memomics@test.org'})
```
- **必须带 UA header** `{'User-Agent': 'Mozilla/5.0 (MemOmics)'}`，否则可能被拒
- 批间 sleep 0.8s；批量内 200 id 的 URL 长度没问题（9 位数 id × 200 ≈ 2KB）

### ⚠️ 格式陷阱 1：`Gene-track_geneid` 是**元素**，不是属性
- ❌ 错误正则 `<Gene-track[^>]*geneid="(\d+)"` → 匹配 0 个（实测批量返回全空）
- ✅ 正确：按 `<Entrezgene>(.*?)</Entrezgene>` 顶层块分块（`re.S`），每块内取
  `<Gene-track_geneid>(\d+)</Gene-track_geneid>`，然后在该块内找
  `'Orthologs from Annotation Pipeline'` 段落（`seg[idx:idx+12000]`），再正则提取
  `Dbtag_db>GeneID` + `Other-source_pre-text`(symbol) + `Other-source_anchor`(物种，过滤 'human')
- **ncRNA/假基因无 Orthologs 段落 → 返回空列表是正常**，不是 bug（实测 141407760 ncRNA 无 ortholog，4/5 有效）

## 2. 批量 esummary 查 hg38 坐标（200 id/批）

```python
url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?' + urlencode({
    'db': 'gene', 'id': ','.join(map(str, batch)), 'retmode': 'json', ...})
# 坐标在 data['result'][str(gid)]['genomicinfo'][0]：chrloc/chrstart/chrstop（GRCh38）
```

### ⚠️ 格式陷阱 2：负链基因返回 chrstart > chrstop（NCBI 按转录方向给坐标）
- 实测 ZNF692 = `chr1:248859084-248850007`（start > end）
- ⛔ 必须 min/max 归一化，否则下游 `if hend <= hstart: continue` 会**静默丢弃全部负链基因**
- ✅ `result[str(gid)] = (chr, min(s0,e0), max(s0,e0))`
- 跨物种 frac 映射的两侧语义：猴 feature_table 恒 start<end，human 侧 min/max 后也是低→高，
  两侧都用"低坐标→高坐标比例"，方向一致（负链生物学方向略偏但两侧误差同源，可复现优先）

## 3. 为什么不用本地 ortholog 文件

- NCBI 官方 `gene_orthologs.gz`（tax_id=7070 猴 全量关系表）**实测下载 52MB 处 gzip EOF 截断**
  （只有 7.6M 行，非全量）→ 本地解析不可靠
- 批量 efetch/esummary 结果实时、覆盖 200 基因/请求，全量 10-30 分钟，足够快

## 4. 跨物种基因锚定链路参数（T2T-MFA8v1.1 → hg38，无 chain fallback）

```
monkey peaks (NC_xxx) 
  → ±2kb 基因体 overlap（feature_table：col6=genomic_accession 作 key，col7/8=start/end，
    col14=symbol，col15=GeneID，仅 feat=='gene' 行；注意不是 col5 chromosome）
  → unique 猴 GeneID → 批量 efetch ortholog（只看 human 物种）
  → unique human GeneID → 批量 esummary 坐标（min/max 后为 GRCh38）
  → frac = (peak_mid - monkey_gene_start)/(monkey_gene_len)
  → hg38_pos = human_start + frac*(human_len) ± 2500bp 窗口打分
```

- 命中率参考：猴海马 peaks 对 ±2kb 基因体 overlap 约 **72%**（144/200 小样实测 2026-08-31）；全量版实测 343,617/538,420（63.8%）
  食蟹猴 T2T-MFA8v1.1 feature_table 共 40,596 个 gene 行（22 条染色体）
- 每 peak 多基因 overlap 时取排序后第一个（最近）

### ⚠️ 格式陷阱 3（最隐蔽，2026-08-31 全量版实测）：`result` dict 的 key 类型必须 store/query 一致，否则静默 0 输出
- ❌ 第一版 `esummary_coords` 存 `result[str(gid)] = ...`，而 main() 查询用 `if hgid in coords`（hgid 是 **int**）→
  Python `123 in {'123': ...}` 恒为 False → 日志一路"正常"（efetch 26501、esummary 16158 coords），
  但最终 `monkey_peaks_hg38_map.csv` **只有表头 0 行**、`human_ortholog_hg38_full.csv` 坐标列全空——**exit 0 ≠ 产物非空**
- ✅ 修复：统一 key 类型——`result[int(gid)] = ...`（NCBI JSON 返回 key 是字符串，用 `res.get(str(gid))` 读，但**自己的 result dict 存 int**）；或查询时也 `str(hgid)`
- ✅ 修 bug 后先小批量验证再全量：3 个 gid 断言 `gid in dict(by int)` True / `(by str)` False
- ✅ **缓存提速模式**：中间结果落盘（`monkey_human_orthologs_full.csv` ortholog 表 26502 行已验证），修 bug 后只重跑 esummary（~2min）跳过 20min efetch 全量——除非 ortholog 逻辑本身变了
- 修复版脚本：`E:/专利/P3_L1_data/gene_anchor_ortholog_fix.py`（复用缓存 + int key + 只重跑 esummary+frac 映射）

> ⛔ **验证铁律**：任何后台"完成"任务，除读日志尾部外**必须核对产物实际行数/文件大小**（`wc -l` + `ls -la`）——日志级成功可能已被 silent 逻辑 bug 架空。

## 5. 全量锚定的性能预期

- feature_table 载入：~30s（gzip 解压 + 4 万行解析）
- 53.8 万 peaks overlap 查询：二分查找每染色体基因列表（脚本内 `hits_in` 二分），分钟级
- efetch：唯一猴 GeneID N 个 → ceil(N/200) 次请求；esummary 同量级
- 总计 10-30 分钟，后台 + notify_on_complete 即可

## 6. 脚本位置

- `E:/专利/P3_L1_data/gene_anchor_ortholog_full.py`（全量版，2026-08-31）
- 输出：`monkey_peaks_hg38_map.csv`（monkey peak → hg38 窗口）+ 
  `monkey_human_orthologs_full.csv` + `human_ortholog_hg38_full.csv`
- 下游打分：`l1_full_peaks_monkey_v4.py`（NBG=1000 + BH-FDR，同 human v4 逻辑）