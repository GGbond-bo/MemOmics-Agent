# M2→M7 端到端复现流水线（2026-09-11 修复版）

> 适用：复现「跨物种衰老可替代性」专利的 M2→M7 全链数字（16031 对 / A=1904 / B=3487 / C=7562 / D=3078 / τ=1.96）时。脚本：`E:/专利/M2/repro_full_pipeline.py`（端到端单脚本，零手动修正）。

## 用户交付铁律（2026-09-11 用户原话）
"你修改了脚本，为什么不能直接用脚本生成出来呢？不然人家复现，还要修正一下吗？"
→ 修复后的脚本必须**一条流水线直接生成全部产物**（输入输出固定、端到端可跑），禁止多版本产物并存、禁止复现需手动 patch。与记忆 `[imp:0.85]` 一致。

## 写脚本前必做：逐文件核实列名（用户明确纠正过）
"你在写对应脚本之前，需要一些列名，需要自己先查看一下文件列名，然后写"——**禁止凭记忆/注释猜列名**。本次实测各输入的真实表头：

| 文件 | 表头 | 关键陷阱 |
|---|---|---|
| `E:/专利/M2/human_ageDA_all.csv` | `chr,start,end,r,p,q` | chr=`chr1`（hg38 格式） |
| `E:/专利/M2/monkey_ageDA_all.csv` | `chr,start,end,r,p,q` | chr=`NC_088375.1`（T2T RefSeq accession 格式） |
| `E:/专利/P3_L1_data/monkey_human_orthologs_full.csv` | `macaque_gene_id,human_gene_id,human_symbol` | 均为 NCBI GeneID |
| `E:/专利/P3_L1_data/human_ortholog_hg38_full.csv` | `human_gene_id,chr,start,end` | **chr 列无 'chr' 前缀**（值是 `19`）→ 加载时须 `'chr'+row[1]` 才能与 tile 的 `chr19` 匹配 |
| `E:/专利/P3_L1_data/GCF_037993035.2_T2T-MFA8v1.1_feature_table.txt.gz` | NCBI feature table（tab 分隔） | **列索引**：`[0]='gene'` 过滤（跳过 mRNA/CDS/ncRNA 行）；`[6]=genomic_accession`（=猴 tile 的 chr，NC_ 格式）；`[7]=start`；`[8]=end`；`[9]=strand`；`[14]=symbol`；`[15]=GeneID` |

## 锚定逻辑（必须猴人分开）
- 猴 tile → **T2T feature table** 锚定（genomic_accession 匹配）；人 tile → hg38 坐标表锚定（chr 补前缀）。
- **禁止**用人坐标表锚猴 tile（曾写 `MONKEY_GENE_BED=None` 导致猴侧 0 命中）。
- tile 主循环 + `np.searchsorted` 反查（千万行 CSV 逐基因扫描不可行）；tile 中点 ±2000bp overlap 基因体。
- M6 promoter 版：只保留 tile 中点落在 TSS±2kb（正链 TSS=start，负链 TSS=end）。

## 统计口径（与专利正本一致）
- Stouffer 聚合：`Z = Σ[sign(r)·Φ⁻¹(1−p/2)] / √n`（r 带符号；不是 Fisher Z、不是 r_mean）。
- 分级（τ=1.96）：A=同向+双侧 \|Z\|≥τ；B=反向+(任一侧显著)；C=单侧显著；D=双侧不显著。
- 置换检验：shuffle 猴 Z 配对 → A 计数空分布 → 双侧 p。
- ⚠️ **口径版本冲突（重要）**：A=1904 四分级是 v5 **旧口径**；`substitutability-score-formula-traps.md` 已裁决 min 公式统计方向是反的、四分级"一打就倒"，**正确口径 = `min(|Z₁|,|Z₂|)>τ_A`（τ_A≫1.96，本数据 37 核心元件）**。复现脚本按用户要求对齐旧数字对账没问题，但**给专利下结论时必须按新口径**（37 核心元件 + 其余标不可判定），不要引用 1904 当 claim 证据。

## 零 scipy 依赖的统计实现（环境缺 scipy 时的通用模式）
rail_review(pre) 报 Missing: scipy，而项目 venv / 共享库 / 系统 Python 三处都无 → 不装包（铁律 29 需用户同意），改为纯 numpy：
- `norm_cdf`：`0.5*(1+erf(x/√2))`
- `norm_ppf`：`√2·erfinv(2p−1)`，erfinv 用 Winitzki 初始估计 + 6 次牛顿迭代（精度 ~1e-12）
- `rankdata` / `linregress` / `spearmanr`：手写（mergesort argsort 平均秩；最小二乘；秩相关 + 大样本正态近似 p）
- **⛔ numpy 没有 `np.erf`**（erf 在 `math` 模块）→ 用 `np.frompyfunc(math.erf, 1, 1)(x).astype(float)` 向量化。写 `np.erf` 会 AttributeError 崩（本会话实测）。
- **验证必做**：Φ⁻¹(0.975)=1.959963984540、Φ⁻¹(0.5)=0、cdf(1.96)=0.9750021048517795 等 6+ 锚点 + 1000 点圆整误差 `max|ppf(cdf(z))−z|<1e-8`——确保纯 numpy 实现与 scipy 数值一致后才跑。

## 对账清单（跑完后逐项核对）
| 指标 | 专利正本（旧口径） |
|---|---|
| ortholog 对 | 16031 |
| A / B / C / D | 1904 / 3487 / 7562 / 3078 |
| 置换均值 A / p | 2012.71 / 0.0008 |
| M6 promoter A | 402 |
| M7 同向 R² | 0.2785 |

> 输入改用 M2 版（divideN=FALSE, 1-based）后数字会偏离 continuous 版（0-based, divideN 默认）——同套 bin 两种坐标表示（差 +1bp），但 r 值体系不同，数字差异属预期，交底书同步更新。

## 中文路径坑
- `search_files` 对中文路径（`E:/专利/...`）内容搜索可能返回 0（本会话 grep 却命中）→ 改用 terminal `grep -n` 或 read_file 确认。