# 跨物种衰老可替代性专利 · 验证数字精确出处 + 三张验证图画法

> ⚠️ **口径警告（2026-09-11 起）**：本文件下方「一、关键数字表」记录的是 **continuous 口径**（已作废）。
> 该专利 2026-09-11 起改用 **all 口径**（`M2/human_ageDA_all.csv` + `M2/monkey_ageDA_all.csv`），
> 现行数字见下表；交底书现行版 = `技术交底书_已填写_附图版_v9.docx`（v8 及更早为 continuous，勿用）。
> 引用数字前先确认口径 —— 见 `references/deliverable-caliber-switch-traceability.md`。

## 〇、现行 all 口径数字（唯一有效）

| 数字 | all 值 | 出处 / 一行判据（在 `P3_L1_data/M2_repro_gene_conservation_all.csv` 上） |
|------|--------|-----------|
| ortholog 基因对 | **16,029** | `len(df)` |
| 人侧强效应池 | **1,409** | `(df.Z_human.abs()>=12).sum()` |
| 候选（强效应且同向） | **582** | `((df.Z_human.abs()>=12)&sd).sum()`，`sd=np.sign(Z_human)==np.sign(Z_monkey)` |
| **核心元件 A 级** | **357** | `((df.Z_human.abs()>=12)&(df.p_monkey<0.05)&sd).sum()` |
| **双侧铁证** | **16** | 上式 且 `df.Z_monkey.abs()>=12` |
| 双高反向 | **19** | `((df.Z_human.abs()>=12)&(df.Z_monkey.abs()>=12)&~sd).sum()` |
| 对称 min 法（对照） | **16** | 双侧 \|Z\|≥12 且同向 |
| 漏检 / 漏检率 | **341 / 95.5%** | 357−16；341/357 |
| 富集倍数 | **12.3×** | 357/(582×5%)=357/29.1 |
| 双向随机期望 / 双向富集 | **14.6 / 24.5×** | 582×50%×5%；357/14.6 |
| v5 A 类 | **2,336** | 双侧 \|Z\|≥1.96 且同向 |
| 整体 ρ / 同向比例 | **−0.1955 / 0.4636** | 锚定器 stats txt（置换 p=0.0000, n_perm=2000） |
| 人侧 shuffle（**口径无关**） | **24.3× / p=0.005** | `v8_age_shuffle_stats.rds`（基于人侧自身 tile 矩阵，不随 M5 输入口径变） |
| v7 外推 | `Z_h=1.0335+1.2931·Z_m`, **R²=0.3472** | `pipeline_out_all/v7_extrapolation_baseline.json` |

**两套独立实现互证**：正本锚定器 `repro_m3_from_M2.py` → 16,029 对；完整管线 `repro_full_pipeline.py` → 16,010 对；
核心指标（357/16/95.5%/12.3×/19）**完全一致** → all 口径结论不依赖单一实现。

**名单换血**：all 核心元件与 continuous 交集仅 159（丢失 177 / 新增 198）；
357 主清单仍含 SLC1A2、GRIA1、GRIA2、NRXN1、EPHA5、SORL1（SYT1、EPHA6 掉出）；
16 子集仅保留 SLC1A2、NRXN1、SORL1 + RBFOX3、CACNA1B、KCNT1、STXBP5L 等。

---

## 一、关键数字精确出处（⚠️ continuous 口径 · 已作废，仅作历史对照）

| 数字 | 精确值 | 出处 / 复现 |
|------|--------|-----------|
| 24 倍富集 | **24.3**（不是 24.0） | `v8_age_shuffle_stats.rds` `$human`: obs=6285, null_mean=258, null_sd=1075, ratio=24.3, p=0.005 |
| 猴侧年龄效应（诚实边界） | ratio=0.231, p=0.815（独立不显著） | 同文件 `$macaque`: obs=34128, null_mean=147794 |
| 537 候选 | 537 | `strong(\|Z_human\|≥12) & same_direction` 计数 |
| 336 核心元件 | 336 | `strong & same_direction & p_monkey<0.05` |
| 37 最高置信子集 | 37 | 336 里再 `\|Z_monkey\|≥12` |
| 12.5 倍富集 | 336/(537×0.05)=12.5 | 同上（期望命中 26.85） |
| 89% 漏检 | (336−37)/336 = 299/336 = 89.0% | 对称 min vs 主-参考非对称对比 |
| 整体 ρ / 同向比例 | −0.0627 / 0.4155 | `np.corrcoef(Z_human, Z_monkey)` |

⚠️ 正文概述常写「24 倍」，精确值是 24.3——两者是同一事实（24.3≈24）。写附图说明建议用「24.3 倍」或「约 24 倍」，避免被审查员/用户挑「图文不符」。

## 二、三张验证图（脚本 `results/<sid>/scripts/regen_figures_v2.py`）

1. **图2 置换检验空分布**：人侧年龄标签 shuffle，用 gamma 近似空分布（`k=mean²/var≈0.058`, `θ=var/mean≈4479`，从 null_mean=258/null_sd=1075 反推）+ **log x 轴** + observed 竖线（6285）+ 空分布均值虚线（258）。标注「富集 24.3 倍 p=0.005」。log 轴必要：obs 与 null_mean 差一个数量级，线性轴会挤压。
2. **图3 336 核心元件散点**：x=Z_human, y=Z_monkey，299 个（`|Z_monkey|≤12`）浅蓝 + 37 个（`|Z_monkey|≥12`）深红，参考线 ±12。这张图直接可视化「对称 min 只筛 37 vs 主-参考筛 336」的对比实验——是最有力的创造性可视化。
3. **图4 12.5 倍富集**：log y 轴柱状，期望 26.9（灰）vs 实际 336（蓝），标注「富集 12.5 倍」。

## 三、出图 + 内嵌 pitfall

- **mathtext 下标**：SimHei/微软雅黑无 Unicode 下标字符（`₁`/`₂` = Glyph 8321/8322 missing，出 UserWarning 且显示方框）。Z₁/Z₂ 必须用 mathtext `$Z_1$`/`$Z_2$` 渲染，不要用 `\u2081`/`\u2082` 字面量。
- **docx 被 Word 占用**：旧 docx 被 Word 打开时（目录有 `~$xxx.docx` 锁文件），`docx.save()` 到原路径会锁冲突。处理：输出新文件名（如 `_v2.docx`），旧文件让用户自己关掉，不覆盖。
- **OCR 检查三张图（用户明确要求）**：`vision_describe` 逐张核对——① OCR 有文字、② 亮度图非全空白（空白图主色 100% 浅灰是致命缺陷）、③ 图内标题/坐标轴/关键数字与附图说明三者一致。内嵌 docx 前用 `zipfile` 读 `word/media/` 确认图片数 == 说明条数。
