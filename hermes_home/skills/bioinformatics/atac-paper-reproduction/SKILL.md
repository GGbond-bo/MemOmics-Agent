---
name: atac-paper-reproduction
description: >
  ATAC-seq 论文对比/年龄相关流程复现。核心原则：官方路径优先——去论文官方代码仓库
  （GitHub/Zenodo）、官方补充表（Table_S*）、GEO 找方法，不自行发明。
  关键技巧：官方补充表含 cCRE/peak 全集时直接复用坐标做片段计数，跳过本地
  peak calling（免装 MACS3/snapatac2）。覆盖 cellranger-arc fragments 格式、
  Windows 环境限制、pseudobulk 年龄 Pearson 相关前置检查。
  触发词：论文复现 / 对比流程 / 官方路径 / official code / ATAC 复现 /
  fragments 年龄相关 / cCRE 复用 / 复现某篇文章的流程 / GSE... ATAC
trigger_level: YEL 讨论触发
version: 1.0.0
prerequisites:
  python_packages: ["pandas", "scipy", "statsmodels", "matplotlib", "numpy"]
  system_requirements: "Python 3.12+; 官方补充表(Table_S*); cellranger-arc fragments.tsv.gz"
---

# ATAC-seq 论文对比流程复现

## ⛔ 术语澄清铁律（用户 2026-08-04 纠正：'虽然我说错了，但是你没有纠错'）

用户说"对比流程"时**必须先澄清**，不要默认理解成"年龄相关分析"：
- **比对（alignment）**：fastq → BAM → fragments.tsv.gz —— **cellranger-arc 在数据发布前已完成**，下载的 fragments 就是比对产物，不需要再做
- **对比/分析（analysis）**：fragments → QC → cCRE → pseudobulk → 年龄相关 —— 论文 M&M 的全部内容，官方脚本第一行就是 `import_fragments`（**论文方法里没有任何比对步骤**）

本会话教训：用户说"找一下它的对比流程"被默认理解成"年龄相关分析"，等跑完分析用户才指出"这才是fq对比完成的结果就是fragments，那你还对比什么？你这是做什么呢？"——**白做了一轮才纠正**。

**正确动作**：听到"对比/比对流程"先回一句"你说的对比是指比对（fastq→fragments，发布方已完成）还是分析（fragments→结果）？"，确认后再动手。顺手讲清数据层级：fragments 已是比对终点，论文方法从 fragments 开始。

## 核心原则：官方路径优先（用户 2026-08-04 明确要求）

复现任何论文流程前，按此顺序找官方方法，**不自行发明参数**：

1. **官方代码仓库**：GitHub 搜「第一作者名 + 关键词」或通讯作者实验室 repo；Zenodo DOI（论文 Code Availability 段）
2. **官方补充材料**：`suppl_media1.pdf`（M&M 全文）→ 精确定位 ATAC 处理/年龄相关段落；`suppl_media2/`（Tables S1-S24）→ 注意 Table_S* 里常直接给出**官方 cCRE/peak 全集**
3. **GEO 页**：确认平台/样本数/元数据列；GSE suppl 页 vs GSM 页的两级存放结构（fragments 按样本在 GSM 页）
4. **论文正文**：Science/Nature 付费墙 → 用 bioRxiv 预印本（内容一致，免费全文）

交付确认：**先给用户确认原文（标题/PMID/DOI/作者/数据规模）再动手**。用户拿给师兄审的方案文档必须自包含、有官方出处。

## 关键技巧：官方 cCRE 复用（跳过 peak calling）

**当官方补充表提供 cCRE/peak 全集时，不要自己 call peaks。**

- 官方 Table_S*.tsv 通常 = 全部 cCRE（坐标 chr-start-end + 细胞类型归属），直接作为分析区间
- 流程：官方 cCRE 坐标 → 自己 fragments 计数 → pseudobulk log2CPM → 年龄相关分析（官方逻辑不变）
- 收益：免装 MACS3/snapatac2、与论文特征完全对齐、省去 peak calling 参数争议
- 案例：GSE278576 Table_S7 = 472,859 个官方 cCRE（详见 `references/gse278576-case.md`）

## cellranger-arc fragments 格式（10x Multiome/ATAC）

```
# 前 ~51 行是注释头（@HD/@SQ 等，含 primary_contig 列表）
# 数据行格式：chr start end barcode count（5 列 tab 分隔）
# 解析必须跳过所有 '#' 开头行，数据从首个非 '#' 行开始
```

- 文件：`{sample}_fragments.tsv.gz` + 必须配 `.tbi.gz` 索引（索引缺失 = 样本不完整）
- 计数性能：单样本 2-3GB gzip 逐行扫描 ≈ 456s；**用 multiprocessing 按样本并行（4 workers）**，9 样本 ~15 分钟
- 落 cCRE 率参考：45.4% 属正常（GSE278576 实测）

## pseudobulk 年龄 Pearson 相关（官方逻辑）

```
每细胞类型 × 每供体：fragments 落在 cCRE 的计数 → log2CPM
cor.test(cpm[i,], age, method="pearson") 逐 cCRE
shuffle 供体表达生成零分布（×5000）验证
p.adjust(pval, "fdr") → FDR < 0.1 → Up (cor>0) / Down (cor<0)
```

**前置检查（必做，否则白跑）**：
- ⛔ **供体年龄跨度**：查官方 Table_S1 的 donor→age 映射，确认年龄覆盖 ≥3 个年龄组/≥30 年跨度
- ⛔ 全 Young（如 20-38 岁）→ FDR 必全空（无统计力），结论只能是"流程验证"，不能外推衰老
- 供体数才是硬指标（混合效应模型需 ≥6 个体 × ≥3 年龄组），细胞数 ≠ 个体数

## Windows 环境现实（2026-08-04 实测）

- **snapatac2 全版本无 Windows wheel**（仅 macOS/Linux）→ 源码编译需 MSVC → Windows 上装不上。**不要浪费时间尝试**，走官方 cCRE 复用路径即可
- MACS3 在 Windows 可试 conda；但 cCRE 复用路径完全不需要它
- 纯 Python (pandas/scipy/statsmodels) + gzip 扫描即够跑完整流程，无需 GPU

## 已知陷阱

0. **🔴 用户指定脚本路径 ≠ 目标任务脚本（2026-08-11 实测）** — 用户说"继续跑热图，用 `E:\...\webui\session_state.py` 那个脚本，配色换蓝白"，但 session_state.py 是 webui 会话状态捕获模块（capture_user_request/extract_assets），**不含任何绘图逻辑**。用户凭记忆给路径容易把基础设施文件误当分析脚本。**修复**：拿到用户指定的脚本路径先 `read_file` 确认内容匹配任务（含目标图型绘图代码），不匹配就按已知产出物反查——`search_files(target='files', pattern='*heatmap*', path='results/')` 找到目标 figure → 看同目录 `scripts/` 找真正脚本 → 确认后再跑。**用户给的路径是线索不是事实。**
1. **官方代码 vs 论文 M&M 可能不一致**（GSE278576：代码 MACS3 vs 论文 MACS2）——以官方代码仓库为准，标注差异
2. **细胞注释是 RNA-based**（Multiome）——只有 ATAC fragments 时无法直接复现原文 18 亚类，用 marker 基因 TSS 可及性近似（海马 marker: SLC17A7/GAD1/GFAP/AIF1/MOG/PDGFRA/CLDN5）
3. **git clone 被墙** → 用 `https://codeload.github.com/<user>/<repo>/zip/refs/heads/main` 或 Python requests 下载 zip
4. **MSYS bash 路径转换坑**：`E:\\` 会被加前缀 → 用 `/e/` 格式或在 execute_code 里用 Windows 路径
5. **execute_code 的 .venv 可能有包冲突**（PIL）→ 绘图用系统 python3 直接跑
6. **rail_review(post) 传摘要字符串会误判"代码过短"** → 产出物齐全（图+TSV 存在）即视为通过，直接 record_run
7. **改 results 目录分析脚本后全量 pytest 会超时**（600s 跑 57 个测试未完）——分析产出脚本不在 pytest 覆盖内，验证 = ① 直接运行被改脚本（exit 0 + 产出物存在）→ ② 最小相关 pytest 子集（如 `webui/tests/test_session_memory.py` → 45 passed）→ ③ 全量后台跑。只改 matplotlib 配色等不碰仓库核心逻辑时全量非必需
8. **🔴 ArchR 1.0.3 `getGroupSE(TileMatrix)` 三层坑（2026-09-03 专利 L3 实测，详见 `references/archr-getgroupse-tile-coordinates.md`）** — ① `divideN` 默认 TRUE：counts 会除以组内细胞数（每细胞平均计数，小数量级），`rowSums(cnt) >= 2*ncol` 全灭报 "All tiles filtered out" → **必须 `divideN = FALSE`** 才返回原始总 counts；② `rowRanges(se)` 返回**空**（length=0，源码层 SE 只填 `rowData = featureDF` 不填 GRanges）→ 坐标从 `as.data.frame(rowData(se))` 取，不是 `rowRanges`；③ **`rowData(se)` 第 2 列也不是碱基坐标**——是每条染色体独立 1 起的 tile index，CSV 侧的 `end` 列 = (idx-1)×500 伪坐标 → 真实坐标换算 `start=(idx-1)×500+1, end=idx×500`。判定方法：awk 扫染色体切换点，index 重置（chr10 首=93/chr11 首=391/猴 NC_088376.1 首=41）即每染色体独立编号。**修复不需要重跑 getGroupSE**（r/p/q 统计列正确，只换坐标列，本地 fread/fwrite 几秒）。**猴侧 20 样本 + FDR(q<0.1) 显著=0 是真实数学结果不是 bug**——下游秩保守比较用全表 r 值，不受显著子集为空影响

## 验证方式

- **临时 ad-hoc 验证**（无正式 test suite）：① `py_compile` 语法检查 ② 真实数据运行日志 EXIT=0 ③ 小规模 smoke test 构造已知信号（如 50/200 显著）验证 Pearson/FDR 逻辑
- 最强证据 = 真实数据全量运行产出（TSV 大小、图文件数）

## 已知陷阱（复现类追加）

9. **🔴 复现对账必须逐基因核对，禁止"差异属预期"糊弄（2026-09-11 M2-M7 复现实测）** — 流水线跑完对账数字对不上时，禁止只改 REPRO_SUMMARY 文字说"输入版本不同，差异属预期"。必须逐基因 diff 定位根因：读正本 all.csv 与复现 all.csv 按 symbol 对齐，比较 Z_m / Z_h / n_tiles。判别逻辑：**同 tile 数但 Z 不同 = 输入文件版本不同或聚合逻辑不同**；human 侧完全一致 + monkey 侧全不同 = 猴侧输入文件用错版本。本例：误用 `E:/专利/monkey_ageDA_all.csv`（530 万 tile, 1-based）而正本实际输入是 `E:/专利/monkey_ageDA_continuous.csv`（567 万 tile, 0-based）——**两套独立 ageDA 计算结果**（首行 `19500-19999` vs `20001-20500`，偏移 501bp、tile 数差 37 万），不是"同网格差 1bp"。⚠️ **修正（2026-09-11 实测）**：机制**不是**"锚到的 tile 集合不同"——AGBL2 两侧 `n_tiles_m` **同为 151**，命中集合与坐标网格相同，变的是**每个 tile 的 r/p 值体系**（Z_monkey 正本 −3.3395 vs all 版 −1.5678，p 8.39e−04 vs 1.17e−01）。所以判别式要写成「**实体个数相同而值不同 ⇒ 另一张同网格输入表**」。

**决定性指标 = 逐实体逐位一致率**（比总量硬得多，两张不同输入表也能撞出相近总量）：

```python
m = pat.merge(cand, on='symbol', suffixes=('_pat','_cand'))
dz = (m['Z_monkey_pat'] - m['Z_monkey_cand']).abs()
print(len(m), (dz < 1e-4).mean(), dz.median(), dz.max())
```
实测：正本 vs continuous 版 → 共有 15965 / 一致率 **100.0%** / 中位差 0.0000 / 最大差 **0.0000**（同一输入表）；正本 vs all 版 → 共有 15963 / 一致率 **0.0%** / 中位差 1.8062 / 最大差 20.1043。可直接跑 `cross-species-cre-conservation/scripts/diff_two_runs.py`。注意 `suffixes` 命名坑：列名是 `Z_monkey_pat` 不是 `Z_monkey_a`（写错 AttributeError）。

**归属取证的三个廉价动作（先做这个，比调参快 100 倍）**：
1. **文件名考古**：`ls -lt` 排中间产物找链式关系——原始作者常把口径**写进文件名**，本轮铁证 `P3_L1_data/v4b_gene_conservation_continuous.csv`、`v4b_conservation_stats_continuous.txt`（`continuous` 是文件名里的字）。
2. **中间 stats 正文考古**：正本数字常原样躺在中间产物里而你没翻——`v4b_conservation_stats_continuous.txt` 正文即「ortholog 基因对: **16031** / 高置信保守相似基因: **1904** / 加权 Spearman **ρ = -0.0810**」，与专利三个数字逐字对应；`v4b_gene_substitutability_table.csv` 首行 AGBL2 与正本 v5 逐位相同。**先 grep 中间产物正文找正本数字原文，再决定跑什么。**
3. **时间链**：`monkey_ageDA_continuous.csv(01:05) → v4b_*_continuous.csv(01:10) → v4b_*_table.csv(02:16) → v5(12:41)`——正本产物必晚于其输入且紧邻，这条规律本身就能排除大部分旧候选。

**单脚本多口径改造（禁止复制兄弟脚本）**：`OUT_DIR = os.environ.get("OUT_DIR", 默认); MONKEY_CSV = os.environ.get("MONKEY_CSV") or 默认` —— 一份脚本跑多口径、`OUT_DIR` 隔离旧产物、默认值保证向后兼容。复制出 `repro_continuous.py` 这种只改两行常量的"兄弟脚本"= 维护异味（必然漂移）。口径对账产物属**诊断中间物，不得进交付目录**（交付目录永远只有唯一口径的一套产物）。

详见 `references/reproduction-reconciliation.md` + `cross-species-cre-conservation/references/input-provenance-reconciliation.md`⚠️ **表格文件同名/同族 ≠ 同一版本**：`_all` 与 `_continuous`、1-based 与 0-based、divideN 口径差异都会让 r 值体系完全不同。**定位正本生成脚本**：`find E:/MemOmics-Agent/results -name "*.py"` 搜历史会话 `results/<sid>/scripts/`（本例正本 v4b/v5/v6 在 `memomics-cd677556/scripts/`）——专利自有算法（非论文流程）的 ground-truth 脚本在历史会话里，不在论文官网。详见 `references/reproduction-reconciliation.md`
10. **🔴 复现分级/置换必须逐行对齐正本脚本语义（2026-09-11）** — S 四分类（A/B/C/D）与置换检验的任何一行语义偏差都会造成数字大迁移：① **B 类 = 反向且双侧显著**（`amin>=tau`），写成"反向且至少一侧显著"→ B 暴涨（3487→7091）、C 减半（7562→3656），B+C 总量不变是典型特征；② **S 带符号** = `min(|Zm|,|Zh|)×sign(Zm·Zh)`（反向为负），不能反向给 0；③ 置换 **shuffle Zh（不是 Zm）**、**n_perm=10000（不是 2000）**、**p = min(P(A≥obs), P(A≤obs))×2**（不是离均值距离双侧 p）；④ **Z 先 round 4 位再分类**（正本从 v4b CSV 读的就是 4 位精度 Z）。修复后对账目标：16031 / 1904 / 3487 / 7562 / 3078 + perm_mean_A=2012.71 + perm_p=0.0008。另：M6 promoter 口径是 tile 中点 ∈ [TSS±2kb] 直接锚定（猴 strand 精确 TSS、人用 start 近似），不是 gene-body 窗口 + promoter filter 两段式
11. **⛔ 写数据加载脚本前必须先读实际文件表头（用户 2026-09-11 明确要求："你在写对应脚本之前，需要一些列名，需要自己先查看一下文件列名，然后写"）** — 禁止按记忆/推断写列索引。先 `head -2 <file>`（zcat + `head -1 | tr '\t' '\n'` 看 feature_table 表头）确认真实列名与顺序，再写 loader。实测注意：CSV 可能带引号（`"chr","start",...`）也可能不带；feature_table 首行是 `# feature` 注释头，gene 记录列索引 p[6]=genomic_accession / p[7]=start / p[8]=end / p[9]=strand / p[14]=symbol / p[15]=GeneID
12. **⛔ numpy 无 `np.erf`；`np.frompyfunc` 对标量输入返回 Python float（2026-09-11 实测）** — 纯 numpy 实现正态分布函数时：① 用 `math.erf`（C 双精度）+ `np.frompyfunc` 向量化；② `np.frompyfunc` 对**标量/0 维数组**输入返回 Python float，`.astype()` 会报 `'float' object has no attribute 'astype'` → 修复：`np.atleast_1d` 强制成 1 维数组计算，输入是标量时再解包 `out[0] if xa.ndim == 0 else out`；③ `erfinv` 无现成 numpy 实现 → Winitzki 初值 + 6 轮牛顿迭代可达 1e-12（锚点 Φ⁻¹(0.975)=1.959963984540054 验证）
13. **⛔ 后台进程报错日志可能是修复前旧脚本的残留（2026-09-11 重跑 M2-M7 实测）** — 修复 bug 后重启后台任务，若又立刻收到 exit 1 + traceback，**先比对 traceback 行号与当前文件内容**再动手：旧日志的 `line 67: return _erf_vec(np.asarray(x)).astype(np.float64)` 与当前文件 line 67=`xa = np.asarray(...)` 对不上 → 该日志是修复前进程的残留，不是新失败。判定法：read_file 当前文件出错函数区域，行号语义不一致 = 日志过期。别把已修复的 bug 当活 bug 再排查一遍

14. **⛔ 禁止静默更换输入口径；禁止把未证实的溯源结论写成结论句塞进生成的报告（2026-09-11 实测，用户强烈不满）** — 两个层面都会犯，都要防：
   - **执行层**：用户指定了输入文件（如"M2 都在这里面"→ `M2/monkey_ageDA_all.csv`）时，若发现该文件复现不出正本数字，**停下来报告 + 给证据 + 等裁决**，绝不能悄悄换成另一个文件让数字对上——用户原话："为什么是 continuous 版 567 万 tile？我不是说了吗？用我给你的文件"。正确话术：「你给的文件跑出 A=2335，正本 1904，差 431；我怀疑正本用的是另一张表，证据是 ①逐实体一致率 0% ②中间产物文件名含 continuous ③时间链，是否切过去验证？」
   - **产物层**（更隐蔽，本次真发生）：生成的 `REPRO_SUMMARY.md` 里写死了一句"专利正本数字来自 continuous 版输入"——**当时那只是推测，却被写成了结论句固化进产物**，等于把未验证结论当事实交付。修复：① 报告里的输入/口径字段一律**从变量取**（`os.path.basename(MONKEY_CSV)`，实际用了哪个文件就写哪个路径），不写死叙述；② 叙述句只写本次**实际观测到**的事实，推测一律标注"待验证"；③ 用户提出"If 吻合 then 证明"式判据时，**真跑真判，吻合/不吻合都报**（本次假设不成立照报，并给出反向定论——这才是用户要的"矛盾消除"）。
   - 通用口诀：**输入路径是线索不是事实；报告里的每一句口径叙述都要能被变量渲染或日志复现。**

15. **🔴 复现正本必须逐字复用正本原脚本的实现函数——重写算法会引入残差（2026-09-11 v5 零差异收官）** — 本类任务最大的隐形偏差源**不是输入表，而是自己重写锚定/聚合函数**。实测：同一 continuous 猴输入，重写 `anchor()` → 16012 对（残差 19、66 个正本 symbol 缺失）；**逐字复刻**正本原脚本 `P3_L1_data/repro_m3_from_M2.py` 的 `anchor()` → **16031 对，逐位零差异**。
    - **正本 anchor 语义（照抄，别自创）**：`mid=(s+e)//2`；窗口 `[mid-2000, mid+2000]`；`idx = np.searchsorted(starts[chrom], hi, side='right') - 1` 后**向前回溯**，取**首个**满足 `gs_ <= hi and ge_ >= lo` 的基因（first-overlap-wins），遇 `ge_ < lo` 即 break；每 tile 只归一基因；再按 `Stouffer Z = Σ sign(r)·Φ⁻¹(1−p/2) / √n` 聚合。WINDOW=2000 是常量，不是可调参数。
    - **残差归因三判据（先跑这个，再谈"算法差异"）**：① 缺失 symbol 是否全在 ortholog 表（实测 66/66 ⇒ 不是 ortholog 表缺行）② 是否出现在另一输入版本的输出（实测 0 个 ⇒ 不是输入表问题）③ 换回正本函数后残差是否归零（归零 ⇒ **属实现层**）。三条都查完才准下结论。
    - **验收标准 = 逐位零差异，不是总量对得上**：symbol 集完全重合（两侧独有均为 0）+ `Z_monkey / Z_human / n_tiles_m / n_tiles_h` 的 max|Δ| = 0（p 列 ≤1e-21 属浮点存储精度）+ class 不一致 0 个 + class 分布逐项一致（1904/3487/7562/3078）。只对上 n 或 A 类数**不足以**宣称复现。
    - **取用正本脚本前先 `ls -lt` + 读函数体**：正本目录里的同名脚本可能已被当期改动——本例 `repro_m3_from_M2.py`（mtime 今天）的输入路径已被改指向 all 表，但输出文件名仍保留 `_continuous`。**文件名/输出名里的口径词是历史残留，以函数体为准。**

## 参考

- `references/v5-canonical-zero-diff-recipe.md` — v5 正本零差异复现配方（输入表 + 正本 anchor 语义 + 逐位核验脚本 + 残差归因三判据 + L2 辩论裁决摘要）
- `references/gse278576-case.md` — GSE278576 人海马衰老 ATAC 案例细节（官方来源/参数/9样本pilot结果/脚本入口）
- `references/nhpabc-cre-workflow.md` — 张潇 NHPABC cCRE 流程参数基线（peak calling 501bp fixed-width / maxPeaks=500000 / cutOff=0.01 / maxCells=5000 / maxReplicates=10；PeakMatrix→Seurat CPM→MeanCPM>4@≥4样本 & >0@≥12样本；addCoAccessibility k=10/500kb/250kb；与 ArchR 默认差异表）— 专利复现猴脑 cCRE 时按此参数
- `references/archr-getgroupse-tile-coordinates.md` — ArchR 1.0.3 getGroupSE(TileMatrix) 三层坑（divideN=FALSE / rowData 非 rowRanges / tile index→坐标换算公式与 awk 判定法）— tile 级 age-DA 必读
- 关联 skill：`gse278576-atac-aging-comparison`（该论文专属复现 skill，含官方参数表）；`public-data-download`（GSE fragments 下载）；`atac-seq-memomics`（ArchR 全流程 + peak calling 调试）

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| human | hippocampus | aging | 2026-09-03 | fix_ageDA_coords.R | - | - |  |
