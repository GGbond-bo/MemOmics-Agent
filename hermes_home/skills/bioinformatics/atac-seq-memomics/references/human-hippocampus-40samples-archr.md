# GSE278576 人海马 40 样本 ArchR 处理（猴参数复现）— 2026-08-07

## 背景：为什么用 ArchR 而非官方 SnapATAC2

用户专利方向是**跨物种 CRE 保守性评估（猴→人）**。猴侧海马 ATAC 已用 ArchR 1.0.3
跑完整流程（`E:/专利/ArchR_Output/`，3 Arrow：O1_Hip_1, Y3_Hip_1/2，21 clusters）。
人侧若用官方 SnapATAC2 流程，两侧分析管线不一致，无法公平比较 → **用户明确要求
人侧也走 ArchR + 猴侧完全相同参数**，保证跨物种可比性。

⚠️ 不要因为 gse278576 skill 写的官方流程是 SnapATAC2 就默认走官方管线 —
**先问用户要哪个管线**。本专利项目用户已明确选 ArchR。

## 数据状态（2026-08-07 磁盘实测）

- 路径：`E:\专利\Human_Hippocampus_ATAC\fragments\`
- **40/40 `*_atac_fragments.tsv.gz` 全部下载完成**
- **40/40 `.tbi.gz` 索引齐全**（无缺失——早期 hc78 缺索引问题已解决）
- 大小 0.96–5.97 GB/样本（平均 ~2.5GB）
- 头部 `# id=hcNNN_deep` = cellranger-arc 注释格式，ArchR 可直接读
- E 盘 666GB 可用；40 个 Arrow 预计 80–150GB，够

## 年龄分布 = 官方 4 组 × 10（Table_S1 确认）

| 年龄组 | Donor（年龄） | 数量 |
|--------|---------------|:---:|
| 20-40 | 77(20), 78(20), 5579(25), 76(26), 29(28), 6052(28), 5614(31), 13344(33), 935(38), 937(38) | 10 |
| 40-60 | 1134(41), 13414(41), 5021(43), 5087(44), 1745(46), 4781(46), 81(48), 5610(50), 5551(54), 6021(55) | 10 |
| 60-80 | 13394(65), 73787(66), 46426(68), 1265(69), 8(69), 1271(71), 1153(75), 1203(75), 69984(75), 1216(79) | 10 |
| 80-100 | 98(82), 12(83), 11(86), 73(86), 19(87), 26(89+), 40(89+), 212191(89+), 35(89+), 9(89+) | 10 |

**Table_S1 路径**：`E:\专利\Human_Hippocampus_ATAC\papers\suppl_media2\Supplemental Tables S1-S24\Table_S1.tsv`
（47 行 donor，其中 40 个有 10x multiome = ATAC 样本）

## 🔴 80-100 岁组是必须，不是可选

用户曾问"真的要 80-100 岁的吗？"——答案是**必须保留**，三个理由：

1. **官方分析是连续年龄 Pearson 相关**（pseudobulk CPM vs age，非 Young vs Old 分组）。
   早期 pilot 只有 9 个 Young 样本 → 年龄跨度窄 → FDR 全空、统计力不足。
   只有覆盖全年龄谱（20→89+）才有统计力。
2. **专利要 species × age 交互**（mixed model SDI）→ 猴侧已有 4 年龄组，
   人侧必须对应完整年龄谱才能做可代替性评估。
3. **这批 80-100 岁供体 Braak Stage 全部 0-II（无 AD 病理）** → 是"健康衰老"样本，
   不是 AD 混杂样本，正是衰老研究理想最老端。

## 猴参数 → ArchR 映射（人侧照抄）

| 猴子论文参数 | ArchR 调用 |
|-------------|-----------|
| TSS enrichment < 4 移除 | `createArrowFiles(minTSS=4)` |
| fragment numbers < 3,000 移除 | `createArrowFiles(minFrags=3000)` |
| addDoubletScores + filterRatio=2 | `addDoubletScores()` + `filterDoublets(filterRatio=2)` |
| merge all libraries | `ArchRProject(ArrowFiles=...)` 自动合并 |
| 500-bp genomic tiles | `addTileMatrix(tileSize=500)` |
| iterative LSI | `addIterativeLSI()` |
| Seurat clustering res 0.8 | `addClusters(resolution=0.8)` |
| snRNA-seq marker 注释 | `addMarkers()` / marker 基因 |

## 环境（2026-08-07 实测可用）

- R 4.5.3 + ArchR 1.0.3 + Seurat 5.5.1（`"C:/Program Files/R/R-4.5.3/bin/Rscript.exe"` + `.libPaths(c("USER_R_LIBS/R-4.5.3", .libPaths()))`）
- **BSgenome.Hsapiens.UCSC.hg38 = TRUE** ✅
- chromVAR = TRUE, motifmatchr = TRUE ✅
- EnsDb.Hsapiens.v86 = FALSE（如需 TSS 注释另装）
- 人侧用标准 UCSC hg38（`addArchRGenome("hg38")`），**比猴侧自定义 T2T 基因组简单得多**

## 计划（用户确认后执行）

- **P1**：逐个 `createArrowFiles`（40 样本，minTSS=4, minFrags=3000）—— 单样本 15-60min，串行 10-30h
- **P2**：`addDoubletScores` + `filterDoublets(filterRatio=2)`
- **P3**：保存过滤后的 Arrow 文件（用户明确要的产出）
- **P4**（待确认）：merge → addTileMatrix(500bp) → addIterativeLSI → Seurat res 0.8

⚠️ 40 样本串行 = 长任务 → 后台进程 + 心跳监控 + error_scanner，逐样本验证输出。

## ⚠️ 批处理执行方式（2026-08-07 故障修复后的标准做法）

**禁止 cmd.exe //c + bat 方式跑 R 脚本**（MSYS 转义 bug）：
- `cmd.exe //c "E:\\MemOmics-Agent\\results\\...\\${local_bat}"` → MSYS 把 `\r` 转义吃掉 → `'un_GSM...bat' 找不到`
- `cmd.exe /c "\"$RSCRIPT\" \"$SCRIPT\" ..."` 嵌套引号 → 同样失败（9 样本全 FAIL exit=1 no CSV）

**✅ 正确方式：bash 直接调 Rscript.exe**（MSYS bash 可直接执行 Windows exe）：
```bash
RSCRIPT="/c/Program Files/R/R-4.5.3/bin/x64/Rscript.exe"
"$RSCRIPT" "E:/.../create_arrow_qc.R" "$s" > "batch/logs/${s}.log" 2>&1
```
中文路径（E:/专利/...）在 R 脚本内部处理，bash 只传 ASCII 参数 → 无编码问题。

**并发根因（严重）**：monitor 自动重启机制 + 手动启动双源 → 3 个 run_serial.sh + 5 个
monitor_serial.sh 并发 → ArchR tmp 目录竞争（已知 bug）→ 全部失败。修复：
1. 彻底清理：`cmd.exe /c "taskkill /F /IM Rscript.exe /T"` + `taskkill /F /IM bash.exe /T`
2. 清理锁文件（.run_serial.pid/.monitor.pid 可能 stale）
3. 单实例启动 + 单实例锁，monitor 停用（用 terminal background+notify_on_complete 替代）

参考实现：`MEMOMICS_HOME/results/memomics-1135ed52/batch/run_serial_v2.sh`

## 交叉引用

- 猴侧 ArchR 输出：`E:/专利/ArchR_Output/`（project_clustered.rds 21 clusters）
- 猴侧 Arrow：`E:/专利/ArrowFiles/`（O1_Hip_1, Y3_Hip_1, Y3_Hip_2）
- 官方 cCRE 复用路径（472,859 cCRE）→ 见 gse278576-atac-aging-comparison skill
- 公共 GEO fragments 导入一般方法 → `public-geo-fragment-import.md`
