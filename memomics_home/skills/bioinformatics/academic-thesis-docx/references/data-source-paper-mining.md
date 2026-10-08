# 从「数据来源论文」抽取实验细节（学位论文材料与方法用）

适用：素材包里的数据来自某篇已发表论文（尤其**用户是共同作者**），论文的材料与方法章节必须交代该数据的完整实验细节，且必须**逐字转录、不推断**。

## 一、为什么必须做

学位论文的数据可用性与可复现性审查会追问：这份数据是谁做的、伦理批件号是多少、用了什么试剂和仪器、怎么处理的。素材包（如专利交底书）通常**只有结果没有湿实验细节**——细节只能在来源论文里挖。用户原话："组织是怎么处理保存的，数据是怎么处理的，用的哪些仪器，哪家公司，哪些试剂，你都要拿出来……保证数据真实清晰，不捏造。"

## 二、抽取清单（逐项必须落到论文里）

| 类别 | 要抽到的具体项 |
|---|---|
| 伦理与来源 | 机构名称 + **批件号**（可能有两个：动物设施 IACUC + 数据方 IRB）、遵循的指南（NIH Guide / ARRIVE）、动物原产地与品系、设施认证（如 AAALAC） |
| 饲养 | 饲料品牌与货号、投喂频次、饮水、健康监测项（病原检测清单与结果） |
| 采集与保存 | 麻醉剂（名称 + 剂量 + 给药途径 + **厂家**）、安乐死试剂（+ 厂家货号）、灌注液、解剖时间窗、组织分块大小、冻存方式（液氮速冻/液氮保存） |
| 细胞核提取 | 匀浆器（品牌 + **货号**）、研磨次数与杵型、缓冲液**完整配方**、RNase 抑制剂（品牌 + 货号）、蛋白酶抑制剂（品牌 + 货号）、筛网孔径、离心转速/时间/温度、密度梯度试剂（品牌 + 货号）、终悬液 |
| 建库 | 试剂盒全名 + 厂家 + **货号**、平台名、浓度测定试剂盒（厂家 + 货号） |
| 测序 | 仪器型号、测序地点、**read 1 / read 2 读长** |
| 数据处理 | 比对软件 + 参考基因组版本、QC 阈值（如 TSS 富集 / 片段数）、双细胞过滤参数、降维方法、聚类分辨率、下游软件与版本 |
| 可获取性 | 归档库名 + **accession**、处理后数据的数据库 URL |

## 三、抽取脚本（Windows / 中文文件名）

### 1. 文件名可能带零宽空格

中文文件名常夹 U+200B，`ls` 看得到但 `bash`/`open()` 打不开。

```python
import os
d = r"D:\硕士毕业论文"
for fn in os.listdir(d):
    print(repr(fn), os.path.getsize(os.path.join(d, fn)))
# '猴脑\u200b.docx' 482848   ← 零宽空格在这里
```

### 2. 抽取正文（python-docx）

`read_file` 可能对该 .docx 返回 `Cannot read binary file`；python-docx 能正常读。
python-docx 通常装在**系统 Python**、分析内核里没有 → 用 `subprocess` 调系统 Python，脚本落盘再跑（不要把长脚本塞进一行 `-c`）。

```python
import subprocess
PY = r"C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe"
open("_dump.py", "w", encoding="utf-8").write(r'''
import os
from docx import Document
p = os.path.join(r"D:\硕士毕业论文", "\u7334\u8111\u200b.docx")   # 用 \u 转义避开不可见字符
paras = [x.text.strip() for x in Document(p).paragraphs]          # 保留原始索引！
WANT = ["Ethical statement", "Dissection and collection of macaque brain tissue",
        "Tissue processing and nucleus isolation", "snATAC-seq library preparation and sequencing",
        "snATAC-seq preprocessing", "Data and code availability"]
def find(h):
    for i, t in enumerate(paras):
        if t.startswith(h): return i
    return -1
for h in WANT:
    i = find(h)
    if i < 0:
        print(f"!!!! NOT FOUND: {h}\n"); continue
    print(f"########## [{i}] {h} ##########")
    for j in range(i+1, min(i+6, len(paras))):
        if paras[j] and any(paras[j].startswith(w) and paras[j] != h for w in WANT): break
        if paras[j]: print(paras[j], "\n")
''')
r = subprocess.run([PY, "_dump.py"], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print(r.stdout[:12000])
```

## 四、两个实测翻车点

1. 🔴 **不要先过滤空段再编号。** 先 `[t for t in paras if t]` 会改变索引，按错位索引去读会读到**完全不同的章节**（实测：以为在读 METHODS，实际读的是 DISCUSSION，且开头几句很像，肉眼不易发现）。**一律保留原始索引，用标题字符串定位。**
2. **打印时不要截断。** 第一次抽取若写成 `t[:200]`，关键信息（伦理批号、货号、读长）正好落在 200 字之后 → 必须重新抽一遍。**抽方法段时直接打全文。**
3. **先确认段落结构再抽**：`len(doc.paragraphs)` / `len(doc.tables)`；方法细节可能全在 `doc.tables` 里（本次为 0 表，全在段落）。

## 五、写进论文时的三条纪律

1. **转录而非转述**：货号、批件号、读长照抄，不做同义改写。
2. **队列差异留钩子**：来源论文队列规模（如 23 只动物）与本文实际用量（如 20 例样本）不一致且论文未写明原因时 → 正文写"⚠️ 须由作者核实"，并指出核对依据（原论文样本—脑区对应表），**绝不编造"质控未通过"之类的原因**。
3. **引用要对上**：抽取所得细节必须能指回来源论文的具体章节，参考文献里给出该论文的 PMID/DOI；数据可获取性另列 accession 与数据库 URL。
