# 五效应热图配色方向：面板标题 ≠ 计算方向（2026-08-14 实证）

## 触发场景

用户看着五效应热图（Fig1_five_effects_matrix 类：行=打分、列=效应轴、fill=效应量 d/eff）问
**"红色代表谁上升呢？"**。这是方向性提问，答案取决于**生成该图的代码**的符号约定，
不是面板标题、不是直觉、不是早期版本脚本。

## 核心坑：同名效应轴在 R 与 Python 脚本里方向相反

同一会话、同一数据、同一批效应轴（Aging/T2D/ExYoung/ExOld/ExT2D），两版脚本计算方向**相反**：

### R 版（早期探索，`aucell_cns_figures.R`）

```r
axes <- list(
  Aging     = c('O_Pre','Y_Pre', FALSE),   # g1=O_Pre, g2=Y_Pre
  ...
)
x1 <- ind[[s]][ind$type==g1]; x2 <- ind[[s]][ind$type==g2]
eff <- mean(x2) - mean(x1)                  # eff = mean(Y_Pre) - mean(O_Pre)
```

→ **eff 正值 = Y_Pre（年轻）打分更高**。Aging 轴红色=年轻高。

### Python 版（最终成图数据源，`effect5_d_table.csv`）

```python
eff_defs = {'Aging': ('O_Pre','Y_Pre'), ...}   # g1=O_Pre, g2=Y_Pre
def cohens_d(a, b):
    d = (a.mean() - b.mean()) / sp             # d = mean(O_Pre) - mean(Y_Pre)
a = agg.loc[(agg['annotation_L3']==sub) & (agg['type']==g1), s]
b = agg.loc[(agg['annotation_L3']==sub) & (agg['type']==g2), s]
```

→ **d 正值 = O_Pre（老年）打分更高**。Aging 轴红色=老年高。

**面板标题 `Aging (O_Pre − Y_Pre)` 两个脚本都适用，但红色含义完全相反。**
回答"红色代表谁上升"若拿错脚本（凭记忆/早期探索版），方向直接答反。

## 回答前必做核实流程

1. **锁定用户实际看到的图**：从产出物清单/图目录找最终交付版
   （如 `figures/Fig1_five_effects_matrix.png`），不是早期 `figA_effect_matrix` 之类。
2. **追溯生成代码**：`log/system_log.jsonl` 检索生成该图及其数据表
   （`effect5_d_table.csv` / `effect5_q_table.csv`）的 `execute_code` 调用，
   读出 `eff_defs`/`axes` 定义 + `cohens_d` 计算式。代码在 jsonl 的 `args.code` 字段。
3. **锚点验证符号**：选一个生物学方向确定的打分验证约定。
   - 本会话锚点：scoreIIa（快肌 IIa 已知随衰老下降）
   - 实测 `LRP1B+(I)|Aging d = -3.863` → 负值=蓝 → 蓝=年轻高 → 所以**正值(红)=老年高=衰老升高** ✅
   - 若锚点结果与预期矛盾 → 说明约定的正负方向判断有误，重新读计算式。
4. **输出速查表**（逐面板谁高 + 图例细节）：
   - Aging：红=O_Pre 高（打分随**衰老上升**），蓝=Y_Pre 高（随衰老下降）
   - T2D：红=OD_Pre 高（随**糖尿病上升**），蓝=O_Pre 高
   - ExYoung：红=Y_Post 高（随**运动上升**）
   - ExOld：红=O_Post 高（随**运动上升**）
   - ExT2D：红=OD_Post 高（随**运动上升**）
   - 颜色深浅 = |d| 大小；TwoSlopeNorm ±3 截断（本数据 D 范围 −4.73~3.36，超界全深色）
   - 格内 `*` = FDR<0.05（BH 校正；本数据 1100 检验 93 项显著）
   - 配色 `#2166AC`(蓝) → `#F7F7F7`(白) → `#B2182B`(红) = clusterProfiler 官方 7 级 RdBu 两端色

## 通用推广

- **任何"这张图红色/蓝色代表谁"的问题**，一律先追溯生成代码的符号约定再答。
- 不只热图：效应量方向解读（Cliffs'd、Cohen's d、delta）都遵循
  **"符号约定 + 方向锚点验证"** 协议（见 l3-proportion-boxplot-paired-design.md 的方向坑）。
- 同会话多版脚本并存时（R 探索版 + Python 成图版），**成图版优先**——用户看的是最终交付。
