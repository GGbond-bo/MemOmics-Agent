# hdWGCNA 结果验证清单（审稿人视角 C1-C5）— MF 骨骼肌实测

> 来源：memomics-2f229850 session，MF_subset_2000.rds（10 亚群 × 2000 cells）hdWGCNA 官方流程。
> 官方流程参数：MetacellsByGroups(k=25) + blockwiseModules(signed, bicor) → **power=10, R²=0.982, 11 模块**。
> 产物：results/memomics-2f229850/hdwgcna/figures/CNS/Fig_hdwgcna_CNS.{png,pdf,tiff} + figure_debate.md

## 背景：首次失败 ≠ 方法不可行

| 尝试 | 参数 | 结果 |
|------|------|------|
| 07-31 首次 | fraction 0.05 + top3000 HVG | 软阈值 R² max 0.72（不达标），全基因落单一 turquoise 模块 |
| 08-01 官方 | 全基因集（10176 基因）+ MetacellsByGroups | power=10, R²=0.982, 11 模块 ✅ |

**教训**：task_plan 里记录的"hdWGCNA 在 MF 不可行"是**过时负面结论**，被官方 workflow 重跑推翻。引用 task_plan 负面结论前必须查产出目录 verify_*.txt / 文件 mtime 是否晚于 task_plan。

## 审稿人必问 5 个验证点（结论发表前必须落实）

### C1 — metacell 级相关伪重复（最致命）
- CorrelateModules 在 metacell 级（n=6524）做相关 → p 值被夸大
- **必须个体级聚合复核**：module eigengene ~ trait + (1|individual) 混合模型，n=个体数（本例 24）
- judge 裁决 = MODIFY / confidence=high，要求弱化"运动可逆"表述直至个体级复核

### C2 — 模块富集纤维类型 marker → 组成混杂
- red 模块富集快肌 marker 8/9 → "运动可逆代谢程序"可能是纤维类型组成差异
- 下结论前校正细胞组成（协变量/残差），并在亚群内拆分验证响应方向

### C3 — 新模块 0 GO 注释
- purple 模块 T2D r=+0.249 但 0 GO 注释
- 可能是真新模块也可能是注释库不全 → 与已知 T2D 基因集独立重叠验证后才能宣称"新模块"

### C4 — hub 基因与 DEG 交叉验证
- 模块 hub 基因大多不在 DEG 里 → 结论未闭环
- 标准：hub 基因与 DEG 重叠率 >30% 才算闭环

### C5 — 模块效应是否细胞类型特异
- "red 可逆"需在亚群水平拆分（RSS vs Pure IIX 响应是否一致）

## 方法学要点
- MetacellsByGroups 用默认 k=25（勿用 20 以下的过小 metacell，会引入噪声）
- signed 网络比 unsigned 更适合单细胞（正负相关分离）
- marker→模块映射（如 red=快肌 8/9, brown=慢肌 10/10）是注释独立验证的强证据，汇报时列出
