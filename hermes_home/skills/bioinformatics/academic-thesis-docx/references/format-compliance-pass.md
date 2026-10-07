# 按规范做一轮「排版合规巡检」（渲染层）

**触发**：用户说「按照学校规范调整」/「格式再对一遍」/「图题位置不对」/ 交付后学校模板审出格式问题。
**原则**：格式条款不是审美偏好，是**逐条可断言**的硬指标；每条都要有「规范原文 → 渲染实现 → 核验数字」三段证据。凭"看起来差不多"交付必然返工。

## 一、先取规范原文，别背规则

学校规范原件（.doc/.pdf）里，图表/引文条款通常集中在一节（吉大是 3.8 图、表、公式 + 3.11 引文标注）。**逐条摘录原文关键词**再动手：

```bash
grep -n "图题\|表题\|插图\|附表\|居中\|上角标\|续表" <规范抽取文本>.txt
```

吉大规范原文（可作同构学校的模板）：

| 条款 | 原文要点 | 渲染层动作 |
|---|---|---|
| 3.7 | 章节序号「序号与标题间要空一个汉字的位置」；不同层次用「.」相隔，**终止层次号码之后不加点** | 标题行写 `第1章　标题`、`1.1　标题`（全角空格） |
| 3.8 | **图号和图题排于图的下方**，以图所占位置为限居中排列；图号和图题名之间空一个汉字 | 母本图片行在前、图题行在后；图题段居中 |
| 3.8 | **表号和表题排于表的上方**，居中；转页时注明「续表」且表头重复排出 | 表题行在表格前；首行 tblHeader |
| 3.8 | 图题和表题均采用**黑体字，字号与正文相同** | 图/表题用 HEI、`Pt(12)`（正文小四） |
| 3.8 | 编号「章节号和序列号之间用'.'隔开。如图1.1、表2.2」 | `图 3.2` → `图3.2`（号与数字之间**不留空格**） |
| 3.8 | 公式另起一行居中；**编号右端对齐**，公式与编号之间用「…………」连接 | 公式行居中、编号靠右 |
| 3.11 | 顺序编码制：标示置于所引内容**最后一字的右上角**，用**小5号宋体上角标** | 正文 `[n]` → 上角标小5号 |

## 二、渲染层四个实现（python-docx）

### 1) 图题在图的下面

渲染脚本按 Markdown **行序**逐行输出，所以版式由母本行序决定：

```markdown
![图 3.1　图题](figures/x.png)      ← 图片行在前

**图3.1　图题**                      ← 图题行在后
图注：……
```

```python
# 生成器：图片段 keep_with_next，避免图与图题被分页拆开
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.add_run().add_picture(path, width=Cm(14.5))
p.paragraph_format.keep_with_next = True
```

### 2) 引文上角标（小5号宋体）

```python
CITE_RE = re.compile(r"\[\d+(?:[,–\-]\d+)*\]")     # 无空格 → 天然排除数值区间 [30, 500]

def _emit_text(p, text, cn, size, bold):
    if not text:
        return
    pos = 0
    for m in CITE_RE.finditer(text):
        if m.start() == 0:                          # 行首编号＝参考文献条目，不转
            continue
        if m.start() > pos:
            set_run(p.add_run(text[pos:m.start()]), cn, size, bold)
        r = p.add_run(m.group(0))
        r.font.name = cn; r.font.size = Pt(9); r.bold = bold
        r._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), cn)
        r.font.superscript = True
        pos = m.end()
    if pos < len(text):
        set_run(p.add_run(text[pos:]), cn, size, bold)
```

`add_rich()` 里把非加粗片段交给 `_emit_text()`（加粗片段单独 set_run），即可同时支持 `**加粗**` 与引文上角标。
**两个必须排除的误伤源**：行首编号（`[1] AUTHOR…`）、含空格的区间数值（`[30, 500]`）。

### 3) 表头跨页重复

```python
trPr = t.rows[0]._tr.get_or_add_trPr()
th = OxmlElement("w:tblHeader"); th.set(qn("w:val"), "true"); trPr.append(th)
```

### 4) 图表号去空格（母本批量）

```python
txt, n = re.subn(r"([图表])\s+(\d)", r"\1\2", txt)   # 实测全稿 112 处
```

## 三、幂等改稿脚本（必须幂等 + 自带断言）

见 `scripts/fix_fig_caption_order_and_numbering.py`。要点：

- **幂等**：只在「图题行后面 1–3 行内存在图片行」时才互换 → 已换过的不会再换，可反复跑。
- **无图件的图号不碰**：母本里「图 2.3（以文字描述）」这类没有 `![...]` 的图题，找不到图片行就原样保留（否则会被吞掉）。
- **自带断言**：`assert total_swapped == <预期张数>`——数目不符立刻报错，避免"静默少移两处"。
- 改完**必须重跑渲染脚本**；只改母本不重渲染 = 用户打开的还是旧版。

## 四、断言式核验（改完必跑）

```python
import re
from docx import Document
doc = Document(DOCX); paras = doc.paragraphs

cap_below = cap_above = 0
for i, p in enumerate(paras):
    if "w:drawing" in p._p.xml:                       # 图片段
        nxt = next((q.text.strip() for q in paras[i+1:i+4] if q.text.strip()), "")
        cap_below += bool(re.match(r"^图\d", nxt))    # 下一段是图题 → 图题在图下
    if re.match(r"^\*\*图\s*\d", p.text.strip()):
        cap_above += 1                                # 残留未处理的母本图题行

sup = sum(1 for p in paras for r in p.runs
          if r.font.superscript and re.fullmatch(r"\[\d+(?:[,–\-]\d+)*\]", r.text or ""))
sp_bad = re.findall(r"[图表]\s+\d", "\n".join(p.text for p in paras))

print(f"图题在图下 {cap_below}/{cap_below+cap_above} | 上角标引文 {sup} | 图表号带空格残留 {len(sp_bad)}")
assert cap_above == 0 and len(sp_bad) == 0 and cap_below >= N_FIG and sup > 0
```

实测通过样例（吉大硕士论文，9 张图件 / 42 表 / 12 节）：
`图题位于图下方 10/10 处 | 残留图题行 0 | 上角标引文 97 个 | 图表号带空格残留 0`。

## 五、环境提示

- 生成脚本用**装了 python-docx 的解释器**跑（常是系统 Python / 共享 site-packages），不是分析内核。先 `python -c "import docx"` 确认；需要共享库时 `export PYTHONPATH=<共享 site-packages>`。
- 一次把「改母本 → 重渲染 → 核验」串成一条命令跑完，减少往返：

```bash
cd <scripts> && PY=<python.exe> && export PYTHONPATH=<site-packages> \
  && "$PY" apply_xxx.py && "$PY" gen_thesis_docx.py && "$PY" verify_xxx.py
```

## 六、别忘了的连带项（本轮实测清单）

- **图件 ↔ 图号一一对应**：10 个图号只有 9 张 PNG → 必有一图两号（详见 `cn-degree-thesis-writing` 的图号重复条）。删重复图号后**后续图号顺次重编**，并同步目录 / 插图清单 / 正文交叉引用 / 图注内互引。
- **插图附表清单**：有图号的图必须进清单；纯文字（无图件）的"图"要么去号、要么补真图。
- **清单页码是静态数字**：正文一改就偏 → 交付时注明"页码以 Word 实排为准"，定稿同轮重排。
