# 交集/逆转分析实录：覆盖率陷阱 + 韦恩版式三坑

来源：骨骼肌 DEG 五对比（人，skeletal_muscle，exercise + aging + diabetes），
数据 = 新方法细胞级 bayesglm + RUV，按 `FDR<0.05 & |coef|≥0.25` 过滤后的 5 sheet 表；
universe = 5 张未过滤 merged 全表基因交集 = **7,743**（全 10 个细胞群体）/ 7,485（仅 8 个 MF 亚群）。

---

## 一、方向语义自证（先做，一次调用）

```python
xl = pd.ExcelFile(XL); D = {s: xl.parse(s) for s in xl.sheet_names}
for s, df in D.items():
    print(s, df.direction.unique(), ((df.regulation == "Up") == (df.coef > 0)).all())
```

实测输出（**这就是权威语义，名字靠不住**）：

| sheet | direction | Up 含义 | 过滤后 rows / genes |
|---|---|---|---|
| `Y_Pre_vs_O_Pre` | `O_Pre > Y_Pre (coef>0)` | 衰老上调 | 23,178 / 6,679 |
| `O_Pre_vs_OD_Pre` | `OD_Pre > O_Pre (coef>0)` | 糖尿病上调 | 311 / 120 |
| `Y_Pre_vs_Y_Post` | `Y_Post > Y_Pre (coef>0)` | 运动后上调 | 115 / 47 |
| `O_Pre_vs_O_Post` | `O_Post > O_Pre (coef>0)` | 运动后上调 | 1,846 / 985 |
| `OD_Pre_vs_OD_Post` | `OD_Post > OD_Pre (coef>0)` | 运动后上调 | 246 / 120 |

过滤口径自检：`min|coef| = 0.2500`、`maxFDR = 0.0495`、
`(regulation=="Up") == (coef>0)` **全表 True** ⇒ 过滤真的生效、方向无歧义。

⚠️ **`Y_Pre_vs_O_Pre` 实际是 `O_Pre − Y_Pre`** —— 只按名字推 Up/Down 会整体反掉。

---

## 二、覆盖率陷阱的定量证据（本类分析最贵的教训）

### 观测 vs 期望

| 交集 | 观测 | 期望 | fold | P（超几何，单尾） | 判读 |
|---|---|---|---|---|---|
| 三组运动共同上调 | 7 | 0.002 | 3674 | 2.0e-04（置换） | ✅ |
| 三组运动共同下调 | 2 | 0.017 | 115 | 2.0e-04（置换） | ✅ |
| **Aging↑ ∩ Ex_Old↓** | **785** | **779** | **1.01** | **0.30** | ❌ **不富集** |
| Aging↓ ∩ Ex_Old↑ | 27 | 1.0 | 27.5 | 3.2e-33 | ✅ |
| DM↑ ∩ Ex_DM↓ | 13 | 0.3 | 41.9 | 9.3e-19 | ✅ |
| DM↓ ∩ Ex_DM↑ | 5 | 0.6 | 7.9 | 4.1e-04 | ✅ |

### 根因算术

`Aging_up = 6,571` 基因，universe `7,743` ⇒ **覆盖率 84.9%**。
`Ex_Old_down = 918` ⇒ 随机期望 `6,571 × 918 / 7,743 = 779`。
观测 785 ≈ 779 ⇒ **785 完全是覆盖率的算术后果，不是生物学**。

**判据（可直接复用）**：
> 若 `|A| / N > 0.5`，则任何 `A ∩ B` 的"大交集"都要先算期望再解读；
> 尤其 `观察/期望 ≈ 1` ⇒ 该方向**零信息**，必须显式写出来，不能只报数字。

### 为什么会出现通吃型集合

上游统计失校的信号（本会话五对比里 Aging 组全部命中）：
- 显著率 98%（6,571 up vs 112 down）—— up:down ≈ **59:1**，健康应≈1:1
- SE 被压小 ~26 倍 → p 值失去分辨力
- 结论：**先修分母，再谈交集/阈值/口径**（见 `analysis-output-validity-gates` §六）

### 结构性依赖（共享组）

`Aging (Y_Pre vs O_Pre)` 与 `Ex_Old (O_Pre vs O_Post)` **共享 `O_Pre` 组** ⇒
两个估计量天然负相关 ⇒ "反向显著"交集（A↑∩B↓）被人为抬高。
本会话早前实测：两对比符号一致率仅 15.7%（远低于独立假设的 50%），
即该结构性负相关确实存在。**报此类交集时必须声明共享组，不得当独立证据。**

---

## 三、韦恩图版式三坑（OCR 发现 → 包围盒定位 → 修复）

### 发现过程（可复用）

1. **OCR（vision_describe）能发现"粘了"**：
   - `"Aging UP (Old vs Youngx_Old DOWN (Post vs Pre)"` ← 左标签末字与右标签首字重叠（`Ex_` 的 E 被吃掉）
   - `"Exercise-DiabeteExercise-Old"` ← 跨面板粘连
   - `"A  Shared UP-regulatedgengs after exercise"` ← 标题 OCR 噪声（**假阳性，不是真缺陷**）
   ⚠️ 所以 OCR **不能**当判定器：既有假阳性（标题噪声）也可能漏检（亚像素贴合）。
2. **包围盒（matplotlib window_extent）才是判定器**：
   第一次焊进 `save()` 就精确报出 `'Exercise-Young\n(up)' ⋂ 'A Shared UP-regul'` —— 顶部集合名
   向上越出坐标区、撞面板标题。

### 三个缺陷与修法

| # | 缺陷 | 根因 | 修法 |
|---|---|---|---|
| 1 | 2 集合图左右集合名相撞 | 两标签都 `ha="center"` 靠得近，长名（23 字 ≈ 2.0 in）在 1.87 单位/in 的面板上横向铺开 → 两侧互相侵入 | 改**外侧角 + 集合色**：`(-1.52, 1.15, ha="left", color=ca)` / `(1.52, 1.15, ha="right", color=cb)`；同时缩短标签（`Aging UP` / `Ex_Old DOWN`），完整对比名移到副标题 |
| 2 | 3 集合图长标签**越出画布跑进隔壁面板** | `x = cen[2].x + r*0.72 = 0.879` + 17 字（≈1.5 in ≈ 2.8 单位）向右延伸 → 到 3.7 单位，远超 `xlim=±1.35` | 标签**贴边朝内经**：`(-1.30, -0.95, ha="left")` / `(1.30, -0.95, ha="right")`；或整体缩短为 `Young / Old / Diabetes` |
| 3 | 顶部集合名撞面板标题 | `names[0]` 放 `y = cen[0].y + r + 0.12 = 1.22` 且 `va="bottom"`，2 行标签向上占 ~0.35 单位 → 穿出 `ylim` 顶（1.25） | `ylim` 顶提到 **1.52**，标签放 `y=1.16 va="bottom"` 且改单行；标题 `pad=16` 留距 |

### 几何（保证中心区存在）

3 个等圆，圆心距原点 `R`、半径 `r`，中心三交区存在 ⟺ **`R < 2r/√3`**。
- 实测可用：`R=0.50, r=0.62`（阈值 0.716 ✓）；圆心角 90°/210°/330°
- 两圆：`r=0.78, dx=0.50`（圆心距 1.0 < 2r=1.56 ✓）
- 区域数字落点（3 集合）：`A=(0,R+.35)`、`B/C` 在各自圆心外侧、`AB=(-.47,.27)`、`AC=(.47,.27)`、`BC=(0,-.34)`、`ABC=(0,0)`

### 验收（确定性，不用肉眼）

```
版式自检 fig_venn_exercise_shared_updown: 画布 1150x520 | 文字 24 个 | 越界 0 | 重叠 2  ⚠ ...
版式自检 fig_venn_reversal_aging_diabetes: 画布 1250x1060 | 文字 28 个 | 越界 0 | 重叠 0 ✓
        ↓ 修完顶部标签后
版式自检 fig_venn_exercise_shared_updown: 画布 1150x520 | 文字 24 个 | 越界 0 | 重叠 0 ✓
```

### 顺带核到的两个假警报（别再重复排查）

| 警报 | 真相 |
|---|---|
| SVG 里出现 `http://...` ⇒ 疑似字体 CDN 外链 | 只有 W3C DTD / xlink **命名空间** URL；`@import`=0、`url(http:`=0、`fonts.googleapis`=False；`font-family` 是本地 `Arial/Helvetica/DejaVu Sans` ⇒ **无外链** |
| OCR 把标题读成 `"Shared UP-regulatedgengs"` ⇒ 疑似标题粘连 | 单行 Text 对象不可能自我重叠；这是粗体标题的 OCR 噪声 ⇒ **必须用包围盒复核再改** |

---

## 四、交付清单（本类任务的完整产物）

```
task4/
├── figures/
│   ├── fig_venn_exercise_shared_updown.{png,pdf,svg}     # 3 集合：上调/下调两面板
│   └── fig_venn_reversal_aging_diabetes.{png,pdf,svg}    # 2 集合 2x2：逆转衰老/糖尿病
├── results/
│   ├── table1_exercise_venn_regions.csv          # 7 个韦恩区 × up/down 计数
│   ├── table2_exercise_shared_genes_detail.csv   # 交集基因明细（含 coef/FDR/亚群）
│   ├── table3a/3b/4a/4b_*.csv                    # 四个逆转方向明细
│   ├── table5_summary_counts.csv                 # 总览（含口径对照行）
│   ├── table6_overlap_significance.csv           # 期望/fold/P/test/verdict
│   ├── table7_set_sizes.csv                      # 各集合规模速查
│   └── key_genes_plaintext.txt                   # 一行速贴清单
└── scripts/01_venn_exercise_reversal.py
```

图规格：300 dpi PNG（画布 1150×520 / 1250×1060）+ 矢量 PDF（`FontFile` 内嵌）+ SVG（`<text>` 可编辑，24–31 个）。
墨迹占比 0.31–0.32（非空判据 5–35% ✓），16/16 分块非空。

---

## 五、复现基线（改数据时先对这几个数）

| 量 | 基线值 |
|---|---|
| universe（全 10 群体 / 仅 8 MF 亚群） | 7,743 / 7,485 |
| 三组运动共同上调 / 下调 | **7 / 2**（两口径**完全相同** ⇒ 口径不敏感，可写进交付） |
| 每组运动 up 数（Young / Old / DM） | 28 / 68 / 60 |
| 每组运动 down 数 | 19 / 918 / 60 |
| 逆转衰老 A / B | 785（不富集）/ 27（fold 27.5） |
| 逆转 DM A / B | 13（fold 42）/ 5（fold 7.9） |
| 2 集合标签最小间隙（修好后） | ≈0.32 数据单位 ≈ 51 px @300dpi |

⚠️ notebook/HTML 模板里的原图可能是**另一代亚群命名**（`Type_I/II/IIX`、`GALNTL6_I/II`、
`ANKRD1_II`、`BMPR1B_MF` 等 9 个）—— 那种情况只能当**样式模板**用，
不能拿它反推当前数据的集合顺序或数量（本会话实测：两套命名不同代，原顺序无从复原）。