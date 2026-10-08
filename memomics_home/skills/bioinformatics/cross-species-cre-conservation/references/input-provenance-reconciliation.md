# 输入口径对账与复现溯源（完整取证链）

> 2026-09-11 实证定论。适用场景：用户问「专利/论文里这组数字是哪个输入文件跑出来的？」「用我给你的文件能不能复现？」
> 结论（本次）：专利 v5 的猴侧正本输入 = `E:/专利/monkey_ageDA_continuous.csv`（567 万 tile, 0-based），
> **不是**用户提供的 `E:/专利/M2/monkey_ageDA_all.csv`（530 万 tile, 1-based）。

---

## 0. 结论摘要

| 输入口径 | ortholog 对 | A | B | C | D | 置换均值 A | ρ | 与正本吻合? |
|---|---|---|---|---|---|---|---|---|
| **正本（专利 v5）** | **16031** | **1904** | **3487** | **7562** | **3078** | **2012.71** | **−0.081** | — |
| continuous 版复现 | 16012 (−19) | **1905** | 3474 | 7554 | **3079** | **2011.42** | **−0.0809** | ✅ 吻合（残差 0.12%） |
| all 版复现 | 16010 | 2335 (+431) | 3070 | 7677 | 2928 | 2617.14 | −0.195 | ❌ 完全不吻合 |

v6 promoter：正本 pairs=15178 / A=402 / B=222 / C=5840 / D=8714；continuous 复现 15182 / **404** / 223 / 5841 / **8714** ✅；all 版复现 15180 / 794 / 731 / 6704 / 6951 ❌。

---

## 1. 定性刀：逐实体比对（不是比总量）

```python
import pandas as pd, numpy as np
pat = pd.read_csv("E:/专利/P3_L1_data/v5_substitutability_all.csv")        # 正本
rc  = pd.read_csv("E:/专利/M2/pipeline_out_cont/v5_substitutability_all.csv")  # continuous 复现
r4  = pd.read_csv("E:/专利/M2/pipeline_out/v5_substitutability_all.csv")       # all 复现

def cmp(a, b, na, nb):
    m = a.merge(b, on='symbol', suffixes=('_'+na, '_'+nb))
    dz = (m['Z_monkey_'+na] - m['Z_monkey_'+nb]).abs()
    print(f"{na} vs {nb}: 共有 {len(m)} | 一致(±1e-4) {np.mean(dz<1e-4):.1%} "
          f"| 中位差 {dz.median():.4f} | 最大差 {dz.max():.4f}")

cmp(pat, rc, 'pat', 'cont')   # 共有 15965 | 一致 100.0% | 中位差 0.0000 | 最大差 0.0000
cmp(pat, r4, 'pat', 'all')    # 共有 15963 | 一致   0.0% | 中位差 1.8062 | 最大差 20.1043
```

⚠️ **merge 的 suffixes 命名坑**：`suffixes=('_pat','_cont')` 生效后列名是 `Z_monkey_pat`，不是 `Z_monkey_a`——写错直接 `AttributeError`。

### 单实体溯源（定性最快的一步）

| 量 | 正本 v5 | continuous 复现 | all 版复现 | 判读 |
|---|---|---|---|---|
| AGBL2 Z_human | −8.2675 | −8.2675 | −8.2675 | 人侧同一文件 |
| AGBL2 p_human | 2.220446e−16 | 同 | 同 | 同 |
| AGBL2 n_tiles_h | 114 | 114 | 114 | 同 |
| AGBL2 **n_tiles_m** | **151** | **151** | **151** | 猴 tile 命中集合相同 |
| AGBL2 **Z_monkey** | **−3.3395** | **−3.3395** | **−1.5678** | ← 定性点 |
| AGBL2 p_monkey | 8.3918e−04 | 同 | 1.1692e−01 | 同 |

**裁决**：实体个数（n_tiles）相同、坐标网格相同，而逐 tile 的 r/p 值体系不同 ⇒ 猴输入表是**另一张同网格表**。不是聚合公式错、不是阈值错，调参毫无意义。

▶ 通用脚本：`scripts/diff_two_runs.py`。

---

## 2. 廉价取证三件套

### 2.1 文件名考古

```
E:/专利/P3_L1_data/v4b_gene_conservation_continuous.csv     ← 文件名自带 continuous
E:/专利/P3_L1_data/v4b_conservation_stats_continuous.txt     ← 同上
```

### 2.2 stats 正文考古（正本数字原文）

`v4b_conservation_stats_continuous.txt` 内容（节选，**与专利数字逐字对应**）：

```
==== V4 跨物种衰老可替代性（Stouffer 聚合版）====
ortholog 基因对: 16031
加权 Spearman ρ = -0.0810  置换 p = 0.0000  (n_perm=2000)
方向一致: 6662 (41.6%)  相反: 9369 (58.4%)
高置信保守相似基因: 1904
```

`v4b_gene_substitutability_table.csv` 首行（与专利 v5 的 AGBL2 行**逐位相同**）：

```
symbol,effect,substitutability,Z_monkey,Z_human,p_monkey,p_human,n_tiles_m,n_tiles_h
AGBL2,衰老下调,保守·可替代(down),-3.3395,-8.2675,0.0008391846689406,2.220446049250313e-16,151,114
```

### 2.3 时间链（mtime）

```
monkey_ageDA_continuous.csv        9-4 01:05
v4b_gene_conservation_continuous.csv  9-4 01:10   (+5 min)
v4b_gene_substitutability_table.csv   9-4 02:16
v5_substitutability_all.csv          9-4 12:41   ← 正本
```

正本产物必晚于其输入且紧邻 —— 这条规律本身就足以排除 `M2/monkey_ageDA_all.csv`（9-3 01:30）之外的旧选项。

### 2.4 两版差异幅度必须实测，不许推断

```bash
head -1 E:/专利/monkey_ageDA_continuous.csv   # NC_088375.1, 19500, 19999  (0-based)
head -1 E:/专利/M2/monkey_ageDA_all.csv       # NC_088375.1, 20001, 20500  (1-based)
wc -l < E:/专利/monkey_ageDA_continuous.csv   # 5674191（567 万）
```

偏移 **501bp**、tile 数差 **37 万** ⇒ 两套**独立**计算结果，不是"同一网格差 1bp"。**先实测再断言。**

---

## 3. 单脚本多口径改造（禁止复制兄弟脚本）

```python
M2_DIR  = r"E:/专利/M2"
OUT_DIR = os.environ.get("OUT_DIR", os.path.join(M2_DIR, "pipeline_out"))

# 输入口径可注入（对账用）：默认 M2 all 版；MONKEY_CSV=... 可切 continuous 版
HUMAN_CSV  = os.environ.get("HUMAN_CSV")  or os.path.join(M2_DIR, "human_ageDA_all.csv")
MONKEY_CSV = os.environ.get("MONKEY_CSV") or os.path.join(M2_DIR, "monkey_ageDA_all.csv")
```

跑法（旧产物不被覆盖）：

```bash
MONKEY_CSV="E:/专利/monkey_ageDA_continuous.csv" \
OUT_DIR="E:/专利/M2/pipeline_out_continuous" \
python repro_full_pipeline.py > pipeline_out_continuous_run5.log 2>&1
```

**报告输入行也必须变量化**（否则写出假口径）：

```python
md = f"""...
- 输入：`{os.path.basename(HUMAN_CSV)}` + `{os.path.basename(MONKEY_CSV)}`（猴输入表：{MONKEY_CSV}）
..."""
```

❌ 反面教材：把整份脚本复制成 `repro_continuous.py` 只改两行常量 —— 改一处忘另一处，两边以后必然漂移。
❌ 反面教材：报告里写死一句"专利正本数字来自 continuous 版输入" —— 当时只是推测，却被写成结论句固化进产物（用户会查、会追问）。

> 口径对账跑出的多份产物 = 诊断中间物，只留 scratch 目录；交付目录永远只放唯一口径的一套产物。

---

## 4. 与用户交互的正确姿势

| 情形 | 错 | 对 |
|---|---|---|
| 用户指定的输入跑不出正本数字 | 悄悄换另一个输入让数字对上 | **停下来报告**："你给的文件跑出 A=2335，正本 1904，差 431；我怀疑正本用的是另一张表，证据是 X/Y/Z，是否切过去验证？" |
| 用户指定的输入**确实**是正本 | 仍写"可能是另一个" | 逐实体比对给出 100% 一致证据，直接收口 |
| 判据是"If 吻合 then 证明" | 预设结论、只报有利部分 | 真跑真判，**吻合/不吻合都报**（本次 A 假设不成立也照报，并给出反向定论） |
| 报告要写口径 | 写死叙述 | 从变量取实际路径；推测标"待验证" |

---

## 5. 验证清单

- [ ] 总量表（N/A/B/C/D/ρ/置换均值）双列对照（正本 vs 本次复现）
- [ ] 逐实体比对，报"共有数 / 一致率 / 中位差 / 最大差"四元组
- [ ] 至少 1 个实体的逐字段溯源表（Z_m / Z_h / p_m / p_h / n_tiles_m / n_tiles_h）
- [ ] `ls -lt` 中间产物时间链 + 文件名口径自查
- [ ] 中间 stats 正文里能否找到正本数字原文
- [ ] 报告输入字段是否是变量渲染（不是写死）
- [ ] 交付目录未被诊断产物污染
