# matplotlib 画布与字体陷阱（导出段自检）

> 来源：跨物种衰老可替代性专利 v10 附图（memomics-7839e23a，2026-09-12）。
> 三处都是「图生成了、没报错、但交付件是坏的」——**静默失败**，必须靠自检抓。

---

## 1. 🔴 超出 xlim 的柱/标注 → `bbox_inches='tight'` 把画布撑爆

### 症状
`figsize=(13.5, 5.4)` @ dpi=300 应为 ~4050×1620 px，实际输出 **8416×1641 px**（28 英寸宽），且部分数值标签渲染到坐标轴外。

### 根因
坐标轴上限设 `ax.set_xlim(0, 125)`，但数据里存在超过上限的值（本例：两个基线方法的召回率是 392.8% 和 544.0%）。matplotlib **不裁剪**超出范围的柱和 `ax.text`——它照画在轴外；`bbox_inches='tight'` 再为容纳这些越界元素**扩大画布**。

### 自检（必做）
```python
from PIL import Image
im = Image.open(path)
expected = (figsize[0]*dpi, figsize[1]*dpi)   # 例：(4050, 1620)
assert abs(im.size[0]-expected[0]) < 0.15*expected[0], f"画布被撑爆: {im.size} vs {expected}"
```
**宽度/高度任一超过 `figsize × dpi` 的 15% ⇒ 有元素越界**，回去查数据范围。

### 修法（选一）
- **不要在图上画不可比的量**（本例首选：把超范围的方法从该面板剔除，并标注「精度仅 X% → 不可比」）
- 裁剪：给柱设 `clip_on=True`（但标注仍会越界）
- 显式给标注留边：`ax.set_xlim(0, max_val*1.15)`

> 关联规则：比值类指标（召回/命中率/占比）的分子集合可能大于分母池 ⇒ 值 >100%。**跨方法比较前先做可比性判定**（本例规则：`precision ≥ 0.90` 才纳入召回比较）。

---

## 2. 中文字体缺下标字形 → 静默变方框

### 症状
```
UserWarning: Glyph 8321 (\N{SUBSCRIPT ONE}) missing from font(s) Microsoft YaHei.
UserWarning: Glyph 8322 (\N{SUBSCRIPT TWO}) missing from font(s) Microsoft YaHei.
```
`Z₁`、`Z₂` 会渲染成 □，但**脚本正常退出、图正常保存**——不报错。

### 判据
`Microsoft YaHei` / `SimHei` / `SimSun` **不含 U+2081–U+2089（下标数字）**。含的是 `ℝ`、`α` 等常用符号，下标/上标数字不在其中。
（对比：`①②③` U+2460– 这些**有**，可以放心用。）

### 修法
画布文本里**禁用 U+2080–U+2089**，改写：
- `Z₁` → `Z1` 或 `Z-human` / `Z_主体`
- 排版需要真下标时用 mathtext：`$Z_1$`（会走数学字体，不经中文字体）

### 自检
```python
import warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    make_figures()
    miss = [str(x.message) for x in w if "missing from font" in str(x.message)]
assert not miss, miss
```
**不要靠肉眼看**——方框在小字号缩略图里和正常字很像。

---

## 3. 出图后必须读图核验（不能只看「文件已保存」）

即使没有 warning，也要用 `vision_describe` 拿事实清单确认：
- OCR 是否读出**全部**预期数字（缺哪个数字 = 哪个标签没渲染出来）
- 有没有乱码/方框（OCR 置信度 <0.7 的词多半是渲染问题，不是 OCR 问题）
- ASCII 亮度图是否全白/全黑（空白图是致命缺陷）

**并报像素尺寸**（见 §1 自检），尺寸异常本身就是内容越界的信号。

---

## 4. 图与正文的耦合：换数字必须重出源图

图里的数字是**像素**，`grep` 和 python-docx 提段落/表格**都拿不到**。所以：
- 「正文旧数字零残留」**不能**当作图文一致的证据
- 换口径/删论据时，**必须重出对应源 PNG** 并把它从交付件里换掉（例：删掉循环论证的富集倍数 ⇒ 那张富集图必须换成新的论证图，不能只改文字）
- 探针：解包 `word/media/*`，把每张内嵌图**字节数**与候选源图目录比对——**字节数一模一样 = 该源图没重出 = 头号嫌疑**
