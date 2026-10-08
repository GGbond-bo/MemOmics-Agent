# FigA/B 效应矩阵图族规格卡（18 程序 + 4 身份 × 6组/5效应/亚群）

本文件是「18 程序 + 4 身份，各自出 6组图 / 5效应图 / 亚群图 = 6 张」的**完整规格与溯源卡**。
用户 2026-09-15 要求「找 FigA3_program_subcluster 和 FigA2_program_5effects 的代码，**颜色这些都要对得上**」时定稿。

## 1. 唯一生成脚本

```
results/<sid>/scripts/fig_split_v10.py     # 300 行，一次跑通 A1/A2/A3 + B1/B2/B3 六张
```

行号索引（改图时按此定位，不要通读）：

| 图 | 行号区间 | 画布 |
|----|---------|------|
| FigA1_program_6groups | ≈184–192 | 16.5 × 8.4 in |
| **FigA2_program_5effects** | **≈194–203** | 16.5 × 8.4 in |
| **FigA3_program_subcluster** | **≈205–242** | 9.0 × 12.0 in |
| FigB1_identity_6groups | ≈245–253 | 16.5 × 8.4 in |
| FigB2_identity_5effects | ≈255–264 | 16.5 × 8.4 in |
| FigB3_identity_subcluster | ≈266–298 | 9.0 × 6.0 in |

## 2. 配色 / 归一化（「颜色对得上」的逐条依据）

| 项 | FigA2 / FigB2（5 效应） | FigA3 / FigA1 / FigB1 / FigB3 |
|---|---|---|
| cmap | `plt.cm.RdBu_r` | `plt.cm.RdBu_r` |
| 色带锚点 | 蓝 `#2166AC` → 白 `#F7F7F7` → 红 `#B2182B` | 同左 |
| norm | `TwoSlopeNorm(vmin=-3, vcenter=0, vmax=3)` | `TwoSlopeNorm(vmin=-2, vcenter=0, vmax=2)` |
| 数值含义 | Cohen's d（`effect5_d_v2.csv` 的 `d` 列） | 行内 z-score（跨 6组×10亚群 / 跨 10亚群 标准化） |
| 色条标签 | `Cohen's d` | `row z-score` |
| 星号 | FDR `q<0.05` 打 `*`；`|val|>1.5` 白字，否则黑字 | 无 |
| 导出 | `dpi=300`，png + pdf + svg 三格式（`save()`） | 同左 |

> ⚠️ 配色空间是 **RdBu_r**（红=正、蓝=负），不是自建 LinearSegmentedColormap。历史上有过深色红 `#B2182B` 与浅红混用的迷惑，认 `RdBu_r` 为准。
> ⚠️ 5 效应用 ±3、z-score 用 ±2 —— **两个 norm 不同**，改图时最容易串。

**行分组色带 `GROUP_COLORS`（左侧色条 + 旋转 90° 的分组名）**

```
Metabolic        #2C7FB8
Structural       #7BA05B
Regeneration     #F4A261
Stress-Inflam    #D64550
Atrophy-Fibrosis #8C5FA8
Identity         #6A6A6A     ← 曾经缺失导致 KeyError，见陷阱
```

**布局常量（两图共用）**：`CELL = 1.0`（等同行/列间距 → **无白色缝隙**，`edgecolor="none"`）、行分组间隙 `0.2`、面板间距 `PANEL_GAP = 1.8`、亚群标签 45° 贴底 `y=-0.15` 色 `#333333` 6.8pt、行标签 8.5pt、`subplots_adjust` 手动布局（**禁 `tight_layout`**，否则 PNG 与矢量渲染分叉）、标题 `pad=24`。

## 3. 数据依赖（复跑必查）

| 项 | 值 |
|---|---|
| 数据源 1 | `E:/骨骼肌锻炼/MF_AUCell_meta.csv`（细胞级 AUCell 打分，58 列，含 `type`/`annotation_L3`/`samplename` + 22 个 `*_AUC` 列） |
| 数据源 2 | `results/<sid>/effect5_d_v2.csv`（五效应 Cohen's d 与 q，列含 `score/effect/sub/d/q`） |
| 列名映射 | 打分裸名 + `_AUC` 后缀，用 `col_map()` 兼容（**漏映射 → pivot 全 NaN → 全白热图**） |
| 18 程序顺序 | OxPhos, Glycolysis, FattyAcidMetabolism, AMPK_PGC1a, Adipogenesis, Insulin, mTORC1 / Sarcomeric / RegMyon, Denervation, Autophagy / SenMayo, Stress, TNFA, Inflammatory, ROS / Atrophy, Fibrosis |
| 4 身份 | scoreI, scoreII, scoreIIa, scoreIIx |
| 10 亚群顺序 | LRP1B+(I), OTUD1+(I), OTUD1+(II), Pure Type I, Pure Type IIA, Pure Type IIX, RP_high(I), RP_high(II), RSS, Specialized MF |
| 6 组顺序 | Y_Pre, Y_Post, O_Pre, O_Post, OD_Pre, OD_Post |
| 5 效应顺序 | Aging, T2D, ExYoung, ExOld, ExT2D |

## 4. 脚本内 helper（改图前先看这层，不要重写）

| 函数 | 作用 |
|---|---|
| `agg_matrix(names)` | `type × annotation_L3` 均值 → 行内 z-score（6 组图用） |
| `sub_matrix(names)` | `annotation_L3` 均值（不分 type）→ 行内 z-score（**FigA3/FigB3 的数据源就是它**） |
| `eff_matrix(names)` | pivot 出 Cohen's d 与 q 两个矩阵（5 效应图用） |
| `row_pos_map(groups)` | 行位置映射，分组间留 0.2 间隙 |
| `draw_panels(...)` | 多面板横排：逐格 `Rectangle` + 面板标题 + 亚群标签 + 星号 |
| `draw_group_stripes(...)` | 左侧分组色条 + 旋转分组名 |
| `add_cbar(fig, cmap, norm, label)` | 右侧色条 + 底部 `* FDR < 0.05` 注记 |
| `save(fig, base)` | **dpi=300** 导出 png/pdf/svg 并打印字节数 |

z-score 用 numpy 层向量化写入（`Z[:] = (Z.values - mu) / sd`），**不要**用 pandas `apply(zscore, axis=1)`（会把 DataFrame 压成 Series，丢失列索引 → `IndexError: Too many indexers`）。

## 5. 陷阱

- **`KeyError: 'Identity'`**：`GROUP_COLORS` 必须覆盖所有分组名。程序组分 5 个轴 + 身份组 1 个，曾漏 `Identity` 键 → 整套 B 图挂掉。
- **脚本名 ≠ 图名**：`FigA2_program_5effects` 由 `fig_split_v10.py` 生成。按图名在 `scripts/` 里 `search_files` 会 0 命中，**不要据此断言"脚本不存在"**——走溯源三步法（见 SKILL.md）。
- **`_AUC` 后缀**：漏掉 `col_map()` 映射 → reindex 后全 NaN → 生成尺寸正常但内容全白的热图。加 `assert` 或列名断言拦截。
- **`tight_layout` + `add_axes` 色条并存** → PNG 底部被裁、矢量正常，呈现"PNG 没变、PDF 对了"的假分叉。本族一律 `subplots_adjust` 手动布局。

## 6. 本次找回代码的溯源链（可复用的证据顺序）

1. `search_files(target="files", pattern="*program*")` 在 `results/<sid>` 下 → 拿到图文件，但**不含代码**
2. `search_files(target="content", pattern="FigA2|FigA3")` 在 `scripts/` 下 → **0 命中**（脚本名不含图名）
3. `skill_evolution(action="query_logs", skill_name="scipilot-figure-skill")` → ✅ 决定性证据：`proven_runs` 里既有 `fig_split_v10.py` 的 params/result，也有一条历史记录明写「确认 FigA3 生成脚本为 fig_split_v10.py 的 `sub_matrix(names)` 函数（第 77 行）」
4. `session_search(query="FigA2_program_5effects FigA3_program_subcluster", role_filter="user,assistant,tool")` → 交叉确认「图名 → 脚本」映射表与产出清单
5. `read_file` 取 `fig_split_v10.py` 逐行代码 + 颜色常量 → 交付

**结论**：`skill_evolution(query_logs)` 是查"某产物出自哪个脚本"的最快通道，`session_search` 带 `role_filter="user,assistant,tool"` 是第二通道，磁盘 `search_files` 只在脚本名与产物名同源时有效。
