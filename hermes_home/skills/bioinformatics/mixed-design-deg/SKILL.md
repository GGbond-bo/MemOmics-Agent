---
name: mixed-design-deg
description: "混合设计差异表达分析（组间独立比较 + 组内配对比较同存）：24 donors × 2 时间点的 aging/糖尿病/运动前后 DEG。pseudo-bulk + dream LMM (1|donor) 统一建模，禁止 cell-level MAST 当主分析。含同构高分文章源码证据库。"
when_to_use: "[mixed-design-deg] 多受试者实验含两组独立比较 + 同一受试者重复测量（pre/post、多时间点）时找 DEG：如 三组（Y/O/OD）× 运动前后、干预前后配对 + 组间比较、纵向随访组间对比。触发词：独立+配对、混合设计、配对比较、pre/post、重复测量、随机效应 donor"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [deg, mixed-design, lmm, dream, pseudobulk, paired, repeated-measures, 03_高级分析]
    difficulty: advanced
    language: R
    category: scRNA
prerequisites:
  r_packages: ["variancePartition", "DESeq2", "edgeR", "limma", "muscat"]
---

# 混合设计 DEG 分析（组间独立 + 组内配对）

## 适用场景

- 设计含两种比较：**组间独立**（如 Y_Pre vs O_Pre 衰老、O_Pre vs OD_Pre 糖尿病）+ **组内配对**（同一 donor 运动前后 Post−Pre）
- 典型结构：24 donors × 2 时间点 = 48 样本，3 组（Y=10 / O=7 / OD=7）
- 用户已用 MAST 但被质询"独立、配对、随机效应怎么处理"时 → 本 skill 是答案

## 核心结论（CNS 编辑视角）

**主分析 = pseudo-bulk counts → dream (variancePartition LMM)**，一个模型统一建模全部比较 + group:time 交互：

```r
# ① 按 donor × time × celltype 聚合 counts（edgeR::sumTechReps 或 rowsum）
# ② 每个 celltype 单独建模:
form <- ~ group + time + group:time + (1|donor)   # group: Y/O/OD; time: Pre/Post
fit  <- dream(dge, form, metadata)
# ③ 提取对比：
contrasts <- makeContrastsDream(form, metadata,
  Aging     = O_Pre - Y_Pre,                                  # 独立
  Diabetes  = OD_Pre - O_Pre,                                 # 独立
  Ex_Y      = Y_Post - Y_Pre, Ex_O = O_Post - O_Pre,          # 配对
  Interact  = (O_Post-O_Pre) - (Y_Post-Y_Pre))                # 组×时间交互（卖点）
fit <- eBayes(fit); res <- topTable(fit, coef="Aging", number=Inf)
```

**备选**（按稳健性排序）：
1. dream LMM（首选，`(1|donor)` 显式建模配对）
2. limma-voom + `block=donor`（duplicateCorrelation 估计重复测量相关）
3. muscat::pbDS（Crowell 2020 同场景现成封装）
4. DESeq2 `~ donor + condition` 独立 paired design（组间+组内全塞一个模型会耗自由度，配对比较建议单独跑）

## ⛔ 为什么不要 cell-level MAST 当主分析（3 条硬伤）

1. **假重复**：同 donor 数千细胞被当独立观测 → I 型错误暴涨（Zimmerman 2021 Nat Commun, 10.1038/s41467-021-21038-1；Squair 2021 Nat Commun, 10.1038/s41467-021-25960-2）
2. **配对未建模**：Pre/Post 同一人 = 重复测量，不建模被个体噪声淹没或虚假放大
3. **随机效应支持弱**：MAST hurdle + (1|donor) 的收敛/自由度业界不认可是金标准；拆开跑 N 次独立比较 → 多重检验不一致、无法回答 group:time 交互

MAST 只能保留为**细胞级敏感性分析**（注明假重复风险），两法交集 = 稳健 DEG。

## 参考文献与源码证据库

见 `references/mixed-design-deg-evidence.md`：
- Lovric 2022 Commun Biol（10.1038/s42003-022-04088-z）— 运动单细胞 3 人配对，源码用 cell-level Wilcoxon 无配对建模 = **反面教材**
- MoTrPAC 大鼠（Nature 2024）— bulk DESeq2 + RNA 质量协变量（RIN/globin/UMI dup）
- MoTrPAC 人类 meta 分析 — rma.mv `random = ~ V1|gse`（研究随机效应）+ `mods = ~ training + time` = 独立+配对+随机效应三者同时建模的正统示范
- Zemke 海马 aging — 连续年龄相关（用户专利参考）

## 找同构文章源码的 GitHub 工作流

1. `https://api.github.com/search/repositories?q=<关键词>&sort=stars`（未认证限流 60/h，遇 403 直接 clone 已知仓库）
2. `git clone --depth 1 <repo> /e/tmp/deg_source/<名>`（clone 不占 API）
3. search_files `*.R`/`*.ipynb` 定位 DEG 脚本；grep `DESeq|MAST|FindMarkers|dream|limma|pseudobulk`
4. 读核心函数（formula/contrasts/聚合代码），别只看 README
5. 关键词：`MoTrPAC` / `exercise+single+cell+skeletal+muscle` / `<tissue>+aging+single` + 作者名

## 汇报规范

- 先给"统计单位是什么"的自答：group 对比用 donor 级聚合值，donor 是统计单位
- 交互（group:time）才是卖点，不要只报各组的运动前后 DEG
- 主分析 dream；MAST 作为敏感性分析，两法交集 = 稳健 DEG
- 每对对比单独跑、单独辩论（铁律：不准一次跑完所有对比组）