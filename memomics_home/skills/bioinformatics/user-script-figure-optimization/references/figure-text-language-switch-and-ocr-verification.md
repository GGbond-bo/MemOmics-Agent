# 图内文字「中 → 英」定点切换 + 双层 OCR 验收

实测来源：2026-10-01，用户对已落盘图 `44_MEF2C_locus_from_GTF` 下指令
**「这个里面的文字变成英文」**（此为用户的全局偏好：展示类图内说明文字一律英文）。

基线脚本：`results/<sid>/task5/scripts/44_mef2c_locus_from_gtf.py`（matplotlib，base 无依赖）
基线图：`task5/figures/44_MEF2C_locus_from_GTF.{png,svg,pdf}`

---

## 1. 请求定性：这是「重绘类」的**子类**，不是重分析

| 项 | 判定 |
|---|---|
| 类别 | 重绘（只换语言）——复用已算好的统计量，**一行数据都不重算** |
| 改动点 | 可数（本次 6 处），其余版式**全部冻结** |
| 业务边界 | 只改**图内可见文字**；脚本注释 / `print()` 不动 |
| 脚本处置 | 用户没要求保留代次时**就地 patch 原脚本**（同一条交付链），有要求才另存新代次 |

> 与「重绘类请求：只改色 / 改语言」小节的关系：那节讲的是**颜色**重绘，
> 本节把**语言**重绘的边界、字体、版式副作用与验收补齐。

---

## 2. 6 处替换清单（本次的完整对照）

| # | 位置 | 改前 | 改后 |
|---|---|---|---|
| 1 | 轨道 1 标签（`draw_gene` 的 label，三行） | `MEF2C\nprotein_coding\n− 链` | `MEF2C\nprotein_coding\n(−) strand` |
| 2 | 轨道 2 标签 | `MEF2C-AS1\nlncRNA\n+ 链` | `MEF2C-AS1\nlncRNA\n(+) strand` |
| 3 | 重叠区 `ax.annotate` | `重叠 {bp} kb\n(head-to-head)` | `Overlap {bp} kb\n(head-to-head)` |
| 4 | `ax.set_xlabel` | `chr5 位置 (Mb, GRCh38)` | `chr5 position (Mb, GRCh38)` |
| 5 | `ax.set_title` | `GENCODE v32 (GRCh38) 中的 MEF2C 基因座 —— 直接解析自注释文件` | `MEF2C locus in GENCODE v32 (GRCh38) — parsed directly from the annotation file` |
| 6 | `fig.text` 脚注（拆两行） | `外显子块 = …（MEF2C {n} 个转录本 / MEF2C-AS1 {m} 个）；三角示转录方向；源文件 …（{N:,} 行）` | `Exon blocks = merged exon intervals across all transcripts of each gene (MEF2C: {n} / MEF2C-AS1: {m});\narrowheads = transcription direction; source file: … ({N:,} lines)` |

**顺带允许的两处（都要在汇报里点明，不能默默做）**：

1. 字体链 `['Microsoft YaHei','SimHei','DejaVu Sans']` → `['DejaVu Sans','Arial','Helvetica']`
   —— CJK 字体从链里摘掉；`DejaVu Sans` 放首位（matplotlib 自带，不依赖系统装 Arial）。
2. 脚注由 1 行拆成 2 行（英文更长），加 `linespacing=1.5`。

**⛔ 不允许（本次刻意没动，并已明说）**：脚本注释（`# 轨道1：MEF2C（负链…）`）与
`print(f"  → 重叠区间 …")` —— 中文留着，因为它们不进图片。

---

## 3. 双层 OCR 验收（关键：不能只做一层）

### 第 1 层：全图 OCR —— 验"中文残留 = 0"

```
vision_describe(image_path=<png>, question="图内所有文字是否均为英文？有无中文残留？")
```

实测返回 18 条文字，**零中文字符**，标题/轴名/标签/脚注全部英文。
但 —— ⚠️ **脚注第 1 行不在清单里**。

### 第 2 层：裁切 + 放大 + 二次 OCR —— 验"小字号文字真的渲染了"

小字号（本次 5.6 pt）长文本会被全图 OCR **静默漏读**。这不是渲染失败，
**但也不能不管** —— 万一真被 `bbox_inches` 裁掉了呢？必须复核：

```python
from PIL import Image
p = r'.../44_MEF2C_locus_from_GTF.png'
im = Image.open(p); W, H = im.size            # 1896 x 832
crop = im.crop((0, H - 140, W, H)).resize((W * 2, 280), Image.LANCZOS)   # 底部 140px，放大 2x
crop.save(r'.../_check_44_footnote.png')      # 再喂 vision_describe
```

**二次 OCR 结果**：读出
`Exon blocks = merged exon intervals across all transcripts of each gene (MEF2C: 56 transcripts / MEF2C-AS1: 15);`
⇒ 第 1 行确实在 —— 是**漏读**不是没画。

**ASCII 亮度图佐证**：vision 输出里的 ASCII 图在底部带出现**两条满宽文字行**（row 13–16 与 row 20–23）
—— 与"两行脚注都在"一致。这条佐证在 OCR 漏读时很有用。

> 🔑 **铁律：OCR 缺失 ≠ 渲染失败。** 断言"这行没画出来"之前必须裁切放大复核一次，
> 否则会去修一个不存在的 bug（本次差点重改一轮）。

工具：`scripts/ocr_crop_upscale.py`（裁区域 + 放大，输出直接可喂 `vision_describe`）。

---

## 4. 脚本层合规扫描

```bash
grep -n "链\|重叠\|位置\|中的 MEF2C\|外显子块 = \|三角示" task5/scripts/44_mef2c_locus_from_gtf.py
```

本次命中 6 行，**全部**是 `#` 注释行或 `print(` 行 ⇒ 合规（图内文字域已无中文）。
判据是**命中行的性质**，不是命中数量 —— 不要为了让 grep 变空而把注释也翻译掉。

---

## 5. 数据口径必须逐项对齐

换语言**不重算任何统计量**。重跑后对比上一版：

| 指标 | 上一版 | 英文版 |
|---|---|---|
| MEF2C | chr5:88,717,117–88,904,257 (−) protein_coding，56 tx / 36 外显子块 | **完全一致** |
| MEF2C-AS1 | chr5:88,833,328–89,466,398 (+) lncRNA，15 tx / 22 块 | **完全一致** |
| 重叠 | 20,930 bp | **完全一致** |

汇报句式：「**数值与上一版完全一致，只换了语言文字**」——用户会逐位核对数字。

---

## 6. 交付与归档

- 图重出三格式：`44_MEF2C_locus_from_GTF.png | .svg | .pdf`（102 KB / 96 KB / 35 KB，1896×832 px @300 dpi）
- **同步一份到会话主 `figures/`**（脚本写的是 `task5/figures/`；主输出目录也留一份便于查找）
- 临时裁剪图（`_check_*.png`）验收完 **`rm` 掉**，别留在 `log/` 里当产物
- `rail_review(post)` + `skill_evolution(record_run)`（`score=9`，`params_used` 记 figsize/dpi/font/%
  脚注 y 与 linespacing）

---

## 7. 检查表（下次直接照做）

- [ ] 只改图内可见文字，注释 / `print` 不动，并在汇报里明说
- [ ] 字体链换拉丁体、摘掉 CJK 字体；`axes.unicode_minus = False` 保留
- [ ] 英文变长的脚注/标题拆行 + `linespacing`；`fig.text` 的 y 按**第一行**给（默认 `va='baseline'`）
- [ ] 全图 OCR 断言中文字符 = 0
- [ ] 小字号文字**必须**裁切放大二次 OCR，才敢说"渲染正常"
- [ ] 重跑后数据口径逐项与上一版对齐，写明"数值未变"
- [ ] 三格式重出 + 主 `figures/` 同步 + 临时图清理