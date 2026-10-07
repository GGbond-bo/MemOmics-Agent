# xlsx 读不开时的兜底：把 xlsx 当 zip 手动解析

## 症状

| 读法 | 结果 |
|---|---|
| `openpyxl.load_workbook(p, data_only=True)` | `KeyError: "There is no item named 'xl/drawings/drawing1.xml' in the archive"`（文件内图片关系损坏 / 关系表与实际内容不一致） |
| `openpyxl.load_workbook(p, read_only=True)` | **不报错但静默返回空表**：`max_row=1 max_col=1` —— 比报错更危险，会让人以为"文件本来就是空的" |
| R `openxlsx::read.xlsx()` | 这类文件往往**能正常读**（本项目实测），可作为交叉验证的第二条路 |

判据：报错指向 `xl/drawings/...` 或 `xl/media/...` ⇒ **是图片/关系表损坏，数据本体的 sheet XML 大概率完好**，别放弃、别让用户重发文件。

## 兜底方案：xlsx = zip → 直接解 XML

xlsx 本质是 zip，`sharedStrings.xml` 存字符串池，`worksheets/sheetN.xml` 存单元格（`t="s"` 表示值是共享字符串索引）。
绕开 openpyxl 的图片检查即可读到全部数据。

**可直接运行的脚本**：本 skill 的 `scripts/read_xlsx_manual.py`

```
python read_xlsx_manual.py <文件路径> [sheet序号] [起始行] [行数]
```

核心逻辑（约 20 行，可内联进任何 persistent kernel 调用）：

```python
import zipfile
from xml.etree import ElementTree as ET
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'

def read_xlsx_manual(p):
    z = zipfile.ZipFile(p)
    ss = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall(NS + 'si'):
            ss.append(''.join(t.text or '' for t in si.iter(NS + 't')))
    out = {}
    for sh in [n for n in z.namelist() if n.startswith('xl/worksheets/sheet')]:
        rows = {}
        for row in ET.fromstring(z.read(sh)).iter(NS + 'row'):
            ri = int(row.get('r')); cells = {}
            for c in row.findall(NS + 'c'):
                col = ''.join(ch for ch in c.get('r') if ch.isalpha())
                t = c.get('t'); v = c.find(NS + 'v'); isel = c.find(NS + 'is')
                if t == 's' and v is not None:      val = ss[int(v.text)]
                elif t == 'inlineStr' and isel is not None:
                                                    val = ''.join(x.text or '' for x in isel.iter(NS + 't'))
                elif v is not None:                 val = v.text
                else:                               val = None
                cells[col] = val
            rows[ri] = cells
        out[sh] = rows
    return out
```

单元格类型三种都要处理，否则会读空：`t="s"`（共享字符串索引）/ `t="inlineStr"`（内联串）/ 无 `t`（数值原文）。
**行号可能不连续**（空行不写进 XML），所以拿到的是 dict 而非 list —— 遍历时用 `sorted(rows.keys())`。

## 列字母 → 序号

```python
def colidx(ref):                      # "A"->1, "B"->2, "AA"->27
    s = ''.join(ch for ch in ref if ch.isalpha()); n = 0
    for ch in s: n = n * 26 + ord(ch) - 64
    return n
```
按 `colidx` 排序单元格，才能保证基因列表顺序与表内一致（dict 顺序不可靠）。

## 同根因的兄弟现象

- **`read_only=True` 的假空表**：不报错、返回 1 行 —— 拿到"文件是空的"这类反常结论前，换手动解析再确认一次。
- **"数据只有 N 行"可能是假的**：`max_row` 可能远大于有效行号（本次 `pathway_score.xlsx` 报 max_row=126，实际数据只到第 24 行，25–126 为空行占位）。判断"有没有残留数据"要**逐个有数据的行号打印**，不能只看 `max_row`。
