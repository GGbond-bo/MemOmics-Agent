---
name: gene-set-overlap-analysis
description: 基因集合交并分析（韦恩图 / 多对比共表达交集 / 逆转分析）——建集合、出交集表、**做富集显著性检验**、画可交付韦恩图。触发：韦恩图/venn/画个韦恩图/交集/共表达/三组交集/共同基因/重叠基因/上调和下调分别多少/逆转分析/衰老上调运动后下调/DM上调运动后下调/交集有没有意义/UpSet。
when_to_use: "[gene-set-overlap-analysis] 用户要比较多个对比（contrast）的 DEG 上调/下调基因集合、找交集或'逆转'基因（A 上调但 B 下调），要交集基因清单表或韦恩图时；或已有交集结果、要判断这个重叠到底有没有统计学意义时"
display-name: "Gene Set Overlap Analysis (交集/韦恩 + 富集检验)"
category: bioinformatics
short-description: "多对比基因集合交并：韦恩图 + 交集表 + 重叠富集检验（期望值门）"
starting-prompt: "帮我做韦恩图，看看三组运动交集有什么，上调和下调分别有多少，做成表格。"
---

# 基因集合交并分析（Gene Set Overlap / Venn）

## 核心原则

> **交集数 ≠ 发现。任何交集数字，没有"随机期望值"陪衬就是无意义的。**
> `A_up ∩ B_down = 785` 听起来像结论；它的期望值是 **779**（fold=1.01, P=0.30）——
> 也就是**什么都没发现**。只报 785 就是误导。

三条铁律：

1. **交集必报期望**（期望值 + fold + P）——否则不许把交集清单当"结果"讲。
2. **方向语义先用工具自证**，不许凭对比名字推断 Up/Down 指向谁。
3. **集合口径必须写明**（基因级 / 同亚群级），口径不同数字不可比。

---

## 一、方向语义自证（第一步，不许跳）

DEG 对比表的命名（`Y_Pre_vs_O_Pre`、`A_pre_vs_A_post`）**不保证** coef 正负指向谁 ——
`X_vs_Y` 既可能是 `X−Y` 也可能是 `Y−X`，跨方法（dreamlet / glmer / MAST / DESeq2）惯例不统一。

**做法：读表里的 `direction` 列（或等价注释），并用一行断言自证 `regulation` 与 `coef` 符号一致：**

```python
print(df.direction.unique())                     # 例: ['O_Pre > Y_Pre (coef>0)']  ← 权威语义
print(((df.regulation == "Up") == (df.coef > 0)).all())   # 必须为 True
```

实测样例（骨骼肌 5 对比表）：

| sheet | `direction` 自证 | 于是 Up = |
|---|---|---|
| `Y_Pre_vs_O_Pre` | `O_Pre > Y_Pre (coef>0)` | 衰老上调 |
| `O_Pre_vs_OD_Pre` | `OD_Pre > O_Pre (coef>0)` | 糖尿病上调 |
| `Y_Pre_vs_Y_Post` | `Y_Post > Y_Pre (coef>0)` | 运动后上调 |

⚠️ **别按名字猜**：`Y_Pre_vs_O_Pre` 实际是 `O_Pre − Y_Pre`，光看名字很容易反。

---

## 二、集合口径：三选一，且必须报对照

同一张 DEG 表通常有多个细胞群体（亚群 / celltype）列，**同一个基因可在多个亚群里显著**。
"这个基因算不算进集合"有三种口径，数字差别很大：

| 口径 | 定义 | 什么时候用 |
|---|---|---|
| **gene-level（默认）** | 在**任一**细胞群体显著即计入 | 用户问"哪些基因响应"（基因清单型问题） |
| **same-celltype** | 基因在**同一**亚群里两边都显著 | 严谨的"同一细胞类型内被逆转" |
| **指定亚群子集** | 只在某几个亚群内算 | 与已有图族口径对齐（如只算 8 个 MF 亚群） |

**规范**：默认用 gene-level（不擅自丢细胞群体），**同时在汇总表里附一行"仅 N 个亚群"的对照**，
并在图内写明作用域（`gene-level (significant in any of 10 cell populations); universe N=7,743`）。
实测：本例 8-MF 口径与全 10 群体口径的**三组交集结果完全相同（7 / 2）**，
这种"口径不敏感"本身就是值得写进交付的一句话（说明结论稳）。

⚠️ **不要把"某个亚群没算进去"当默认**——用户的数据里有什么群体就用什么，
要收窄必须说明理由并给对照数（见 [analysis-output-validity-gates] 的"数据完整性"纪律）。

---

## 三、universe（期望值的分母）从哪来

**必须用未过滤的全表**，不能用过滤后的显著表 —— 后者只剩显著基因，分母会小到离谱。

```python
# 各对比全表（merged_*.xlsx）的基因取交集 = 真正被检验过的基因集
g = None
for v in merged_files:
    cur = set().union(*[set(pd.read_excel(v, sheet_name=sh)["gene"]) for sh in sheets])
    g = cur if g is None else (g & cur)
N = len(g)          # 实测 7,743
```

---

## 四、富集检验：交集是否超出随机

**两集合 → 精确超几何**（单尾，`P(X>=obs)`）；**三集合 → 置换检验**（无现成精确检验）。

```python
# 两集合：精确、零依赖（math.comb 大整数无溢出）
exp = nA * nB / N
p = sum(math.comb(nA, k) * math.comb(N - nA, nB - k) / math.comb(N, nB)
        for k in range(obs, min(nA, nB) + 1))

# 三集合：从 universe 随机抽同大小集合，布尔数组算交（快）
exp3 = nA * nB * nC / N**2
for _ in range(5000):
    ms = []
    for k in (nA, nB, nC):
        m = np.zeros(N, bool); m[np.argpartition(rng.random(N), k)[:k]] = True
        ms.append(m)
    hit += (ms[0] & ms[1] & ms[2]).sum() >= obs
p = (hit + 1) / (5000 + 1)
```

**结果必须成表**（`comparison | n1 | n2 | overlap | expected_by_chance | fold_vs_chance | P_value | test`）。

### 🔴 覆盖率陷阱 —— 本类分析最容易出的假发现

**当一个集合占了 universe 的绝大部分时，"大交集"是必然的、且可能是空集意义上的负结果。**

实测（骨骼肌 5 对比，universe N=7,743）：

| 交集 | 观测 | 期望 | fold | P | 判读 |
|---|---|---|---|---|---|
| Aging↑(6,571) ∩ Ex_Old↓(918) | **785** | 779 | **1.01** | **0.30** | ❌ **不富集**，785 = 覆盖率的算术后果 |
| Aging↓(112) ∩ Ex_Old↑(68) | **27** | 1.0 | **27.5** | 3.2e-33 | ✅ 真信号 |
| DM↑(40) ∩ Ex_DM↓(60) | 13 | 0.3 | **41.9** | 9.3e-19 | ✅ 真信号 |
| DM↓(82) ∩ Ex_DM↑(60) | 5 | 0.6 | **7.9** | 4.1e-04 | ✅ 真信号 |

**Aging↑ 占 universe 的 85%**（6,571/7,743）—— 全基因组几乎全在里面，
任何 Ex_Old↓ 基因都"自动"落进去 ⇒ 785 ≈ 918 × 85%，与随机无异。
**此时"逆转"清单（785 个）不能当逆转基因集交付**，必须显式说明它是覆盖率后果。

**为什么要留个心眼**：这类"通吃型集合"通常是**上游统计失校**的症状
（SE 被压小 → 假阳性膨胀 → 显著率 50%+，up:down 极度不对称）——
先查 [analysis-output-validity-gates] §六 六问诊断，再谈交集。**修分母优先于修阈值/口径**。

**报告措辞模板**：
- 富集：`overlap 27 | expected by chance 1.0 | fold 27.5 | P = 3.2e-33`
- 不富集：`overlap 785 但期望 779（fold 1.01, P=0.30）——该方向受上游"通吃集合"污染，不构成逆转证据；真信号在反方向（27 个, fold 27.5）`

### 共享组的分母依赖（读结果时必想一层）

若两个对比**共享一组**（`A_pre_vs_B_pre` 与 `A_pre_vs_A_post` 共享 `A_pre`），
两个估计量天然负相关 ⇒ "反向显著"类交集（A↑ 且 B↓）会被人为抬高。
发现此类交集时，**同时报共享组、并说明该结构性依赖**，别当成独立证据。

---

## 五、画韦恩图（手绘几何 + 确定性版式自检）

`matplotlib_venn` 常常没装（不要为它装包）——手绘 20 行即可，且能完全控制标签位置。

**几何（保证中心区存在）**：三圆半径 `r`、圆心距原点 `R`，**必须 `R < 2r/√3`**，
否则三圆不交于中心 → "三组共同"格子不存在。实测可用 `R=0.50, r=0.62`（阈值 0.716）、
两圆 `r=0.78, dx=0.50`。

**🔴 版式三坑（本类图必踩，实测全中）**：

| 坑 | 症状 | 修法 |
|---|---|---|
| 集合名左右相撞 | `Aging UP (Old vs Young` 与 `Ex_Old DOWN` 粘成 `Aging UP (Old vs Youngx_Old DOWN` | 标签**外侧角对齐**（`x=±1.52` + `ha="left"/"right"`）+ 用**集合色**着色标归属；或短标签 |
| 长标签**越出画布跑进隔壁面板** | 3 集合图里 `Exercise-Diabetes` 与邻图 `Exercise-Old` 粘成 `Exercise-DiabeteExercise-Old` | 标签**贴边朝内经**（`x=+1.30, ha="right"` 时向左延伸）；或缩短为短名（`Young/Old/Diabetes`），把完整对比名放副标题 |
| 顶部集合名撞面板标题 | `'Exercise-Young\n(up)' ⋂ 'A Shared UP-regulated genes…'` | 顶部标签 `va="bottom"` 要给足 `ylim` 余量（实测 `ylim` 顶从 1.25 提到 1.52，标签放 `y=1.16`）；2 行标签需要 ≥0.35 数据单位 |

**⛔ 别靠肉眼/OCR 猜版式**——OCR 会把相邻文本读成一条粘连字符串（能发现"粘了"），
但**判定和修法必须用包围盒**：见第六节。

---

## 六、把版式自检焊进出图函数（关键工作流）

**问题**：出图 → 读图 → 发现标签粘连 → 改 → 重跑 … 的迭代会连吃**循环检测干预**
（实测本类任务因此重跑 3 轮、两度收到"判定为循环失控"）。

**解法**：把自检写进 `save()`，**一次运行就给出越界/重叠的确定性数字**：

```python
def save(fig, stem):
    fig.canvas.draw(); r = fig.canvas.get_renderer()
    W, H = fig.bbox.width, fig.bbox.height
    tx = [(t, t.get_window_extent(r)) for ax in fig.axes
          for t in list(ax.texts) + [ax.title] if t.get_text()]
    ovf = [t.get_text()[:26] for t, b in tx
           if b.x0 < -1 or b.x1 > W + 1 or b.y0 < -1 or b.y1 > H + 1]
    coll = [(a.get_text()[:18], b.get_text()[:18])
            for i, (a, A) in enumerate(tx) for b, B in tx[i + 1:]
            if A.x1 > B.x0 + 1 and B.x1 > A.x0 + 1 and A.y1 > B.y0 + 1 and B.y1 > A.y0 + 1]
    print(f"  版式自检 {stem}: 越界 {len(ovf)} | 重叠 {len(coll)}"
          + (("  ⚠ " + "; ".join(map(str, ovf + coll))) if (ovf or coll) else " ✓"))
    for ext in ("png", "pdf", "svg"):
        fig.savefig(f"{OUT}/{stem}.{ext}", dpi=300, bbox_inches="tight", facecolor="white")
```

现成工具：`scripts/mpl_text_layout_audit.py`（可直接 import 的 `audit_figure_layout(fig)` / `save_figure(...)`）。

**交付前的三条硬判据**（都要求算出数字）：
1. `越界 0 | 重叠 0` —— 两张图都过
2. 计数正确：OCR/包围盒核对每个韦恩格子的数字 = 集合运算结果
3. 导出：PNG 300dpi 非空（墨迹占比 5–35%）+ PDF `FontFile` 内嵌（`pdf.fonttype=42`）+ SVG 文字可编辑

---

## 七、交付形状（用户口径）

| 用户说 | 交付 |
|---|---|
| "做成一个表格" | **交集区计数表** + **交集基因明细表**（每基因在各对比的 coef / FDR / 命中亚群）+ 一行 `key_genes_plaintext.txt` 便于贴正文 |
| "上调和下调分别有多少" | **必须分上调/下调两张韦恩**（不是一张），计数表按 `regulation × venn_region` 两列展开 |
| "不要把事情搞复杂" | 只给结论数 + 清单 + 产物路径；**不要**附方法学长文、不要多套方案、不要追问"要不要我再…" |

**交集明细表的规范列**（每基因一行）：
`regulation | gene | <对比A>_subclusters | <对比A>_max_absCoef | <对比A>_minFDR | <对比B>_… | n_groups_sig`
—— 亚群列表用 `;` 连接（一个基因可在多亚群显著），不要只留一个亚群。

---

## 八、坑表

| 现象 | 根因 | 处置 |
|---|---|---|
| 交集数很大（几百上千）但"没意义" | 某集合覆盖 universe 绝大部分（通吃型，上游 SE 失校） | 报期望/fold/P；退回 [analysis-output-validity-gates] §六 修分母 |
| 反向交集（A↑∩B↓）数量异常多 | 两对比**共享一组** → 估计量负相关 | 显式声明结构性依赖，别当独立证据 |
| 换个亚群口径数字大变 | gene-level vs same-celltype 口径不同 | 报对照行 + 图内写明作用域 |
| 韦恩格子数字与集合运算不符 | 手填/硬编码了计数 | 必须由 `len(A & B - C)` 这类运算生成；跑完用包围盒/OCR 核一遍 |
| 标签粘连/越界 | 见第五节三坑 | 用第六节的包围盒自检，一次跑完判定 |
| `matplotlib_venn` 未装 | 环境无此包 | **不要装**，手绘 20 行（几何见第五节） |
| 过滤表当 universe | 分母只剩显著基因 | universe 必须取自**未过滤全表** |

---

## 参考与脚本

- `scripts/mpl_text_layout_audit.py` —— **确定性版式自检**（包围盒越界 + 两两重叠），
  可直接 `import` 进任何 matplotlib 出图脚本；`save_figure(fig, stem, outdir, audit=True)` 一步导出
  PNG/PDF/SVG 并打印自检结果。**任何多面板图都建议焊上它**（不限于韦恩图）。
- `scripts/venn_overlap_toolkit.py` —— 本类分析的可复用引擎：读多对比 DEG 表 → `direction` 语义自证
  → 建集合（gene-level / 指定亚群 / same-celltype）→ 精确超几何（2 集）+ 置换检验（3 集）
  → 手绘 3 集合/2 集合韦恩（含内置版式自检）→ 输出计数表与明细表。
- `references/overlap-vs-chance-and-venn-layout.md` —— 完整实录：骨骼肌 5 对比（universe 7,743）
  的覆盖率陷阱定量证据、三处标签缺陷的 OCR 发现 → 包围盒修复全过程、几何推导与实测参数。
- 相关 skill：`analysis-output-validity-gates`（通吃型集合的上游诊断 + 效应量阈值门）、
  `platform-execution-pitfalls`（出图迭代触发循环检测的处置）、
  `academic-figure-skill` / `cns-visualization`（发表级出图规范）。