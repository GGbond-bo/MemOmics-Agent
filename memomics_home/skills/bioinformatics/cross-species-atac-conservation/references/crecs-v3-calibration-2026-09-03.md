# CRECS v3 阈值校准 + 人猴高相似基因筛选（2026-09-03 实测）

## 触发场景
外部验证（GSE67978）出结果后，用户拍板"先做方案②阈值校准"（本地数据已齐，不依赖网络）。
v2.2 分类有结构缺陷 → 修复后重算 A/B/C/D → 再回答用户模拟老师问题 3（"你有筛出一批人和猴相似性很高的基因吗？"）= tile→基因映射 + 人/猴 r 相似性评分。

## 关键文件与脚本
| 文件 | 说明 |
|---|---|
| `P3_L1_data/p4_crecs_v3.py` | v3 校准脚本（138 行）：L2 chr 统一 + H3K27ac 逐 tile 命中 + 分类输出 |
| `P3_L1_data/p4_crecs_v3_scores.csv` | 1000 tiles × 11 列（chr/start/direction/r/phyloP/l1/da_m/h3k_h/h3k_m/class/class31），**class31 = v3.1 真分类** |
| `P3_L1_data/p4_crecs_v3_summary.csv` | A/B/C/D 命中率汇总 |
| `P3_L1_data/gse67978/peaks/GSM*.narrowPeak.gz` | 人 3（hg38）+ 猴 3（rheMac3）H3K27ac peak（用户手动下载） |
| `E:/专利/rheMac3ToHg38.over.chain.gz` | 猴→人 chain（用户下载，已验证可用，head 行 src=rheMac3 chr1 229590362 → tgt=hg38 chr1 248956422） |
| `monkey_peaks_hg38_map.csv` | 锚点映射表（⚠️ hg38_chr 无 chr 前缀） |
| `monkey_ageDA_all.csv` | 猴 DA tiles |
| `P3_L1_data/p4_crecs_AB_genes_tile.csv` | 310 行 tile×基因 明细（含 r_human/r_monkey/相似性） |
| `P3_L1_data/p4_crecs_AB_genes_summary.csv` | 基因级汇总 |

## v3 三个根因修复

### 根因① L2 chr 前缀 bug
`monkey_peaks_hg38_map.csv` 的 `hg38_chr` 列是 `1/2/X`（无前缀），DA tiles 是 `chr1` → set 精确匹配必 0。修复：`'chr'+hg38_chr if not startswith('chr')`。

### 根因② L3 池级常量（C=0 真正根因）
```python
L3_JACC = {'up': 0.213, 'down': 0.034}   # 池级均值常量
l3_score = min(1.0, L3_JACC[direction] * 5)
```
→ up & L1=1 恒 A（crecs≥0.8）；down & L1=1 恒 B；C 分支数学上不可达 → C=0、B=364 全是常量算出来的。
**检查铁律**：L3 来自固定 dict = 池级常量顶替逐 tile 值，分类边界必然失真。先查这个，不是先调阈值。

### 根因③ 坐标网格不对齐（最深根因，修复②后暴露）
修好 chr 前缀后 `da_m` **仍全 0** → 不是前缀问题：**锚点平移窗 start ≠ 500bp tile start**，两套 bin 网格天然错位，set 精确匹配数学上必为 0。
**解法**：弃锚点平移式猴 DA 命中，改真实 GSE67978 H3K27ac 峰逐 tile 命中（人 `h3k_h` / 猴 liftover `h3k_m`）。
pyliftover 环境坑：**pyliftover 只装在系统 Python**（`C:\Users\23136\AppData\Local\Programs\Python\Python312`），execute_python 内核没有 → 用 `python <script>.py` 直接跑（terminal）；`LiftOver(chain_path)` 传**本地 chain 文件路径**（传组装名会联网下载失败）。

## v3.1 最终分类（权威）
| 类别 | v2.2（伪） | v3.1（真） | 含义 |
|---|---|---|---|
| A | 182 | **47** 人100%/猴100% | 保守+双活性保留 |
| B | 364 ←假 | **49** 人0%/猴100% ★ | 保守+人失活+猴保留（"人类谱系活性丧失的保守增强子候选"） |
| C | 0 ←不可达 | **450** 人6.4%/猴0% | 中间态 |
| D | 454 | **454** | 不保守 |

**关键发现**：即使修好 chr 前缀，锚点平移表的 da_m 仍全 0——锚点窗 start ≠ 500bp tile start，坐标网格天然不对齐，set 精确匹配数学上必为 0。这是 v2.2 L2 设计的根本缺陷，不是小 bug。用真实 H3K27ac 实验峰替代锚点平移作猴侧活性证据 = 证据质量关键提升。

## 外部验证在"错误分类"上的方向仍成立
外部验证跑的是 v2.2 B=364（错误口径），但结论"猴侧 H3K27ac 活性显著高于人（p=3.7e-3）+ 猴侧 B 富集于 A/D（OR≈3.1, p<1e-4）"与 v3.1 B=49 的"猴 100% 活性保留"方向**自洽**（v3 B 定义中猴侧活性=1 正是其分类特征，Honest Check：v3 分类特征与外部证据不矛盾，反而强化）。
⚠️ 但 v3.1 未重跑外部 Fisher——若正式写实施例需在 v3.1 分类基础上重跑外部验证。

## 人猴高相似基因筛选（老师问3 · 专利实施例基因清单）

### 方法
1. tile 集 = v3 scores 的 class31 A/B（A=47/B=49）
2. tile→基因：`v4/l1_full_monkey.csv`（272K 锚点行，含 hg38 坐标 + human_gene/macaque_gene）500bp tile 与锚点窗 overlap → 基因集合（chr 归一化去前缀再比）
3. 人/猴相似性：`m3_conservation_gene.csv`（symbol → r_human/r_monkey = 两侧年龄 Pearson r）
4. 评分：同方向 + max(|r_h|,|r_m|)>0.05 = 高；同向弱 = 中；反方向 = 低

### 结果
- A 类 21/47 tile 映射到 20 基因；B 类 15/49 tile 映射到 14 基因（其余 tile 落基因间区，第一版最近基因映射的边界）
- **A 类高相似 10 基因**：BIRC3, BRINP3, FKBP5, MARVELD1, NID1, PHKG1, RGS20, SLC16A9, TOX, ZFHX3, ZNF770
- **B 类高相似 8 基因**：ALPK2, ATP6V0E2, DGKI, FBXL17, FZD1, GABRB1, NID1, SALL2
- **实施例叙事亮点（GABRB1 GABA-A受体β1 / FZD1 Wnt/Frizzled / ZFHX3 ATBF1 海马发育 TF）**：保守增强子控制的海马神经元受体/信号核心基因在衰老人脑静默、正常猴脑仍活跃 = "人谱系特异衰老脆弱性"候选机制

### 产物
`p4_crecs_AB_genes_tile.csv`（310 行 tile×基因明细）+ `p4_crecs_AB_genes_summary.csv`（基因级汇总）

### 可优化方向（进实施例前）
① 用 H3K27ac peak 关联的非 500bp 窗口替代最近基因映射；② 叠加 L3 motif 支持证据（MO-TF 已算过）；③ 重跑外部验证在 v3.1 分类上。