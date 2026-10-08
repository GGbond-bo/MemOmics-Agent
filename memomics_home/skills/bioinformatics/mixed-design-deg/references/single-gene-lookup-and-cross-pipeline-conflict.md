# 单基因定位查询 + 两套 DEG 口径冲突处理（实测记录）

**会话**：memomics-afd2d418 · 2026-10-01 · human skeletal muscle / MF 10 亚群 / 24 供体 × Pre-Post
**触发**：用户问「帮我确认一下 MEF2C 在哪个条件下变化了，哪个亚群」

---

## 0. 数据处境（先画清源表地图，否则一定答错）

| 表 | 位置 | 性质 | 每对比行数 | 是否过滤 |
|---|---|---|---|---|
| 用户原始 5 对比表 | `D:/肌肉锻炼/file/{Aging,DM,Ex_Young,Ex_Old,Ex_DM}.csv` | 17,395 基因 × 10 亚群，列 `logFC/CI.L/CI.R/AveExpr/t/P.Value/adj.P.Val` | 173,950 | ❌ **全量** |
| 过滤交付表 | `D:/肌肉锻炼/DEG_file/DEG_fdr05_coef025_5contrasts_formatted.xlsx` | 5 sheet（Aging/DM/Y_EX/O_EX/DM_EX），单列 `coef/se/z/p/fdr` + `n_cells/method/nRUV_used` | Aging 23,178 等 | ✅ `fdr<0.05 & |coef|>0.25` |
| 平台侧全量缓存 | `results/<sid>/task2/results/deg_allraw_cache.pkl` | 340,971 行，含 `is_sig` | Y_Pre_vs_Y_Post 76,060 等 | ❌ 全量（带 is_sig 标记） |

**对比名映射**（两套命名不同、方向代数式一致，务必先建映射表）：

| 用户表名 | 代数式 | allraw / xlsx 名 | 判读（coef>0 时） |
|---|---|---|---|
| Aging | `O_Pre − Y_Pre` | `Y_Pre_vs_O_Pre` | 后 − 前 ⇒ coef>0 = O_Pre 高 |
| DM | `OD_Pre − O_Pre` | `O_Pre_vs_OD_Pre` | coef>0 = OD_Pre 高 |
| Ex_Young | `Y_Post − Y_Pre` | `Y_Pre_vs_Y_Post` | coef>0 = Post 高 |
| Ex_Old | `O_Post − O_Pre` | `O_Pre_vs_O_Post` | coef>0 = Post 高 |
| Ex_DM | `OD_Post − OD_Pre` | `OD_Pre_vs_OD_Post` | coef>0 = Post 高 |

⇒ 命名规律 = `A_vs_B` 表示 **B − A**（coef>0 ⇒ B > A）。**不要**按 `A−B` 读 —— 会整体反号。

---

## 1. 为什么在过滤表里搜不到 MEF2C（用户困惑的根因）

```
过滤表 5 sheet 全查：gene == 'MEF2C'  →  0 行
回原始 5 表：                        →  50 行（5 对比 × 10 亚群，无缺格）
```

两条判据分别看：

| 判据 | 实测 | 结论 |
|---|---|---|
| FDR<0.05（口径 A） | **0 / 50**（min FDR = 0.333） | 严格口径下不显著 |
| `\|coef\|` vs 0.25（口径 B） | max = **0.2058**（O_EX × RP_high(II)） | **全部低于效应量阈值** |

⇒ **MEF2C 属于「被效应量阈值筛掉」，不是「数据里没有 / 漏行」**。
⚠️ 两个判据要**分开报**：口径 A 下它连 FDR 都没过（真阴性），口径 B 下它过了 FDR 但幅度不够。
混成一句「不显著」会丢掉用户需要的区分。

### 家族模糊匹配（必做）

```python
df[df.gene.astype(str).str.upper() == 'MEF2C']              # 精确 → 0 行（过滤表）
df[df.gene.astype(str).str.contains('MEF2C', case=False)]   # 模糊 → 命中 MEF2C-AS1
```

实测命中：

| 基因 | 在过滤表里的表现 |
|---|---|
| **MEF2C**（正义，protein_coding） | 0 命中（`\|coef\|` 全 < 0.25，且口径 A 下全不显著） |
| **MEF2C-AS1**（反义 lncRNA，同一基因座） | **显著 20 行**：Y_EX 1 · O_EX 10 · DM_EX 9，coef **0.257–0.812** |

⇒ 反义 lncRNA 幅度比正义基因**大一个量级**，所以只有它进了共同 DEG 桑基图。
⛔ 若只精确匹配，会答「MEF2C 没变化」，而用户真正在桑基图上看到的是 AS1。

---

## 2. MEF2C 全矩阵（原始 5 表 logFC；全部 FDR ≥ 0.333，无一显著）

| 亚群 | Aging(O−Y) | DM(OD−O) | Ex_Young(后−前) | Ex_Old(后−前) | Ex_DM(后−前) |
|---|---:|---:|---:|---:|---:|
| Pure Type I | −0.142 | −0.006 | −0.065 | +0.150 | +0.205 |
| Pure Type IIA | −0.093 | −0.012 | +0.054 | **+0.415** | +0.221 |
| Pure Type IIX | −0.094 | +0.185 | +0.039 | +0.280 | +0.140 |
| LRP1B+(I) | −0.102 | −0.054 | −0.067 | +0.088 | +0.200 |
| RP_high(I) | **−0.152** | +0.102 | −0.096 | +0.253 | +0.181 |
| RP_high(II) | +0.015 | +0.151 | +0.087 | +0.224 | +0.247 |
| OTUD1+(I) | −0.092 | +0.048 | −0.114 | −0.005 | +0.121 |
| OTUD1+(II) | −0.101 | +0.355 | +0.047 | **+0.451** | +0.087 |
| RSS | **−0.150** | +0.227 | +0.105 | **+0.431** | +0.071 |
| Specialized MF | −0.126 | +0.074 | +0.035 | +0.212 | +0.223 |

**符号一致性汇总**（判「哪个条件真动了」用这个，不看单个最大格）：

| 条件 | 符号一致 | `\|logFC\|` 均值 | 最接近显著 | 判读 |
|---|---|---|---|---|
| Aging | **9/10 负** | 0.107 | RP_high(I) −0.152 (FDR 0.655) | 老年全面偏低 |
| Ex_Old | **9/10 正** | **0.251** | OTUD1+(II) +0.451 (FDR **0.333**) | 幅度最大、最接近显著 |
| Ex_DM | **10/10 正** | 0.170 | RP_high(I) +0.181 (FDR 0.873) | 方向 100% 一致 |
| DM | 7 正 / 3 负 | 0.121 | Pure Type IIX +0.185 (FDR 0.944) | 方向混乱 |
| Ex_Young | 6 正 / 4 负 | 0.071 | RP_high(I) −0.096 (FDR 0.857) | 幅度最小、最弱 |

**结论句式**：「方向高度一致的趋势 —— 衰老↓（9/10 亚群）、运动↑（老年 9/10、糖尿病老年 10/10），
但 **50 个检验无一达到 FDR<0.05，措辞为「未检出显著证据」**。」
⛔ 不可写「MEF2C 在运动后上调」—— 无一对显著。

---

## 3. 两套口径冲突（本会话最重要发现）

### 识别同源：`n_cells` 指纹

```
过滤表    Y_EX  × Pure Type IIX × MEF2C-AS1  →  n_cells = 4079
allraw    Y_Pre_vs_Y_Post × Pure Type IIX × MEF2C-AS1  →  n_cells = 4079   ✅ 同源
```

⇒ **跨表比对前先挑一格比 `n_cells`**（每格细胞数是数据的硬指纹，不会因模型不同而变）。
相等 = 可并置比较；不等 = 两套不同分析，⛔ 不可混用、不可互相校验。

### 冲突形态（同一格 MEF2C × Pure Type I × Aging）

| | 口径 A（原始 5 表 / dreamlet + `(1\|individual)`） | 口径 B（xlsx/allraw，`method=nRUV/glmer/bayesglm`） |
|---|---|---|
| 效应量 | logFC = −0.1423 | coef = −0.1430 |
| FDR | **0.712** | **4.63e-235** |
| 名义 p | 0.4627 | — |
| 全基因显著占比（同一亚群） | 27.8%（2,033 / 7,309） | **99.7%（7,289 / 7,309）** |
| 交集基因 corr(logFC, coef) | **0.6098** | — |

**判读逻辑**：
- **效应量逐行同号、同量级（corr 0.61），MEF2C 逐格两套几乎完全相等** ⇒ **数据/预处理没问题**
  （数据坏了效应量会跟着变）
- **只有 p 值/FDR 崩塌** ⇒ 问题在**自由度 / 观测独立性**：口径 B 疑似把细胞当独立重复（伪重复）
- **99.7% 的基因「显著」** ⇒ 反证：真实生物学不会让 99.7% 的基因改变。这是**显著比例饱和指纹**

**两个指纹的分工**（互补，命中任一都指向检验单位）：

| 指纹 | 形态 | 本会话 |
|---|---|---|
| 方向偏倚指纹 | 上下调严重失衡（如 43:1）⇒ SE 低估 | 已有记录（另一轮） |
| **显著比例饱和指纹** | **显著占比 ~99%** | 本会话：7,289/7,309 |

### 处理协议

1. **两套都摆给用户**，不替他选；说明哪套可信（有样本层随机效应建模的那套）及依据
2. **主动提示下游风险**：桑基图 / 共同 DEG 基于口径 B ⇒ 结论需复核
3. 提示一句话即可，⛔ 不要借机重跑整个下游（那是用户才该拍板的动作，走 `ask_user`）

---

## 4. 取证代码骨架

```python
import pandas as pd, glob, os

# ① 过滤表：家族模糊匹配
xl = pd.ExcelFile(FILTERED_XLSX)
for s in xl.sheet_names:
    d = pd.read_excel(FILTERED_XLSX, sheet_name=s)
    hit = d[d.gene.astype(str).str.contains(TARGET, case=False)]
    # hit 为空 ⇒ 不要停，继续 ②

# ② 未过滤源表（用户本地全量 CSV）
rows = []
for name, path in RAW_TABLES.items():
    d = pd.read_csv(path)
    sub = d[d.gene.astype(str).str.upper() == TARGET].copy()
    sub['contrast'] = name
    rows.append(sub)
M = pd.concat(rows, ignore_index=True)          # → 50 行

# ③ 两条判据分开算
for k, g in M.groupby('contrast'):
    sig = g[g['adj.P.Val'] < 0.05]
    print(k, f'n_sig={len(sig)}/10', f'|logFC|max={g.logFC.abs().max():.4f}',
          f'minFDR={g["adj.P.Val"].min():.3g}')

# ④ 符号一致性（判「哪个条件真动了」）
for k, g in M.groupby('contrast'):
    print(k, f'正={(g.logFC>0).sum()}/10', f'负={(g.logFC<0).sum()}/10',
          f'|logFC|均值={g.logFC.abs().mean():.3f}')

# ⑤ 跨口径同源判定（n_cells 指纹）
key = (TARGET, 'Pure Type IIX')
print(xlsx_ncells[key], allraw_ncells[key])     # 相等 ⇒ 同源

# ⑥ 每列 nunique 检查（direction 类是组级常量）
print({c: d[c].nunique() for c in d.columns})   # ==1 的列不能当逐行属性
```

---

## 5. 本轮落盘产物（可复用路径形态）

| 文件 | 内容 |
|---|---|
| `results/45_MEF2C_raw_5contrasts.csv` | 该基因全部 50 行原始记录（logFC/CI/P/FDR） |
| `results/46_MEF2C_logFC_matrix_5contrasts.csv` | 10 亚群 × 5 条件矩阵 + 各列对应 FDR |

命名规范：`<序号>_<基因>_raw_5contrasts.csv` / `<序号>_<基因>_logFC_matrix_5contrasts.csv`
—— 单基因查询一律留这两份，下次用户追问直接复用，不要重跑。