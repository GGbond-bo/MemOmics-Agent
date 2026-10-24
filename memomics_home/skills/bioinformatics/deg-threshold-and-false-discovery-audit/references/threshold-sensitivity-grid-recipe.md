# 阈值敏感性网格 · 完整配方（FDR × 效应量两维）

> 来源：2026-10-23 五对比人示例组织 scRNA-seq DEG（cell-level RUV-MAST，上游全量表 340,971 行；会话 memomics-f3cbef42）。
> 适用：「做阈值敏感性 / 不要重跑模型 / 结论对阈值稳不稳 / 这些数字换门槛会不会变」类请求。
> 配套 SKILL.md「🔬 阈值敏感性网格」节与「铁律 1 · 集合等式法」附注。

## 0. 前置：先做口径实证（同一样本的 0.025 vs 0.25 教训）

接手已交付/第三方筛选表时，先按 SKILL.md 铁律 1 附注做**双向集合等式**：
交付表键集合 F 与候选判据集合 C 必须 **C−F=0 且 F−C=0**（跨全部 sheet/对比）。
实测：文件名 `..._coef025` 实际口径 = `|coef|≥0.25`（"coef025"=0.25）；5 对比全部双向差集 = 0 才落槌。
确认口径后，一切敏感性讨论都基于**实证口径**，不是文件名推断值。

## 1. 输入与网格

- 输入：上游 merged 全量表（每对比一文件，如 sheet=`ALL_merged`；列含 gene / coef / fdr / celltype / comparison / method）。**行 = 全部检验行（gene×celltype），不重跑模型**。
- 网格：FDR {0.1, 0.05, 0.01, 0.001} × |coef| {0.05, 0.1, 0.15, 0.25, 0.4, 0.6, 1.0}（现行档必含）。
- 上下调一律用 `coef` 符号派生；表内 `direction` 列常为全表常量说明列，不可逐行用。

## 2. 四类输出（代码骨架）

```python
big = pd.concat([df.assign(contrast=k) for k, df in allrows.items()], ignore_index=True)
big["abscoef"] = big["coef"].abs(); tot = big.groupby("contrast").size()
# ① 主表：每格 rows / unique genes / up% / retention / top_subcluster（groupby contrast + head(1)）
# ② 亚群级：同上 groupby [contrast, celltype]
# ③ 交集/共享结构：每格 set(gene) 求五对比共同、A-up∩B-down、两两交集计数
# ④ ECDF：np.searchsorted(np.sort(|coef|), 网格点)/n（解释断崖位置）
```

## 3. 读数四模式（每次必报）

| 模式 | 实测（五对比示例组织） | 含义 |
|---|---|---|
| FDR 惰性 | 固定 \|coef\|≥0.25 时 FDR 0.001–0.1 变幅 ≤1.1%（Aging 23,190→23,013） | p 已饱和，筛选力全在效应量；**不得**反推「无多重检验问题」 |
| 断崖 | 0.15→0.25：Aging 46,008→23,178；Ex-Old 16,341→1,846；DM 2,479→311 | 计数数字引用必须带门槛 |
| 标签漂移 | Aging top 亚群：0.05→LRP1B+(I)、0.15–0.25→Pure IIA、≥0.4→RSS | 「XX 亚群主导」须注明阈值命中区间 |
| 交集塌缩 | 五对比共同基因 4,073→399→45→1→0；Aging↑∩Ex-Old↓ 7,502→5,790→785→21 | 共享/核心基因结论必须先给阈值轨迹 |

稳定项（可作正面结论）：规模排序跨 0.05–1.0 七档稳定（Aging>Ex-Old>DM>Ex-DM>Ex-Young）；方向比稳定至 0.25（Aging 96.7–98.1% up；Ex-Old 96.5–97.3% down @0.05–0.15、85.7% @0.25）。

## 4. 措辞红线（L2 辩论裁定 · stats_design 场景 · modify/medium）

- **主口径唯一化**：FDR<0.05 且 |coef|≥0.25 为唯一主结论口径；敏感性网格 = 探索性/补充报告，不替代主结论。
- **宽松阈值计数**（如 DM 33,293 行 @|coef|≥0.05）：cell-level 探索性计数，**不得写「存在大量小效应差异」**（受 SE 低估/伪重复膨胀影响；Squair 2021 PMID 34584091）。
- **共享集合**：写「本主阈值及更严阈值下未检出稳健共响应核心」，**不得写「生物学上不存在」**。
- **方向比/排序稳定**：仅「描述性一致性」，不证明效应真实或消除膨胀。
- **Top 标签漂移**：入补充/限制说明，不进结论段。

## 5. 图（CNS 规格参考）

4 面板：a) 计数 vs |coef|（symlog y + FDR 跨度浅带）、b) up% vs |coef|（50% 参考线）、c) 共享结构 vs |coef|（symlog）、d) |coef| ECDF + 门槛竖线。
现行门槛竖虚线；183mm 宽；图内注用英文；出图后做像素四边距自检（边缘 8px 带零内容、四边距 ≥10px 才放行）。