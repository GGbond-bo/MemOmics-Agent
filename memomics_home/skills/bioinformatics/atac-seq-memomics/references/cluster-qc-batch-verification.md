# 存疑 cluster 验证：QC + batch 检查（勿凭 marker 数量判"噪声"）

2026-08-27 人 40 样本海马 ATAC 实证教训。用户对"细胞量很大却是噪声"的判断提出质疑，真实 QC 数据推翻该判断——标记为噪声前必须做以下验证。

## 触发场景

`getMarkerFeatures` 输出中某 cluster marker 极少 / 全是 OR 嗅受体 / ncRNA，但**细胞量很大**（数千到数万）。典型：C25 仅 5 marker 全 OR（OR7A5/OR2T4）、C28 仅 3、C29 仅 1 ncRNA。此时**禁止**凭"marker 少 + 无脑 marker"判垃圾群。

## 核心教训

**marker 数量少 ≠ 噪声群。** marker 只反映"该群与其它群差异最大的基因"，大量真实群因 peak 质量/分辨率不足而 marker 极少。判垃圾群必须看**独立于 marker 的真实 QC 证据**。

## 验证步骤（ArchRProject rds 自带 cellColData，无需 Arrow 文件）

### ① 逐群 QC（aggregate median）
```r
d <- as.data.frame(human@cellColData)
d$nFrags_log10 <- log10(d$nFrags + 1)
agg <- aggregate(cbind(TSSEnrichment, nFrags_log10, DoubletScore,
                       PromoterRatio, BlacklistRatio) ~ Clusters, data = d, FUN = median)
```
判读：
- **TSS ≥ 中位（甚至更高）+ DoubletScore≈0 + nFrags 正常 → 不是低质量群**（C25/C28 TSS 11.4/11.3 vs 全体中位 9.8）
- 用户"plotGroups 看 TSS 还挺高"是有效反驳：TSS 高 = 核完整、转座酶偏好正常

### ② batch 效应检查（决定性判据）
```r
for (cl in c("C25","C26","C28","C29")) {
  sub <- d[d$Clusters == cl, ]
  smp <- sort(table(sub$Sample), decreasing = TRUE)
  cat(sprintf("%s n=%d top2: %s (%.0f%%) | %s (%.0f%%)\n",
              cl, nrow(sub), names(smp)[1], smp[1]/nrow(sub)*100,
              names(smp)[2], smp[2]/nrow(sub)*100))
}
```
**判据：top2 样本占该群 ≥90% → batch 伪影群。** C25 实证：99% 细胞来自 hc13344+hc73 两样本（2207+1817=4024/4066）→ 该两样本测序/比对污染形成独立群，marker 全 OR 嗅受体是佐证（OR 基因组重复区 mappability 假 peak）。**这类群可排除**（Ambig_excluded）。

### ③ PromoterRatio 解读（识别神经元混合群）
- **低 (~0.08-0.10) = 神经元特征**：开放染色质在增强子不在启动子
- **高 (~0.19) = 胶质/ODC 样**：启动子区开放为主
- C26 PromoterRatio 0.096（低）+ marker 深查含 **GAD2/SLC17A6/FOXP2/CALB1 真实神经元基因** + 混 OR/KRTAP/IFNA 异位基因 → **真实神经元混合群，不是噪声**（保留重聚类）

### ④ marker 深查注意格式
- `getMarkerFeatures` 输出 CSV 的 **`group` 列是数字 (1-30)，`group_name` 才是 C1-C30** — 勿用 "C25" 匹配
- 部分 cluster **完全没有 marker 条目**（C24/C27 实证，getMarkerFeatures 时被过滤）→ 单看 markerList 会漏判这些群

## 决策矩阵（2026-08-27 定稿 + L1 辩论 modify/high 通过）

| 条件 | 判定 |
|------|------|
| QC 正常 + 样本分布正常 + marker 明确 | 真实群（保留） |
| QC 正常 + **top2 样本 >90%** | **batch 伪影群**（排除 / Ambig_excluded） |
| QC 正常 + 样本正常 + marker 少/混合污染 | **Ambig_requery**（保留，重聚类 res=1.5 复查） |
| marker 全 OR + top2 样本 >90% | 伪影排除（C25 实证） |
| 通用 QC 阈值 | minTSS≥8, maxDoubletScore<0.15, minFrags≥1000 |

## 其余坑

- **注释写回**：`proj$cellType8 <- anno_map[...]` + saveRDS 即可（cellColData 层面，不需 Arrow）。沙箱写白名单外的用户目录（E:/专利/patent）会被拒 → 先存 `results/<sid>/taskX/` 再让用户复制回专利目录，或配置 MEMOMICS_ALLOWED_WRITE_ROOTS 放行
- **Arrow 路径**：用户给的 rds 里 ArrowFiles 可能指向远端集群（/hwfssz3/...）→ 本机不存在 → 无法 getAvailableMatrices/重算 GeneScore，但 cellColData 验证完全不受影响
- **猴侧 rds 常已带 predictedAnno**（label transfer 预测注释），检查 `colnames(cellColData)` 若有 predictedAnno → 已是精细注释（ExN 亚型/InN 4 类/胶质全套），无需重注释
- **跨物种注释前先检查两侧已有列**：人侧可能无 predictedAnno（需要注释），猴侧已有 → 决定工作重心

## 8 大类注释映射（人 30 cluster → cellType8，可复用）

```r
anno_map <- c(
  "C1"="ExN","C2"="ExN","C3"="ExN","C4"="ExN","C5"="ExN","C6"="ExN",
  "C17"="ExN","C18"="ExN","C19"="ExN",
  "C7"="Astro","C8"="Astro","C9"="Astro","C10"="Astro","C11"="Astro","C12"="Astro",
  "C14"="InN","C15"="InN","C16"="InN",
  "C20"="Micro","C22"="Micro","C23"="Micro",
  "C21"="VS", "C30"="ODC",
  "C13"="Ambig_excluded", "C25"="Ambig_excluded",   # HOX 伪影 + batch 伪影
  "C26"="ExN_InN_mix_requery",                       # 真实神经元混合，保留重聚类
  "C28"="Ambig_requery", "C29"="Ambig_requery",
  "C24"="Unresolved", "C27"="Unresolved")            # markerList 无显著 marker
human$cellType8 <- as.character(anno_map[as.character(human$Clusters)])
```