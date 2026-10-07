# 学位论文规范细则与出稿校验（实测标本：吉林大学硕士学位论文）

> `degree-thesis-writing` 的支持文件。含格式硬指标表、python-docx 实现要点、
> 出稿校验脚本、参考文献实际版本取证流程。

---

## 一、规范文件清单（一次读全）

| 文件 | 内容 | 读取方式 |
|---|---|---|
| 《研究生学位论文撰写及装帧规范》 | **主文件**，所有硬指标在此 | `.doc` → `antiword` |
| 封面及扉页格式 | 封面字段、单位代码、校徽位置 | `antiword` |
| 原创性声明 / 使用授权声明 | 直接照抄，签名处留空 | `antiword` |
| 参考文献著录规则（GB/T 7714-2015） | 常为**扫描版 PDF** | RapidOCR |
| 专业学位名称表 | 学位类别只能按此表填 | `antiword` |

> 扫描版 PDF 的 OCR 脚本可参考本次落地的 `scripts/ocr_gbt7714_2015.py` 模式。

## 二、硕士 vs 博士（最容易抄错）

| 项 | 硕士 | 博士 |
|---|---|---|
| 前置部分项数 | **7 项**，**没有**评阅意见书与答辩决议书 | 含评阅意见、答辩决议书 |
| 印刷 | **单、双面均可** | 必须双面 |
| 封面学位类别 | 学术学位填「××学硕士」；专业学位按标准名称表 | 同理填博士 |

**前置 7 项**：封面 / 两个声明 / 序或前言（可）/ 摘要与关键词 / 目次 /
插图附表清单（可）/ 注释表（可）

## 三、格式硬指标（逐项都要落进代码）

| 环节 | 要求 |
|---|---|
| 正文字体 | 宋体；5号/小4/4号任选但**全文统一**；标题大正文一号 |
| 章/节/小节标题 | 章=黑体三号、节=黑体四号、小节=黑体小四 |
| 章节序号 | `第1章` / `1.1` / `1.1.1`，序号与标题间**空一个汉字**；终止层次不加点 |
| 摘要 | 硕士中文约 1000 字；英文摘要据中文翻译；关键词 3–8 个 |
| 目录 | 「目录」三号黑体居中；章四号宋体左0缩进、一级节缩1字、二级节缩2字，页码右对齐 |
| **页码** | 前置=罗马数字；主体+结尾=阿拉伯数字且**第1章重新起算**；封底无页码 |
| **页眉** | **仅主体**；楷体小5号居中、普通单划线；双面版双页为「吉林大学博士（或硕士）学位论文」 |
| **图/表题** | 图题在图**下方**、表题在表**上方**；均居中、黑体、字号同正文；**序号与题名空一格** |
| 公式 | 另起行居中，编号右端对齐，公式与编号用「…………」连接 |
| 引用 | GB/T 7714-2015，全文统一顺序编码制或著者-出版年制；**标注不得出现在标题处** |
| 表格跨页 | 表头须重复 |
| 装帧 | A4 左装订；上左 ≥25mm、下右 ≥20mm（实现常取 上2.7/下2.5/左3.0/右2.5 cm） |

## 四、生成脚本模式（`scripts/gen_thesis_docx.py`）

```python
PARTS = ["part1_front.md", "part2a_ch1.md", "part2b_ch2.md",
         "part3_ch3_ch4_ch5.md", "part4_refs_appendix.md"]
# 1) 合并 → 单一 MD 母本（禁止多版本产物并存）
# 2) python-docx 逐节构建
# 3) 页眉/页码逐节设置
```

**python-docx 实现要点**
- 页眉**逐节设置**：每章插 section break，逐节写 `section.header`，
  `header.is_linked_to_previous = False` 断开继承。
- 页码分节：前置罗马 / 主体阿拉伯，第1章处 **restart numbering**，封底不加页码。
- 页眉单划线用段落边框（`w:pBdr` 的 `w:bottom`），**不要**用表格充当。
- 中文字体要同时设 `font.name` 与 eastAsia：
  ```python
  from docx.oxml.ns import qn
  run.font.name = "宋体"
  run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
  ```

## 五、出稿校验：一个脚本跑完

```python
import re, os
from docx import Document

md_path  = "results/thesis/硕士学位论文.md"      # 合并母本
doc_path = "results/thesis/硕士学位论文.docx"
md  = open(md_path, encoding="utf-8").read()
doc = Document(doc_path)

dtxt = "\n".join(p.text for p in doc.paragraphs)
for t in doc.tables:                              # 表格内容不在 paragraphs 里！
    for r in t.rows:
        for c in r.cells:
            dtxt += "\n" + c.text

# ① 页眉逐节
for i, sec in enumerate(doc.sections):
    head = sec.header.paragraphs[0].text.strip()
    assert head, f"第{i}节页眉为空"                # 实测第一版就是这里空

# ② 引文-文献表双向核对
body    = md.split("# 参考文献")[0]
cited   = set(int(x) for x in re.findall(r"\[(\d{1,2})\]", body))
reflist = set(int(x) for x in re.findall(r"^\[(\d{1,2})\]", md, flags=re.M))
print("孤立文献:", sorted(reflist - cited))        # 表中有、正文无 → 补引或删
print("缺条目  :", sorted(cited  - reflist))       # 正文有、表中无 → 必须补

# ③ 纯文本子串校验（不要带 ** 标记，DOCX 会剥离 → 假阴性）
print("引用位置 :", "T2T-MFA8，2025，V1.1[46]" in dtxt)
```

**产物计数最后汇报**：文件大小 / 段落数 / 表格数 / 节数。

## 六、参考文献换成实际版本：三步取证

1. **回溯原始来源逐字取** —— 用户提供的一手材料（原论文参考文献表）最可靠
2. **Crossref 核验**
   ```bash
   curl -s "https://api.crossref.org/works/<DOI>" -H "User-Agent: MemOmics/1.0"
   # 核对 title / volume / issue / page / published-print / author
   ```
3. **同步补正文引用** + `save_reference(action="add", metadata={...})`

**实测例**：`[46]` 原为占位式 `Genome Reference Consortium / CNGB. …(2025, V1.1)[DB/OL].`
→ 从用户给的原始论文参考文献第 92 条逐字取，Crossref 核验通过后落为：
`ZHANG S, XU N, FU L, et al. Integrated analysis of the complete sequence of a macaque genome[J]. Nature, 2025, 640(8059): 714-721. DOI: 10.1038/s41586-025-08596-w.`
并在正文补上引用位置（该条此前是孤立文献）。

## 七、命令与路径的小坑

- **文件名含零宽空格**（U+200B）会让 glob/`find` 匹配失败。
  取真实文件名：`os.path.basename(p).replace("\u200b","")` 后再判断。
- **`.doc` 抽取优先 `antiword`**；`python-docx` 只读 `.docx`，不能读旧版 `.doc`。
- 用户给的**原始论文 `.docx`** 常含大段英文 Materials & Methods，
  用 python-docx 抽 `doc.paragraphs` 后按关键词正则过滤（试剂/仪器/伦理号/数据库编号），
  一次性导出，避免反复读同一个文件。
