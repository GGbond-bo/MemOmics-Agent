# xlsx 基因集宽表格式：追加/编辑铁律与修复配方（2026-08-13 实测）

## 背景

用户手工维护的基因集表（如 `E:\骨骼肌锻炼\pathway_score.xlsx`，Supplementary Table 3）
格式是**宽表**：

```
Row1: 标题 "Supplementary Table 3. Gene signatures."
Row2: Class | Signature | Annoation | Genes
Row3: Muscle | Stress index | List of core dissociation... | ACTB | ADAMTS1 | ADAMTS9 | ...
```

- 第 4 列起**每个基因占一列**（横向展开），不是 TAB 分隔挤一格。
- Class 列只有部分行有值（合并单元格视觉），读取时留空即可。

## 教训链（两次被用户抓住）

1. **第一次错**：Agent 用 `write.xlsx` 把 8 个新基因集写成
   `ABCB6\tADORA2B\tAGL...`（TAB 分隔单格）→ 用户"你新加的，一看就有问题"。
2. **第二次错**：Agent 改写宽表，但用 **openxlsx** 重写原文件 →
   生成 zip 引用 `xl/drawings/drawing1.xml` 但文件缺失 → openpyxl 读它
   `KeyError: There is no item named 'xl/drawings/drawing1.xml'`，execute_r 读 dims 1x1。
   用户"你都不调查吗？"。

## 根因

- openxlsx（R）写入 xlsx 时会带上损坏的 drawing 引用（对已有带绘图/打印设置的工作簿尤其如此）。
- 用户原始文件本身也可能带 `xl/worksheets/_rels/sheet1.xml.rels` + printerSettings
  （Excel 保存痕迹），openpyxl 读入会在 find_images 阶段崩。

## 正确方案（实测通过）

### 读取（原文件 openpyxl 可能崩 → zipfile 直接解析）

```python
import zipfile, re
z = zipfile.ZipFile(r"E:\骨骼肌锻炼\pathway_score.xlsx")
ss = z.read('xl/sharedStrings.xml').decode('utf-8', errors='replace')
strings = re.findall(r'<t[^>]*>([^<]*)</t>', ss)   # sharedStrings 表
sheet = z.read('xl/worksheets/sheet1.xml').decode('utf-8', errors='replace')
cells = re.findall(r'<c r="([A-Z]+)(\d+)"(?:[^>]*?t="(\w+)")?[^>]*?(?:>.*?<v>(.*?)</v>)?', sheet)
# 按行列组织，t="s" 的 v 是 sharedStrings 索引
```

按行提取：A=Class, B=Signature, C=Annoation, D 起 = 基因（直到空列停）。

### 追加（openpyxl 从零重建，绝不 openxlsx 重写用户文件）

```python
from openpyxl import Workbook
wb = Workbook(); ws = wb.active; ws.title = "Supplementary Table 3"
ws.cell(1,1,"Supplementary Table 3. Gene signatures.")
for i,h in enumerate(["Class","Signature","Annoation","Genes"],1): ws.cell(2,i,h)
r = 3
for s in all_sets:                       # original + new
    ws.cell(r,1, s.get('class',''))
    ws.cell(r,2, s['signature'])
    ws.cell(r,3, s.get('annotation',''))
    for g_idx,g in enumerate(s['genes']): ws.cell(r, 4+g_idx, g)
    r += 1
wb.save(out_path)                        # 新文件，原文件先备份
```

关键点：新建 Workbook（干净 9-entry zip，无损坏 drawing 引用）→ 宽表写入 → 保存。
**不要** `load_workbook(原文件)` 再 save（会把损坏结构带过去）。

### 验证（写入后必须重读）

- `load_workbook(out)` 能读 → 结构健康
- 检查行数（表头 + 22 基因集 = 24 行）、列数（最大基因集 200 + 4 = 204 列，实际 203）
- 每行基因数 = 预期数（Stress 23 / Type I 6 / Glycolysis 200 ...）
- 原有行一字未动（对比备份）

## 遗留事项

- 原文件被 Excel 占用时 `Permission denied` → 先写新文件 `pathway_score_CLEAN.xlsx`，
  让用户关 Excel 后替换（或自己替换），不要反复重试覆盖。
- 备份文件命名：`pathway_score_backup_<timestamp>.xlsx` 放同目录。
