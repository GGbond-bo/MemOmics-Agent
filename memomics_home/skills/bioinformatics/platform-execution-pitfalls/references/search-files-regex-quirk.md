# search_files 内联正则标志静默 0 命中的坑（2026-09-25 实测）

## 现象（同一批文件，两种 pattern 结果矛盾）

```
search_files(pattern="(?i)\\bHSP|Hsp[0-9]|DNAJ|HSPB",
             file_glob="table[34]*.csv",
             path="results/<sid>/task4/results")
→ {"total_count": 0}

search_files(pattern="HSP",
             file_glob="table[34]*.csv",
             path="results/<sid>/task4/results")
→ {"total_count": 2}
   ├─ table3a_reversal_aging_up_to_down.csv:346  Up,HSPA9,...
   └─ table3a_reversal_aging_up_to_down.csv:347  Up,HSPD1,...
```

## 根因

`pattern` 底层走 ripgrep，但**内联标志 `(?i)` 与 `\b` 的组合在包装层不被完整传递**：
既不报错、也不警告，直接退化成 `total_count: 0`。

## 为什么危险

0 命中会被当成**事实结论**写进答复 ——「表里没有 HSP 基因」「没有这个家族」。
基因符号 / ID / 样本名 / 列名的检索里，这种假阴性比报错难发现得多，
而且会被当成"数据事实"引用到后续结论里。

## 规避（三条硬规则）

1. **基因符号、ID、前缀一律用纯大写字面量搜索**：`HSP`、`HSPA`、`MT-`、`ENSG`。
   **不要**加 `(?i)`；**不要**加 `\b`。
   （`HSP` 这种前缀子串搜索天然覆盖 HSPA / HSPB / HSPD / HSPE / HSPH 全部命名，
   不需要靠正则写全家族。）
2. **家族扩检用大写字面量 alternation**，而不是正则构造：
   `HSPB|HSPE|DNAJ|CRYAB|BAG3|HSP90`
3. **0 命中必须配"阳性对照"才可信**：先用一个已知必然命中的最小 pattern
   （宽泛大类如 `HSP`，或表头里的列名）在同一批文件上跑一次。
   - 阳性对照有命中 + 目标 pattern 0 命中 → 可以下"没有"的结论
   - 阳性对照也 0 命中 → 是**工具/路径/glob 问题**，不是数据没有，先修检索方式

## 推广

任何「查一下有没有 X」的检索都适用：**0 命中先怀疑检索方式，再下否定结论。**
同类风险：把 `file_glob` 写窄了（如 `table[34]*.csv` 漏掉 `table5*.csv`）也会造成
静默 0 命中 —— 结论前先确认 glob 覆盖面与阳性对照都过。

## 关联

- `platform-execution-pitfalls` 主表（execute_r / rail_review / skill_view 类坑）
- 基因列表成分审计流程（家族扫描 → UniProt 功能注释 → 方向解读 → 反例诚实列出 → 2 基因撑起的词条降级）：
  见 **`enrichment-conclusion-validation`** skill 的 `references/gene-list-composition-audit.md`，
  及其 SKILL.md 的**门禁 6b｜列表成分审计**
  （注：`functional-enrichment` 为人工维护 skill，agent 不可改写，相关实测教训沉淀在
  `enrichment-conclusion-validation` 这个结论把关层里）
- 该审计流程的步骤 1 就是本坑的正面用法：**0 命中先怀疑检索方式，再下否定结论**