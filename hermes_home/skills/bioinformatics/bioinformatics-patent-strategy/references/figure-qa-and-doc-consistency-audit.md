# 附图质检与交付件一致性审计（交底书/说明书）

> 来源：跨物种衰老可替代性专利 v11→v12（memomics-7839e23a，2026-09-12）。
> 触发语：**「这个路径下的内容是不是交底书的来源？」「交底书的图是不是正确的？每张图都检查一下，看看有没有遮挡」「都修」**。
> 与 §11「附图逐张核对铁律（一期）」和「源图漏重出（二期）」互补：一期管**图有没有内容**，二期管**图有没有重出**，
> 本文管 **图里的曲线是不是真的、文字有没有被压住、声明的脚本存不存在**。

---

## 0. 三类必须查的附图缺陷（按危害排序）

| # | 缺陷 | 危害 | 一句话检测法 |
|---|------|------|-------------|
| 1 | **伪造曲线**（fabricated curve） | 最致命：专利附图用拟合/近似曲线冒充实测分布 = 不实呈现 | 打开出图脚本，看曲线数据是**算出来的**还是**几个硬编码常数造出来的** |
| 2 | **文字遮挡**（occlusion） | 图上数字看不见，答辩/审查被追问即穿帮 | OCR 全部文字框 → 两两求交 → 交集即嫌疑 |
| 3 | **图表/脚本不一致** | 表列 N 个方法、图 D 画 M 个；复现脚本清单点名不存在的文件 | 逐表与源 CSV/磁盘比对行数与文件名 |

---

## 1. 🔴 伪造曲线：专利附图的头号风险

### 症状长什么样

```python
# ❌ 反面标本（本次实锤，file: regen_figures_v2.py 第 20 行）
obs, null_mean, null_sd, p, ratio = 6285, 258, 1075, 0.005, 24.3   # ← 五个数字硬编码
theta = null_sd**2 / null_mean                                     # ← 矩匹配
k = null_mean / theta
xs = np.linspace(0.5, obs * 1.6, 4000)
pdf = stats.gamma.pdf(xs, a=k, scale=theta)                        # ← 造一条"空分布曲线"
ax.plot(xs, pdf, label="shuffle 空分布（年龄标签随机打乱）")
ax.annotate(f"富集 {ratio} 倍\np = 0.005", ...)                     # ← 标注也是硬编码文本
```

**判据**：绘图脚本里出现 `pdf = stats.<分布>.pdf(...)` / `spline` / 曲线拟合，且输入是**字面量常数**而非数据列
→ 该曲线**不是实测结果**，是编的。图注里写「shuffle 空分布」而曲线是 gamma 拟合 = 图文双重不实。

### 为什么必须修

- 统计学上无意义：`null_sd=1075.14 > null_mean=258.4`，真实空分布极度右偏，**形状完全不是 gamma 拟合的样子**。
- 专利法上危险：审查员/对手只要问一句「这个空分布的原始置换值在哪」，图就废了。
- **注意区分**：本例的**统计量本身是真的**（归档于 `P3_L1_data/v8_age_shuffle_stats.rds`），只有**曲线形状是假的**。
  所以修法是**保留统计量、换掉图形**，不是推翻数字。

### 正确处置（本次采用）

改为**只呈现可回溯的归档统计量**，不画任何拟合曲线：

```python
st = pd.read_csv(os.path.join(RES, "置换检验统计.csv"))   # 由 R 脚本从 rds 导出
h = st[st["species"] == "human"].iloc[0]
ax.barh(["shuffle 空分布", "真实显著元件"], [h["null_mean"], h["obs"]], ...)
ax.text(..., "富集 %.1f 倍　p = %g\n空分布 200 次置换；均值 %.1f，SD %.1f\n检验单元 %s 个"
            % (h["ratio"], h["p"], h["null_mean"], h["null_sd"], format(int(h["n_units"]), ",")))
```

并在图注里写明**检验单元数与口径无关性**，例如：
「检验单元为人侧 525,137 个 peak/tile（该检验基于人侧自身矩阵，与 M5 输入口径切换无关）」。

> ⚠️ **不要重算**：若原始置换脚本已丢失（本次全目录 grep 无任何脚本引用输入对象 `human_Hf_ATAC_40_clustered.rds`），
> **禁止凭空重算**——重算出来对不上归档值（6285）反而制造新数字漂移。正确做法是导出归档统计量 + 出图脚本入库。

### 顺带的红线：归档统计量与内部文档对不上时以归档为准

本次 `结论_口径决策链.md` 记猴侧 shuffle「富集 **1.17** 倍（p=0.267）」，而 `v8_age_shuffle_stats.rds` 是
`ratio=0.2309, p=0.815`（方向相反！）→ 按归档对象订正为「无富集（0.23×，p=0.815）」。
**凡「同一检验有两处数字」先查归档 rds/csv 原始字段，不要信叙述性 md。**

---

## 2. 🔴 遮挡检测：客观法，不要肉眼看

`scripts/check_figure_occlusion.py`（本 skill 自带，直接跑）：

```bash
python scripts/check_figure_occlusion.py <图.png> --expect "58.7%" "827/1409" "35/67"
```

脚本做三件事：
1. **边缘裁切检测** — 非白像素是否触边（触边 = 内容被裁出画布）；
2. **关键标签命中** — 把你预期的数值标签逐个在 OCR 结果里查，缺哪个就报哪个；
3. **文字框两两相交** — IoU（除以**较小**框面积）> 0.05 的成对列出 = 疑似遮挡。

### ⚠️ 必须排除的假阳性：多行刻度标签

9 对「交叠」实测全部是 **matplotlib 两行 y 轴刻度标签**自身的上下行：
`'基线①a' <-> '对称min+同向'`、`'基线②a' <-> 'meta |Z|≥12'` …
OCR 把一行标签切成两个紧邻框 → 天然相交。**判读规则**：两边文字同属一个刻度标签（前缀相同）→ 不是遮挡。
真正的遮挡是**图例文字 压 数值标签**（两边文本形态完全不同，如 `'基线③单物种筛选' <-> '58.7% (827/1409)'`）。

### 本次根因（可复用的代码模式）

```python
tab = tab.iloc[::-1].reset_index(drop=True)   # 反转行序 → 基线③c 落到最底行
...
axes[0].legend(..., loc='lower right')        # 图例锚右下 → 正好压住最底行末端
for i, (v, n, nr) in enumerate(zip(...)):
    ax.text(v*100 + 1.2, i, f'{v*100:.1f}%  ({nr}/{n})', va='center', ...)   # 每行都画了标签
```

**模式总结**：`barh` + 行序反转 + 图例落在 `lower right`/`lower left` + **每行都画数值标签**
⇒ 必然压住最底/最顶一行。凡见 `loc='lower *'` 且逐行标注，先怀疑。

### 修法（本次采用，保持两面板对齐）

```python
fig.legend(handles=[Patch(facecolor='#C0392B', label='本方法'),
                    Patch(facecolor='#E67E22', label='基线① 独立筛选取交集'),
                    Patch(facecolor='#2980B9', label='基线② 合并Z meta'),
                    Patch(facecolor='#7F8C8D', label='基线③ 单物种筛选')],
           fontsize=8.2, loc='lower center', bbox_to_anchor=(0.5, -0.055),
           ncol=4, framealpha=.95)          # ← 移到画布底部、绘图区之外
```

要点：`fig.legend`（不是 `axes[i].legend`）+ 负 y 锚点 + `ncol=4` 横排 → 配合 `savefig(bbox_inches='tight')` 自动纳入画布。
修复后必须**再跑一次检测脚本**确认 9 个标签全部可读。

---

## 3. 🔴 OCR 误读 vs 图真错：决定性判别法

**问题**：OCR 把 ⑤ 读成 ③、把「阈」读成「阀」时，怎么知道是图错了还是 OCR 错了？

**判别法（本次实证，一步定案）**：**用同一字体渲染「正确字符串」，再 OCR 它一次。**

```python
# 用出图脚本同一字体/字号渲染 ⑤置换定阈+分级，再对渲染结果跑 OCR
# 结果：仍被读成 "③置换定阔+分级"  →  OCR 认不出这个字形，图本身无误
```

- 正确字符串**也被误读** ⇒ **OCR 字形识别缺陷**，图没问题，**不要改图**。
- 正确字符串**读得对**、只有被测字符串读错 ⇒ 图真的错了，去改源脚本。

配套：**字形像素级比对**（裁出两处圆码数字，二值化算 IoU）——本次步骤③与步骤⑤数字 IoU 仅 0.294
（看着"不同"），但裁切宽度不固定有干扰 ⇒ **IoU 只能作提示，不能作判据**，必须回到上面的渲染-复 OCR 测试。

> 承接 §11 f)/h)：OCR 对**框数量/大布局**可靠，对**小字/下标/字形细节**不可靠。
> 本次补充的是：**不可靠时如何在 5 分钟内把责任判给 OCR 还是图**，而不是含糊标"需人工确认"。

---

## 4. 交付目录 ↔ 交底书一致性审计（回答"这是不是交底书的来源"）

固定四步，每步都要给实测证据：

| 步 | 查什么 | 本次结果 |
|---|-------|---------|
| 1 | 找到 docx 的**生成脚本**，读它的输入路径（`FIG = ...`、`RES = ...`、读哪些 md） | `09_gen_disclosure_docx_v11.py` 读交付目录的 md + `patent/figures` → **来源关系成立** |
| 2 | 三处**逐字一致**：发明名称（claims.md / disclosure.md / docx）、权项条数与编号、核心口径数字 | 名称三处一致；权项 14 项逐项对应；口径 357/16/19/221,069/16,004/16,029/16,010 全在册 |
| 3 | **表格 ↔ 源 CSV 行数**比对 | ❌ 表1 列 7 个方法，图4 与 `三基线横评表.csv` 是 **9 个**（缺 基线②b、③b） |
| 4 | **复现脚本清单 ↔ 磁盘实际文件**逐名比对 | ❌ 三处：`07_age_shuffle.R`（磁盘为 `07_age_shuffle_permutation.R`）、成文脚本停在 v10、出图只列 1 个脚本却声称产出「附图 1–5」 |

### 复现链完整性补充检查（本次新增，很有用）

**对每一个「附图 N」，全目录 grep 它的输出文件名，零命中 = 没有生成脚本 = 违反端到端复现。**

```bash
grep -rln "fig_permutation_null\|fig_core_elements_357" "E:/专利" --include="*.py" --include="*.R" --include="*.sh"
# 本次只命中 3 个 docx 生成器（它们只是把 PNG 当输入嵌入），真正的出图脚本零命中
```

顺带查**源图时间戳 vs 口径切换日**：本次 `fig_permutation_null.png` 溯源到 `patent/figures/` 且时间戳 **09-09**（早于 09-11 口径切换），
属高危嫌疑；而同批 `fig_core_elements_357.png` 是 09-11 23:09（新口径）→ 正常。
（口径是否真的影响该图，最终以归档说明为准——本次 `结论_口径决策链.md` 明文写「该检验基于各物种自身矩阵，**与输入口径切换无关，数值不变**」。）

---

## 5. ⚠️ 两处 `figures/` 目录陷阱（本次踩到）

本项目有两个图目录，**docx 只从前者取图**：

```
E:/专利/patent/figures/            ← 交底书生成脚本 FIG 指向这里
E:/专利/交付_跨物种衰老可替代性专利/figures/   ← 交付目录（给用户看的）
```

- 两个出图脚本都写了**同一个 `save()` 同时写两处**：
  ```python
  OUT = [r"E:/专利/patent/figures", os.path.join(DELIV, "figures")]
  def save(fig, name):
      for d in OUT:
          fig.savefig(os.path.join(d, name), bbox_inches="tight", facecolor="white")
      plt.close(fig)
  ```
- **只写交付目录的后果**：交底书仍嵌入 `patent/figures` 里的**旧图**（本次差点把没修的图2 打进去）。
  新写/改写出图脚本时，**必须先确认 docx 读哪个目录**，再决定写哪。

---

## 6. 核验 docx 内嵌图 == 磁盘图（SHA256 逐字节）

一期/二期只比**字节数**；本次升级为**逐字节哈希**，结论更硬：

```python
import zipfile, hashlib, os
with zipfile.ZipFile(DOCX) as z:
    media = sorted(n for n in z.namelist() if n.startswith("word/media/"))
    for m, f in zip(media, order):          # order = 图注出现顺序的磁盘文件名
        assert hashlib.sha256(z.read(m)).hexdigest() == \
               hashlib.sha256(open(os.path.join(FIG, f), "rb").read()).hexdigest()
```

本次结果：5/5 SHA256 一致（302317 / 130808 / 244836 / 373161 / 286489 B）。
**media 顺序 = docx 里 add_picture 的调用顺序 = 图注顺序**，按 `sorted()` 排 `image1..imageN` 即可对齐。

---

## 7. 修完之后的自检清单（本次一遍过）

- [ ] 表行数：表1 = 表头 + **9** 方法；表3 = 表头 + **12** 步；表5 = 表头 + **14** 权项
- [ ] 陈旧字符串**零命中**：`四方法横评`、`07_age_shuffle.R`、`08_gen_disclosure_docx_v10.py`、`v10 交底书`、`12.3`、`95.5%`
- [ ] 图注数字 = 图内 OCR 数字（含新加的 `258.4`、`525,137`）
- [ ] 重跑 `check_figure_occlusion.py`，关键标签全命中
- [ ] 重出图后 **两个 figures 目录都要更新**，再 SHA256 比对 docx media
- [ ] `rail_review(post)` passed；`debate_analysis`（用户问"图对不对"= 结论性判断，走 L1 即可）
- [ ] 口径数字**一个都没动**（本次 357/16/19/16,029/16,010/221,069 全不变 —— 改图不该改数字）

---

## 8. 本次的实际产出（可作模板照搬）

| 新增/修改 | 路径（相对交付目录） |
|---|---|
| 出图脚本（图2/图3） | `scripts/10_make_figures_permutation_core.py` |
| 图2 数据源导出 | `scripts/11_export_permutation_stats.R` → `results/置换检验统计.csv` |
| 成文脚本 | `scripts/10_gen_disclosure_docx_v12.py`（由 v11 复制后 spot-patch） |
| 一键复现入口 | `scripts/run_all.sh`（阶段 C 拆为 C1 导出 / C2 图1·4·5 / C3 图2·3 / C4 成文） |
| 验收脚本 | `results/<sid>/scripts/validate_v12_deliverables.py`（本次 38 PASS / 0 FAIL） |
| 遮挡检测 | `results/<sid>/scripts/check_fig4_occlusion_v12.py`（已泛化进本 skill 的 `scripts/`） |

**版本升级做法**：`cp 09_gen_..._v11.py 10_gen_..._v12.py` 后**只 spot-patch 变更点**（docstring / 版本行 / 输出路径 / 表体行 / 图注），
不重写整个 31KB 生成器 —— 既省 token 又不会漏改无关段落。
