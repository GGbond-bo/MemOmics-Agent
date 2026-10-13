# 出版级 PDF 版式恢复配方（多栏期刊）

用于把出版社 PDF（Nature/Science/Cell 系双栏排版）还原成**正确的阅读顺序正文** + **干净的图表裁剪**。
在解读/精读任何期刊 PDF 之前先跑这里的内容，否则段落级配对会错位、图注会混进正文。

依赖：`pymupdf`（`import pymupdf`；`import fitz` 已废弃）。

---

## 0. 先探结构

```python
import pymupdf
doc = pymupdf.open(pdf_path)
print("pages:", doc.page_count, doc.metadata.get("title"))
for i, pg in enumerate(doc):
    t = pg.get_text(); imgs = pg.get_image_info()
    print(f"p{i+1}: chars={len(t):5d} images={len(imgs)}")
```

判断要点：
- 正文页 chars 通常 3k–10k；**扩展数据页往往 chars 极少（100–1000）但 images=1**（整页是一张大图）。
- 正文主体页与 Extended Data 页的字符数分布差异就是分界线，据此决定哪些页做正文重排、哪些页只做整图裁剪。

---

## 1. 双栏阅读顺序重建（核心步骤）

`get_text("blocks")` 的返回顺序是**内容流顺序**，双栏时左右栏交错 → 段落序列错乱。必须先分栏再排序。

```python
def body_blocks(pg, lx=200, y_footer=750):
    """取正文块：宽度落在单栏正文区间（约 200–275pt），排除页脚。"""
    out = []
    for b in pg.get_text("blocks"):
        x0, y0, x1, y1, txt = b[0], b[1], b[2], b[3], b[4]
        if not txt.strip() or y0 > y_footer:
            continue
        if 200 <= (x1 - x0) <= 275:      # 单栏正文宽 ≈ 255–260pt
            out.append((x0, y0, txt))
    return out

def reorder(pg, split_x=200):
    bs = body_blocks(pg)
    left  = sorted([b for b in bs if b[0] <  split_x], key=lambda z: z[1])
    right = sorted([b for b in bs if b[0] >= split_x], key=lambda z: z[1])
    return [t for _, _, t in left + right]   # 先读完整左栏，再读右栏
```

**关键参数**（A4/Letter 双栏期刊实测）：左栏 x0 ≈ **39.7**，右栏 x0 ≈ **306.1** → 分栏阈值取 200 即可。
不同刊/不同版式请先打印首页块坐标确认，**不要照抄**。

### 验收：语义连续性，而不是"排序规则对不对"

```python
blocks = [(p, clean(t)) for p in pages for t in reorder(doc[p-1])]
for i in range(len(blocks) - 1):
    print(f"{i}: ...{blocks[i][1][-40:]!r}  ||  {blocks[i+1][1][:40]!r}")
```

逐个看接缝：**上一个块的结尾是否自然接进下一个块的开头**。典型信号：
- 新闻式断词续接（`...we thus opted for independent synthesis and` || `separate optimization of the second reaction step...`）= 顺序正确。
- 出现 "It is important to note that..." 在另一栏又整段重复 / 句子从中间劈开 = **栏判错或图注混入**，回去修。

> 这一步不能省。双栏 PDF 的坑就在于"看起来有文本、跑得通、但顺序是错的"，静默产出错版对照。

---

## 2. 块分类：正文 / 图注 / 图内碎片

三类块宽度可能几乎一样，**宽度只能筛出正文，筛不出图注**，要靠前缀与内容形态：

| 类型 | 判别 |
|---|---|
| 正文 | 宽度 200–275pt，含成句散文 |
| **图注** | 以 `Fig. N \|`、`Extended Data Fig. N \|`、`Extended Data Table N \|` 开头 → **剔除出正文序列**（图注另作 `C...`/`F...` 块处理，保留双语对照） |
| 图内碎片 | 纯刻度数字串（`14 12 10 8 6 4 2 0`）、孤立化学符号（`S0 S0`、`S S`、`MeN`）、单字符项 → 剔除 |

图注块还有一个特征：**换页续排**。caption 前半在本页左栏，后半在同一页右栏顶部（或次页），两半要拼回同一条 caption。

---

## 3. Type3 / 子集字体乱码解码

出版社图内标签常排进 Type3 子集字体，文本层提取出**偏移字符码**，看着像乱码：

```
3ULQFLSDO FRPSRQHQW   →  Principal component
'RQRU %ULGJH $FFHSWRU →  Donor Bridge Acceptor
```

偏移量可暴力求解（Nature 语料实测 **+29**）：

```python
def decode(s, ks=range(-40, 41)):
    best = (0, s)
    for k in ks:
        cand = ''.join(chr(ord(c) + k) for c in s)
        score = sum(cand.lower().count(w) for w in ("the", "of", "and", "er", "in"))
        if score > best[0]:
            best = (score, cand)
    return best[1]
```

规则：
- 先跑一遍整体偏移（整段用同一个 k），成立就用定值。
- 还原不成功 → 在 `translation_notes.md` 里标注**"图内文字以渲染图为准，未做还原"**，不要猜、也不要把乱码原样写进交付物。
- 恢复正常：**乱码只出现在图内**，正文文本层不受影响；正文不需要解码。

---

## 4. 图表裁剪（由 caption 反推图区）

不要用内嵌 image 的 bbox 直接裁——矢量图会被拆成几十个碎片块。正确做法是**用 caption 位置反推图区矩形，整块渲染**。

```python
# 1) 找 caption 顶部 y
cap_y = min(b[1] for b in pg.get_text("blocks")
            if b[4].strip().startswith(("Fig. ", "Extended Data Fig")))

# 2) 图区 = 页顶 margin 到 caption 顶部；x 范围按图的跨栏宽度给
rect = pymupdf.Rect(x0, 44, x1, cap_y - 2)
pix = pg.get_pixmap(clip=rect, dpi=550, colorspace=pymupdf.csRGB)
pix.save(out_png)
```

取值经验：
- 页顶起点取 **y≈44**（上方只有页眉 "Article"/页码，无内容）。
- 单栏图 x 取左栏宽（`36–299`）；**跨双栏图 x 取 `36–566`**（右边界要盖住最右的轴标签，先查右栏最右块的 x1）。
- dpi **≥500**，否则图内小字在交付时不可读。
- Extended Data 页往往整页一张大图 → 直接按 image bbox 并留少量边距渲染即可。

### 裁剪后必须抽查

对渲染出的 PNG 跑 `vision_describe`，**断言 OCR 出来的只有图内标签、没有正文成句文字**：

- 期望看到：`Phase I`、`BO`、`Principal component 1`、`Back-up selection`、`~60% success rate` 之类
- 看到整句散文（"...we trained interpretable ML models..."）= **矩形错了**，把正文裁进来了，回去收紧 y/x

---

## 5. 交付前校验

```python
txt = open("paper.md", encoding="utf-8").read()
assert txt.count("**Original:**") == txt.count("**中文:**")     # 块对数量一致
import re, os
imgs = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', txt)
missing = [i for i in imgs if not os.path.exists(os.path.join(outdir, i))]
assert not missing, missing                                     # 图片链接全部存在
assert not re.search(r'\\\\(frac|sum|begin)', txt)               # 无裸 LaTeX
```

再写 `source_map.json`（块 ID / 页 / 类型 / 资产索引）与 `translation_notes.md`（分栏重排方法、乱码标注、不确定性），并把每个图表资产的路径登记进 source_map。

---

## 6. 写入策略

双语长文（`paper.md`，数十 KB 级）**分块 append**，单次全量写入易超长/超时：

```python
open(md, "w", encoding="utf-8").write(head)     # 头部 + 索引 + 摘要
open(md, "a", encoding="utf-8").write(part2)    # 引言 + 方法
open(md, "a", encoding="utf-8").write(part3)    # 结果
open(md, "a", encoding="utf-8").write(tail)     # 图表注 + 术语表 + 阅读提示
```

每块主题明确不同（头部/方法/结果/图表注），避免形态相似的分块被系统的循环检测误判为重复操作。