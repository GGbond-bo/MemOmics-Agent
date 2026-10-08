---
name: metascape-gene-list-prep
version: 1.0
description: >
  从 DEG/FindMarkers 结果表构建 Metascape 输入基因列表。按亚群分列、按 avg_log2FC（或 coef）降序取 top-N，
  输出一列一个亚群的 CSV/TXT（亚群名为列头，基因竖排）。支持上/下调分列（up_/down_ + 亚群）、
  多比较组工作簿一表一组、多表 cbind 合并（如 MF+SMF 合并）。触发词：
  metascape / 基因列表 / top100 / DEG转Metascape / 按亚群取基因 / 合并Metascape表 /
  分出五个比较组的表格 / 各亚群上下调各100个基因。
category: user-skill
source: user-requested
tags: [metascape, deg, gene-list, marker, csv-formatting]
---

# Metascape 基因列表构建

## 使用场景

用户有 FindMarkers / DEG 结果 CSV（含 `cluster`、`gene`、`avg_log2FC` 列），需要构建 Metascape 导入格式的基因列表：
- 每列 = 一个亚群
- 列头 = 亚群名
- 下方 = 该亚群按 `avg_log2FC` 降序排列的 top-N 基因（默认 100）
- 不足 top-N 的亚群全取

## 三种输入形态（先认形态，再动手）

| 形态 | 判定特征 | 分列方式 | 排序键 |
|------|----------|----------|--------|
| 单表 FindMarkers CSV | 有 `cluster` + `gene` + `avg_log2FC` | 每列 = 一个亚群 | `avg_log2FC` 降序 |
| 单组上/下调表 | 有 `celltype` + `regulation`(Up/Down) + `coef` | 每列 = 亚群 × 方向，列名 `up_`/`down_` + 亚群 | `|coef|` 降序（并列按 fdr 升序） |
| 多比较组工作簿（一文件 N sheet） | 一个 xlsx 多个 sheet，各有 `comparison` 列 | 每组出一张表，表内同上 | 同上 |

## 核心流程

1. 读取 DEG CSV → 清洗 gene 列（去制表符/空白）
2. 按 cluster 分组 → 每组按 avg_log2FC 降序排序 → 取 head(top_n)
3. 构建 CSV：每列 = [亚群名, gene1, gene2, ...geneN]
4. 验证：表头行 = 亚群名，第 2 行起 = 基因（无重复表头）
5. 写盘后**读回磁盘文件再核一遍**（见「验证清单」第 6-7 项）

## ⚠️ 关键陷阱：pandas to_csv 表头重复

**根因**：`pd.Series(name=cl)` → `pd.concat(axis=1)` → `to_csv(header=False)` 时，Series 的 `name` 属性会**同时**写入列头和第一个数据行，导致 CSV 第 2 行重复亚群名。

**错误模式**（用户会看到"表头重复了"）：
```
cluster1,cluster2    ← 第1行: 表头 ✓
cluster1,cluster2    ← 第2行: 重复的表头 ✗（应为基因数据）
gene1,gene3          ← 第3行: 基因数据
```

**正确写法**（手动 CSV writer，绕过 pandas）：
```python
import csv

# columns = [ [cluster_name, gene1, gene2, ...], [...], ... ]
with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    for row_idx in range(len(columns[0])):  # 0=header, 1..N=genes
        w.writerow([col[row_idx] for col in columns])
```

**备选修复**（仍用 pandas，但确认 name=None）：
```python
metascape_df = pd.concat(records, axis=1)
# 强制列名 = 亚群名列表，不含 Series.name 残留
metascape_df.columns = clusters
metascape_df.to_csv(OUT, index=False, encoding="utf-8-sig")
# 验证: assert 第2行全是基因名，不含亚群名
```

## ⛔ 陷阱 A：用户粘贴的「示例表」可能是格式示意、内容不实 —— 必须先反查再用

用户常贴一张样板并说"做成这样的表格"。**它 ≠ 口径规格**：可能来自早期 AI 会话、手工拼的。落地前用真实文件做三步反查：

1. **列位置对齐**：样板首行是列名（`up_X` / `down_X`），数据行按列切片。注意粘贴会挤歪字段（本次某列第 2 行出现单字符 `c` → 该样板已判定为手拼）。
2. **穷举候选规则，逐位比对**：至少比这三条 —— A = 按效应量降序（`|coef|` / `avg_log2FC`）、B = **文件自身行序**（导出表常天然按 fdr 升序排）、C = `fdr==0` 过滤后再排序。**"逐位一致个数"才是证据**（本次 7 列样板：5 列与 B 规则 13/13 一致、2 列 0/13）。
3. **存在性检查**：拿样板里的基因去 `全部 sheet × 亚群 × 方向` 里找。**找不到 = 内容不实**（本次 2 列的基因在 5 个 sheet 里完全不存在）。

**结论口径**：以**用户文字写明的规则**为准（本次原话"按照|coef|最高往下排，选变化最大的100个基因"），样板只用来确定**版式**（列名格式、up/down 成对、列序）。把判定过程和证据写进回复——用户认这个。

## ⛔ 陷阱 B：候选口径先用数量级否决，再决定要不要弹窗问用户

本次一个看似合理的候选（"只保留 fdr 精确为 0 的基因"）会**掏空表格**：99 列中位数 0 个基因，`up_RSS` 有 2157 个候选却 0 个 fdr==0。
**先量化**（每列候选数 / fdr==0 数 / 两口径差异基因数）→ 不可行就直接否决并说明理由，**不要拿一个必然失败的选项去问用户**（浪费一轮，还显得没做功课）。

## 多比较组工作簿 → 每组一张表（2026-09-30 实战）

输入 = 一个 xlsx + N 个 sheet（每 sheet 一个比较组），列如 `gene / celltype / regulation / coef / se / z / p / fdr / direction / comparison / …`。
输出 = N 个同构表，**每个文件内：每列 = 一个亚群的一个方向**：

- 列名 `up_<celltype>` / `down_<celltype>`；列序 = 亚群**字母序**，每亚群 up 在前 down 在后
- 列内按 `|coef|` 降序（并列按 fdr 升序）取 top-N（默认 100），不足全取；组内先去重（保序）
- **空列（该亚群该方向无显著基因）不出这一列** —— 只有表头的列会让 Metascape 报噪声/报错
- 同时出两份：`Metascape_<组>_top100.txt`（tab、utf-8-sig，直接上传）+ 同名 `.xlsx`（用户要打开肉眼检查）
- 附带 `Metascape_列基因数汇总.csv`（每列取了几个 / 是否取满 / 该列 |coef| 范围）+ `_自检报告.csv`
- 交付回复必须给**每组列数与基因数范围表**，并主动说明"某组基因少是该对比本身显著基因少，不是漏取"

脚本：`scripts/build_metascape_multi_group.py`（参数化，改顶部常量即可复用）
本次细节（反查证据、分列数字）：`references/multi-group-workbook-and-example-reverse-check.md`

## ⚠️ 假基因符号：只处理「确证是残渣」的，别一刀切短符号

上游注释偶有解析残渣符号：本次 `Aging/up_OTUD1+(I)` 里有个单字符 **`c`**（全表仅 1 行、|coef|=0.837，混进第 2 名）。
但**双字符符号基本都是真基因**（MB 肌红蛋白 / CS / GK / FH / PC / AR / KY —— 全部保留）。
规则：长度 ≤2 的符号**逐个查**（行数 / 出现在哪些亚群 / |coef|），只对确证残渣的**报告并请示用户**，**不静默删改用户数据**。

## 验证清单

生成后必须检查：
1. [ ] 第 1 行 = 亚群名（列头）
2. [ ] 第 2 行起 = 基因名（不含亚群名）
3. [ ] 各列非空基因数 = min(top_n, 该亚群原始基因数)
4. [ ] 同亚群内无重复基因
5. [ ] 编码 utf-8-sig（Excel 直接打开不乱码）
6. [ ] **读回磁盘文件再核**（不信内存对象）：列数 / 最长列 / 表头是否 `up_`/`down_` 开头 / 空列 = 0 / 列内重复 = 0 / 各列基因数与预期吻合
7. [ ] 多组交付时核对总列数 = 各组列数之和（本次 20×4 + 19 = 99），并给用户"组 × 列数 × 基因数范围"表

## 合并多个 Metascape 表格

用户常有多张 Metascape CSV（如 MF + SMF 两套亚群），需要合并成一张大表再丢 Metascape。

### ⛔ 关键陷阱：cbind vs rbind（2026-08-22 用户纠正）

Metascape 表格合并 = **cbind（横向合并）**，不是 rbind（纵向拼接）！

- **cbind（正确）**：`pd.concat([df1, df2], axis=1)` — 列数相加，行数不变
- **rbind（错误）**：`pd.concat([df1, df2], axis=0)` — 行数相加，列数不变

用户原话纠正："用cbind不就行了吗？你现在SMF的基因都跑102行以下了" — 用 rbind 会导致后表的基因从第 N+1 行开始填入，前面全是空值。

**何时用什么**：
- 合并两张 Metascape 表（如 MF 10列 + SMF 7列）→ **cbind**（横向合并，17列）
- Metascape 只需要基因列表，不需要空行填充

### cbind 合并代码（正确做法）

```python
import pandas as pd

df_mf = pd.read_csv(mf_path, encoding="utf-8-sig")    # 100行 × 10列
df_smf = pd.read_csv(smf_path, encoding="utf-8-sig")  # 100行 × 7列

# cbind: 横向合并，列数相加，行数不变
merged = pd.concat([df_mf, df_smf], axis=1)  # 100行 × 17列
merged.to_csv(out_path, index=False, encoding="utf-8-sig")
```

### rbind 合并代码（仅限同结构表的纵向堆叠）

```python
# 仅当两个表列名完全相同、需要上下叠放时才用 rbind
merged = pd.concat([df1, df2], ignore_index=True)  # axis=0 纵向
```

**验证**（cbind 后）：
- 行数 = 各表行数之和（各表 top-N 相同的情况下）
- 列数 = 各表列数之和
- 每列非空基因数 = min(top_n, 该亚群原始基因数)（无空行）

## Metascape 格式要求

Metascape 导入格式：
- 第 1 行 = 列名（自定义，如亚群名）
- 第 2 行起 = 基因 symbol（每行一个基因）
- 不需要 p-value / log2FC 列（Metascape 只需基因列表）
- 列数不限，每列独立分析

## 脚本模板

- `scripts/metascape_top100.py` — 单表构建：输入校验 + 手动 CSV writer + 验证输出
- `scripts/merge_metascape_cbind.py` — 多表 cbind 合并：横向拼接 + 逐列验证非空基因数
- `scripts/build_metascape_multi_group.py` — 多比较组工作簿 → 每组一张表（`up_`/`down_` + 亚群分列、`|coef|` 降序 top100、空列跳过、txt+xlsx 双出、内置"样板反查"检查）

## 参考

- Metascape 官网: https://metascape.org
- `references/multi-group-workbook-and-example-reverse-check.md` — 多组工作簿实战数字 +「用户样板反查」三步法与证据
- 用户偏好（按场景分）：**分析过程中的临时脚本直接贴对话**（不写文件、不封装、多解释会被批）；**交付物**（用户要去检查的表/图）必须**落盘到他指定的目录**，并回报文件名 + 字节数 + 列结构。

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| human | skeletal_muscle | exercise+aging | 2026-09-30 | 23_build_metascape_5groups.py | - | - |  |
