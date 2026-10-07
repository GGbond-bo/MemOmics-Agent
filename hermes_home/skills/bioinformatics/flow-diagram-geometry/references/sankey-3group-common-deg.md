# 实战案例：三组运动共同 DEG「亚群 → 基因」桑基图

> 2026-10-01 · human / skeletal_muscle / exercise+aging · 脚本 `43_sankey_3group_common_deg.py`（v4）
> 产物：`figures/43_sankey_3group_common_{UP,DOWN}.{png,svg,pdf,tiff}` + `results/43_sankey_links_3group_common.csv`

## 需求原话与解读

> "帮我做一个桑葚图，就是把三组锻炼后一起上调或者下调显著的基因展示出来，这个基因来自哪个亚群，左边亚群，右边基因。两个桑葚图。"

解读：**"桑葚图" = 桑基图 Sankey**；"三组锻炼后" = 三个运动前后对比（Post vs Pre）；
"一起上调/下调" = 基因层面**严格交集**；两张图 = 上调一张、下调一张。

## 数据与口径

源表 5 个 sheet（`DEG_fdr05_coef025_5contrasts_formatted.xlsx`）：

| sheet | 对比 | 基因数 | Up | Down |
|---|---|---|---|---|
| Aging | Y_Pre_vs_O_Pre | — | — | — |
| DM | O_Pre_vs_OD_Pre | — | — | — |
| **Y_EX** | Y_Pre_vs_Y_Post | 47 | 28 | **19** |
| **O_EX** | O_Pre_vs_O_Post | 985 | 68 | **918** |
| **DM_EX** | OD_Pre_vs_OD_Post | 120 | 60 | 60 |

阈值：FDR < 0.05 且 |coef| ≥ 0.25（bayesglm / glmer）。10 个亚群。

**交集（gene 层面，三组都显著）**：Up = 7 个 · Down = **仅 2 个**（被 Y_EX 的 19 个下调基因卡住）。

| 图 | 基因数 | 亚群 | 去重链路 | 其中三组共同支持 |
|---|---|---|---|---|
| UP | 7（AC015878.1 / AGBL1 / ITIH4 / LDB3 / MEF2C-AS1 / MYH2 / PALLD） | 10 | 56（原始记录 102） | **6 条** |
| DOWN | 2（CMYA5 / RHOBTB1） | 10 | 19（原始记录 24） | **0 条** |

支撑度最高：`ITIH4` 与 `MEF2C-AS1`、`PALLD` 均覆盖 **10/10 亚群**。

三组都支持的 6 条链路（画出来最粗）：
`OTUD1+(II)→ITIH4`、`OTUD1+(II)→PALLD`、`Pure Type IIX→AC015878.1`、
`Pure Type IIX→MEF2C-AS1`、`Pure Type IIX→MYH2`、`RP_high(II)→ITIH4`。

## 最终版式参数（可直接复用）

| 参数 | 值 |
|---|---|
| 画布 / dpi | `figsize=(11.2, 7.6)`, png & tiff `dpi=300` |
| `xlim / ylim` | `(-0.30, 1.30)` / `(-0.06, **1.34**)` |
| 节点条宽 `NODE_W` | `0.022` |
| 侧边空隙 `gap` | `0.022 * tot / (n-1)` |
| 列标题 y | `1.21`（`va="bottom"`），左 `"Subcluster"`、右 `"Shared up/down genes (…, n=)"` |
| 标签字号 | 节点标签 9.2、列标题 10.5 bold、主标题 13.5 bold（`fig.text(0.5, 0.972)`） |
| 图例 1 / 2 | `bbox_to_anchor=(-0.005, -0.030)` / `(-0.005, -0.125)`，均 `ncol=3` |
| 脚注 1 / 2 | `fig.text(0.5, 0.044 / 0.016, …, va="top", fontsize=8.2, color="#666666")` |
| `subplots_adjust` | `left=0.01, right=0.99, top=0.902, bottom=0.21` |
| 宽度配色 | Up `{3:"#A50026", 2:"#F46D43", 1:"#FDBE85"}`；Down `{3:"#08519C", 2:"#4292C6", 1:"#C6DBEF"}` |
| 亚群配色 | Pure 族 `#7A7A7A`、Mixed 族 `#B08A5A`、Specialized `#5A8AA5` |
| 亚群排序 | Pure Type I → IIA → IIX → LRP1B+(I) → RP_high(I)/(II) → OTUD1+(I)/(II) → RSS → Specialized MF（与其火山图/柱状图 ORDER 约定一致） |
| 右侧排序 | 按总支撑度降序 |

## 碰撞定位全过程（可复用的排查路径）

1. **全图 OCR** → 26 条文字，10 个亚群标签全在、6 个基因标签在，**唯独权重最大的 `ITIH4 (22)` 没被检出**。
2. **疑似**：按 layout 手算它中心在 y≈0.8946，应该最靠上 → 靠近列标题。
3. **裁剪右轴顶部**（`im.crop((2550,120,3352,560)).resize(2x)`）→ OCR 拿到
   `ITIH4 (22)` @(2742,409) 与 `Shared up genes` @(2733,439) → **同一 x 起点、y 差仅 30px（原图 15px）→ 判定重叠**。
4. **像素行带法佐证**：右轴 x∈[2680,3352] 暗像素行剖面显示 y=204–252 只有**一条 48px 高的行带**，
   却要装两行文字（9.2pt≈38px + 10.5pt≈44px）→ 结构性装不下，证实重叠。
5. **修复**（v3）：`ylim` 上沿 1.20→1.34、两处列标题 y 1.105→1.21。
6. **复验**：OCR 得列标题 @288、`ITIH4 (22)` @**394** → 分离 **106px**，7 个基因标签全部检出 ✅。
7. **新问题浮现**：加了双行脚注后，OCR 把图例第二行与脚注读成一串乱码（同为 y≈2035）→
   脚注从 axes 负坐标改用 **figure 坐标锚底**（v4）→ 复验：图例 y=2044 → 脚注 y=2150 / 2206 **三行分离** ✅。

## 审查与沉淀记录

- `rail_review(post)`：**passed=true / issues=[]**，figure_count=17
  （warning 项：无注释行、无 try 捕获、matplotlib 子模块未在 skill 声明 —— 均非阻断）
- `record_run` → `cns-visualization`（human / skeletal_muscle / exercise+aging，quality 8）
- v2 备份：`figures/_backup_sankey_v2/`（8 文件）

## 汇报要点（用户最在意的三条）

1. 两张图 + 四格式路径 + 链路 CSV 路径；
2. **口径偏差主动提示**：Y_EX 下调仅 19 个 vs O_EX 918 个 → 交集被卡到 2 个基因，且这 2 个基因
   **没有任何亚群在三组中都显著**（共同支持 0 条）；把"放宽到 ≥2 组"作为选项交给用户；
3. 本轮实际修掉的版式缺陷逐条列出（含修复前后 OCR 坐标），并附 v2 备份路径可回退。