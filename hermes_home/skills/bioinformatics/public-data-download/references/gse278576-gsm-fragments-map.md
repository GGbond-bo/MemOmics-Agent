# GSE278576 GSM 级 fragments 映射表（已验证 2026-08-03）

> 背景：用户想下载 GSE278576（人海马衰老多组学，Science 2026）的 40 个 ATAC 样本 fragments
> 做跨物种 CRE 保守性专利（猴海马 ATAC vs 人海马 ATAC）。
> 用户按 GSE supplementary 页找 fragments 找不到 → 根因：fragments 在 GSM 级，不在 GSE 级。

## 关键结构认知（GEO 数据两级存放）

```
GSE278576 supplementary 页（用户看到的）:
  ├── GSE278576_ATAC_CA1_age20-40.bw  (121M)  ← 聚合信号（按海马亚区×年龄组）
  ├── GSE278576_ATAC_Astro.bw         (302M)  ← 聚合信号（按细胞类型）
  ├── GSE278576_RAW.tar               (89.2G) ← ⛔ 千万别下，太大
  └── GSE278576_hcXX_raw_feature_bc_matrix.h5  ← Multiome 矩阵

每个 GSM 样本页面（fragments 在这里!）:
  https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM8549615
  ├── GSM8549615_hc77_atac_fragments.tsv.gz       (1.31 GB) ← ArchR 直接输入
  └── GSM8549615_hc77_atac_fragments.tsv.gz.tbi    (索引，ArchR 必需)
```

## 40 个 ATAC 样本的 GSM 映射（全部通过 NCBI esearch 验证）

| hc 编号 | GSM 编号 | hc 编号 | GSM 编号 |
|---------|----------|---------|----------|
| hc8  | GSM8549639 | hc13344 | GSM8549622 |
| hc9  | GSM8549654 | hc13394 | GSM8549635 |
| hc11 | GSM8549647 | hc13414 | GSM8549626 |
| hc12 | GSM8549646 | hc1745 | GSM8549629 |
| hc19 | GSM8549649 | hc212191 | GSM8549652 |
| hc26 | GSM8549650 | hc46426 | GSM8549637 |
| hc29 | GSM8549619 | hc4781 | GSM8549630 |
| hc35 | GSM8549653 | hc5021 | GSM8549627 |
| hc40 | GSM8549651 | hc5087 | GSM8549628 |
| hc73 | GSM8549648 | hc5551 | GSM8549633 |
| hc76 | GSM8549618 | hc5579 | GSM8549617 |
| hc77 | GSM8549615 | hc5610 | GSM8549632 |
| hc78 | GSM8549616 | hc5614 | GSM8549621 |
| hc81 | GSM8549631 | hc6021 | GSM8549634 |
| hc98 | GSM8549645 | hc6052 | GSM8549620 |
| hc935 | GSM8549623 | hc69984 | GSM8549643 |
| hc937 | GSM8549624 | hc73787 | GSM8549636 |
| hc1134 | GSM8549625 | hc1203 | GSM8549642 |
| hc1153 | GSM8549641 | hc1216 | GSM8549644 |
| hc1265 | GSM8549638 | hc1271 | GSM8549640 |

注：GSM8549615-8549654 是 ATAC 样本连续段；另有 GSM8549692-8549694 是 RNA 样本（hc212191_RNA/hc35_RNA/hc9_RNA），勿混淆。

## 已验证的下载 URL 模板

```bash
# fragments 数据（Content-Length 实测 1.31GB / 2.10GB ...）
https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM8549nnn/GSM8549615/suppl/GSM8549615_hc77_atac_fragments.tsv.gz
# 索引（配套必须）
https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM8549nnn/GSM8549615/suppl/GSM8549615_hc77_atac_fragments.tsv.gz.tbi
```

## URL 验证协议（交付清单前必须做）

```bash
# 1. 拉全 GSM 列表（不要手猜编号）
curl -k -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=gds&term=GSE278576[ACCN]&retmax=100&retmode=json"
# 或 query_ncbi(db="gds", query="GSE278576[ACCN] AND ATAC", max_results=50)

# 2. 每个 URL curl -sI 验证（200 OK + Content-Length 合理）
curl -k -sI "https://ftp.ncbi.nlm.nih.gov/geo/samples/GSM8549nnn/GSM8549615/suppl/GSM8549615_hc77_atac_fragments.tsv.gz"
# → HTTP/1.1 200 OK, Content-Length: 1309905677 (1.31 GB)
```

## 教训总结

1. GEO 聚合文件（bw/h5/tar）在 GSE supplementary 页；**原始 fragments 按样本在 GSM 页**
2. 交付下载清单前必须 `curl -sI` 验证 URL 真实存在，否则用户审计时信任崩塌
3. 用户网络带宽 ~6KB/s：40 样本 × 1-3.7GB ≈ 52GB 无法自动下载，需用户手动或换网络环境
4. 先下 4 个样本（2 年轻 hc77/hc78 + 2 老年 hc5579 等）做 pilot 验证再全量
