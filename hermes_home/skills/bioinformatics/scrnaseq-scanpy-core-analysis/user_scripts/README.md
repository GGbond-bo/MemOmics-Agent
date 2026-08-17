# User Scripts — Custom Analysis Overlays

> 放你**自己的分析脚本**（非可视化）。这些脚本在 skill 默认 Pipeline 之后执行，
> 作为分析链的最后一环，不会被 skill 更新覆盖。

## 工作原理

1. **你写好分析逻辑放这里**
2. **运行时** — `rail_review(pre)` 检测到 `.R/.py` 文件 → 提示 agent 加载
3. **执行顺序** — Skill 默认 Pipeline → debate_analysis → **你的 user_scripts/**（链式执行）
4. **结果保存** — 输出写入 `results/<analysis>/04_custom/`
5. **自动沉淀** — 成功后 `skill_evolution(action="record_run")` 记录
6. **覆盖保护** — `skills_sync.py` 的哈希追踪保护此目录下的用户文件不被更新覆盖

## 适用场景

- 你有自己独特的统计分析逻辑（skill 默认没有的）
- 你想在标准分析后追加额外的检验
- 你想用自己的参数/阈值/算法替换某一步
- 跨模块的整合分析（如把 QC 结果和 DEG 结果联合分析）

## 命名约定

```
user_scripts/
├── custom_gsea.R           # 自定义 GSEA（替代默认 fgsea）
├── custom_batch_correction.R  # 自定义批次校正
├── my_enrichment_test.py   # 自定义富集检验
└── README.md               # 本文件
```

## 铁律要求（必须遵守）

每个脚本文件头：

```r
#!/usr/bin/env Rscript
# ============================================================
# MemOmics: rail_review(pre) → debate_analysis → rail_review(post)
# User Script: custom_gsea.R
# Skill: scrna-seurat-core
# Last modified: 2024-07-08
# ============================================================
```

## what-about.md 机制

Agent 发现 user_scripts/ 非空时，分析计划添加：

```
[USER_SCRIPTS] 检测到 user_scripts/ 有 N 个自定义分析脚本:
  - custom_gsea.R
  - custom_batch_correction.R
是否在默认 Pipeline 之后执行这些脚本？[Y/选择特定/N跳过]
```
