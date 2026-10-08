# ArchR 1.0.3 `getGroupSE(TileMatrix)` 三层坑 — 专利 L3 age-DA 实测 (2026-09-03)

专利人 40 样本海马 ATAC（hg38）vs 猴 20 样本（T2T-MFA8v1.1）做 tile 级 age-DA（Pearson cor with age），
`getGroupSE(useMatrix="TileMatrix", groupBy="individual")` 连续踩了三个坑，按顺序排查。

## 坑 1：`divideN=TRUE` 默认 → "All tiles filtered out!"

```r
se <- getGroupSE(proj, useMatrix="TileMatrix", groupBy="individual", scaleTo=NULL)  # ❌
```
报错 `Error: All tiles filtered out! Check scaleTo=NULL or lower threshold.`，
且下游 `rowSums(cnt) >= 2*ncol(cnt)` 一个都不满足。

**根因（ArchR 1.0.3 源码确认）**：`getGroupSE` 默认 `divideN=TRUE`，
```r
if (divideN) {
    groupMat <- t(t(groupMat)/as.vector(nCells))   # counts 除以组内细胞数
}
```
返回的是**每细胞平均计数**（小数、量级 0.x~几），针对原始 counts 的 `>= 2*ncol` 过滤阈值全灭。

**修复**：`getGroupSE(..., scaleTo=NULL, divideN=FALSE)` 才返回原始总 counts。
`scaleTo=NULL` 本身合法（默认就是 NULL），问题只在 divideN。

## 坑 2：`rowRanges(se)` 返回空 → "rowRanges mismatch: length=0 vs nrow=6085841"

```r
rr <- rowRanges(se)  # ❌ length=0！
```
**根因（源码第 69-70 行铁证）**：
```r
se <- SummarizedExperiment::SummarizedExperiment(assays = assayList,
    colData = cD, rowData = featureDF)   # 只填 rowData，不填 rowRanges
```
坐标在 `rowData(se)`（featureDF），`rowRanges` 在 1.0.3 是空的——不是数据坏了。
防御检查（mismatch 报错）恰好抓到了取数位置写错，不是数据问题。

**修复**：`fr <- as.data.frame(rowData(se))`，前 3 列 chr/start/end。

## 坑 3（最深）：`rowData(se)` 第 2 列也不是坐标——是 tile index！

修完坑 2 后导出 CSV，坐标长这样：
```
human: "chr1",1587,793000    monkey: "NC_088375.1",41,20000
       "chr1",1588,793500            "NC_088375.1",42,20500
```
`start` 列是连续整数（tile 编号），`end` 列 = (idx-1)×500 是**伪坐标**，根本不是碱基坐标。
拿这个直接 liftover 会全部错位、M3 跨物种比较全废。

**判定方法（awk 扫染色体切换点，看 index 是否重置）**：
```bash
awk -F',' 'NR>1 {chr=$1; gsub(/"/,"",chr); start=$2+0;
  if(chr!=prev){if(prev!="") printf "%s 末 idx=%d → %s 首 idx=%d\n", prev, lastidx, chr, start; prev=chr}
  lastidx=start}' human_ageDA_all.csv | head -30
```
实测两侧均**每条染色体独立重置**：human chr1 首=1587（前 1586 个低覆盖 tile 被过滤）、
chr10 首=93、chr11 首=391、chr9 首=21；monkey NC_088376.1 首=41、NC_088377.1 首=43。
→ 是"每染色体独立 1 起"的 tile index，不是跨染色体全局编号。

**修复（不需要重跑 getGroupSE！r/p/q 统计列完全正确，只换坐标列）**：
```r
d[, real_start := (start - 1) * 500 + 1]    # 500 = tile 宽（bp）
d[, real_end   := start * 500]
```
验证：human idx=1587 → chr1: 793001–793500；monkey idx=41 → NC_088375.1: 20001–20500。
（修正脚本见 Proven Scripts `fix_ageDA_coords.R`，data.table fread/fwrite 就地改 6 文件几秒完成。）

## 附加事实：猴侧 q<0.1 显著 = 0 是真实结果

20 样本 age-DA、530 万 tile 全表 FDR，q<0.1 显著 tile 恰好 0 个——不是代码 bug。
20 样本检验力 + 百万级多重检验校正下完全可能全灭。**下游秩保守（rank-conservative / Smyth rank）
跨物种比较用的是全表 r 值的秩，不需要显著子集**——全表 all.csv 才是核心输入，up/down 只是富集/注释用。

## 修复后输出核对清单

1. `Tiles: before=6,085,841 -> after=几十万级`（divideN=FALSE 生效的证据）
2. `print(head(out))` 坐标应为 `chr1 793001 793500` 这种 500bp tile 格式
3. human up/down 数十~数百级（q<0.1）；monkey 0 属正常