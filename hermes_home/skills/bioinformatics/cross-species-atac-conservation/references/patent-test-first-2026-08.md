# 专利测试版先行工作流（2026-08-08 用户确认）

## 核心决策（用户原话）

"我的猴子数据有 20 多个，但只下载 3 个测试。人也只挑几个测试，按照专利计划测试，
如果效果可以，就在自己集群按你的方法全面完成。"

**用户的工作流偏好 = 测试版先行**：
1. 本机用少量样本跑通全流程 + 验证结果生物学合理
2. 效果好 → 用户在集群（数据全量：63 猴 Arrow + 40 人样本）全面跑
3. 测试版不可当正式专利实施例（个体数不足），但足以验证"方法可跑通 + 结果合理"

## 测试版数据（2026-08-08 选定）

| 侧 | 数据 | 规模 |
|----|------|------|
| 猴 | Y3_Hip_1 / Y3_Hip_2 / O1_Hip_1（Arrow，Phase 1-6 已完成）| 35,902 cells |
| 人 | **hc78=20M + hc5579=25F（Young）+ hc98=82F + hc9=95F（Old）** | 29,357 cells |

**人侧挑样本标准**：年龄跨 20→95（≥60 年跨度，对比清晰）+ QC 后细胞数 5,800-9,000（稳健）
+ 与猴 Y/O 对齐（2 年轻 + 2 老年）。

## GSE278576 年龄映射获取（关键！）

**series matrix 不含 age**——`GSE278576_series_matrix.txt.gz` 只有 `tissue` + `donor id` 两列 characteristics。

年龄在官方 metadata 文件里：
```
https://ftp.ncbi.nlm.nih.gov/geo/series/GSE278nnn/GSE278576/suppl/GSE278576_hippocampus_RNA_seurat_object_filtered_cells_metadata.tsv.gz
# 12MB, 295K 细胞级行, 列含 Age / Gender / age_group / subclass
# 按 orig.ident 分组取 Age 唯一值 = donor→age 映射
```
40 donor 完整映射已存：`results/memomics-1c1890da/donor_age_map.json`（age 20-95，4 年龄组）。

## P0 参数（复刻猴侧保证对比有效）

```
ArchR hg38 + TileMatrix + IterativeLSI(dims 1:30, resolution 0.5)
QC 已在 40 样本批量完成（minTSS=4, minFrags=3000, filterRatio=2）
差异可及性: getMarkerFeatures(wilcoxon, bias=TSS+nFrags) cutOff FDR<=0.05 & |Log2FC|>=0.5
```

## 持久化产物（后续会话恢复入口）

- `results/memomics-1c1890da/PATENT_TEST_PLAN.md` — 完整测试版计划（流程/参数/红线/里程碑）
- `results/memomics-1c1890da/donor_age_map.json` — 40 donor 年龄表
- `results/memomics-1c1890da/task_plan.md` — Phase 进度（P0 in_progress）
- 脚本/产出：`results/memomics-1c1890da/patent_test/`

## 跨物种对比流程（专利核心）

```
P0 人侧 merge+LSI+UMAP+聚类（复刻猴侧参数）
P1 人侧 Young vs Old DA tiles
P3 L1 序列保守（liftover 食蟹猴T2T→hg38 + phastCons + JASPAR）
   L2 可及性保守（peak overlap Jaccard + 信号 Spearman + species×age 动态）
   L3 TF 结合保守（footprinting HINT-ATAC/TOBIAS + motif 富集一致性）
P4 CRECS 综合评分（进化锚点校准权重）→ A/B/C/D 分类 → B 类 CRE 检出
P5 BNIP3 一正一反验证
P6 专利文档（交底书 + 独权草案 + 实施例数据）
```

## Windows 执行注意（本会话实测）

- R 4.5.3 在 execute_code/Python subprocess 下 segfault（RC=0xC0000005）→ **验证 R 语法用 bash 直接 `Rscript -e 'parse(...)'`**，不要用 Python subprocess f-string（有 `\p` 转义坑）；`Rscript --vanilla -f temp.R` 在 Python subprocess 下也可能 segfault，bash 直接调用最稳
- 后台任务用 `terminal(background=true, notify_on_complete=true)` + 独立 heartbeat 脚本（单实例锁 + 停滞检测）
- **验证脚本勿用 os.unlink 删除临时文件**——触发 Hermes 删除保护拦截（用 write_file 到 tempfile 路径 + 只验证不删除，或留给清理）
