# FDR 检验族：定义审计与误报撤回实录（2026-09-28）

用户诉求：*「重算 fdr_sensitivity.csv 的口径」*（前一轮我自查发现并主动标记了口径疑点）。

## 1. 事故链：变量名偷换 → 族定义错 → 数字误报

建表脚本（`audit_effect5_v3.py`，内联 `execute_python` 跑的、**未落盘**）真实代码：

```python
df["axis"] = df["score"].str.replace("_AUC$", "", regex=True)      # ← axis 装的是【程序名】
df["q_f_all"]   = bh(df["p_np"])
df["q_f_eff"]   = df.groupby("effect")["p_np"].transform(bh)
df["q_f_score"] = df.groupby("axis")["p_np"].transform(bh)          # 实 = 每程序 50 格（命名尚可）
df["q_f_eax"]   = df.groupby(["effect", "axis"])["p_np"].transform(bh)  # 实 = 每效应×程序【10 格】
FAM = {"全表1100": "q_f_all", "每效应220": "q_f_eff", "每score50": "q_f_score", "每效应x轴": "q_f_eax"}
```

- `axis` 列 22 个 unique，全部是 `scoreI / scoreIIa / Glycolysis / mTORC1 / …` —— **程序名**
- FigA2 语境里的「轴」是**生物学分类轴**（②底物代谢/③营养感应/④收缩装置/⑤衰老炎症ROS/⑥终末重塑），概念完全不同
- ⇒ `q_f_eax` 被我在弹窗和汇报里讲成「每效应×轴 = 133，含 ExOld 16 / T2D 3 / ExYoung 2」

**用户下一轮直接逼问**：*「五效应的计算方法，你有文献参考吗？只有衰老在显著变化，为什么其他的就不显著呢？你真的按照独立和配对进行计算了吗？」* —— 逼出了这次自查。

## 2. 数学矛盾：暴露口径错的信号

`ExOld` 的 `p_np` 最小值 = **0.015625**（n=7 Wilcoxon 双侧下界 `2/2⁷`）。在 10 格族里 BH 首选 q ≥ `0.015625 × 10 / 1` = **0.156** —— **不可能 < 0.05**，可表里却有 16 格显著。

> **可复用的判据**：拿到"某效应有零星显著"时，先算 `p_min × 组大小`。若结果 > 0.05 却在表里显著 → 族/列口径必有错配，别急着解释生物学。

真因：组内有 **19 格并列 p = 0.015625**，`np.argsort` 给并列值分配了不同 rank，其中 rank 较大的格拿到 `p×n/r` 较小的 q（本例 n=10, r=8 → 0.0195），制造出"显著"。这是 tie 未按 BH 原定义处理的产物。

## 3. 修正后的完整族表（p 列 = `p_np`，与交付表同口径）

| 族 | 分组键 | 组数 | 每组格数 | Aging | T2D | ExYoung | ExOld | ExT2D | 合计 |
|---|---|---|---|---|---|---|---|---|---|
| `q_all` | 无 | 1 | 1100 | 71 | 0 | 0 | 0 | 0 | 71 |
| `q_eff` ★交付口径 | `effect` | 5 | 220 | **111** | 0 | 0 | 0 | 0 | 111 |
| `q_prog` | `prog` | 22 | 50 | 76 | 0 | 0 | 14 | 0 | 90 |
| `q_e_prog` | `effect×prog` | 110 | **10** | 112 | 3 | 2 | 16 | 0 | 133 |
| `q_axis` | `axis`（真生物轴 7 类） | 7 | ~157 | 67 | 0 | 0 | 0 | 0 | 67 |
| `q_e_axis` | `effect×axis` | 35 | ~31 | 106 | 0 | 0 | 0 | 0 | 106 |
| `qp_eff` | `effect`（p 列换 `p_par`） | 5 | 220 | 114 | 0 | 0 | **6** | 0 | 120 |

**真生物轴族下各效应的最小值 q**（这才是可写论文的）：

| 效应 | p_np_min | q_e_axis_min | 判定 |
|---|---|---|---|
| Aging | 1.03e-4 | 0.0003 | ✅ 106 格显著 |
| ExOld | 0.015625 | **0.0694** | ❌ 差一点（`scoreIIa×OTUD1+(II)`） |
| T2D | 0.006993 | 0.0932 | ❌ |
| ExYoung | 0.005859 | 0.1953 | ❌ |
| ExT2D | 0.015625 | 0.3750 | ❌ |

## 4. 生物轴映射（源：`task2/results/gene_signature_axis_classification.md`，18 集 / 6 轴）

FigA2 用的 22 程序 = 6 轴 18 集 − ①技术伪影(Stress) + 4 个纤维型身份 score：

| 轴 | 成员程序 |
|---|---|
| ①技术伪影（不入结论） | `scoreStress` |
| ②底物代谢 | `scoreOxPhos`, `Glycolysis`, `FattyAcidMetabolism`, `Adipogenesis` |
| ③营养感应/蛋白稳态 | `scoreInsulin`, `mTORC1`, `AMPK_PGC1a`, `Autophagy` |
| ④收缩装置/神经肌单元 | `scoreSarcomeric`, `scoreRegMyon`, `Denervation` |
| ⑤衰老-炎症-ROS 环 | `scoreSenMayo`, `scoreInflammatory`, `scoreTNFA`, `scoreROS` |
| ⑥终末失代偿重塑 | `scoreAtrophy`, `Fibrosis` |
| ⑦纤维型身份（未纳轴） | `scoreI`, `scoreII`, `scoreIIa`, `scoreIIx` |

## 5. 从 `system_log.jsonl` 捞回未落盘的审计脚本

生成脚本是内联 `execute_python` 跑的 ⇒ `search_files` 在 `scripts/` 里**找不到**（total_count=0），但日志里有全文：

```python
import json
p = "results/<sid>/log/system_log.jsonl"
for i, line in enumerate(open(p, encoding="utf-8", errors="ignore")):
    if "q_f_eax" in line:                       # 搜特征字符串，列名/函数名最灵
        d = json.loads(line)
        if d.get("tool") == "write_file":
            print(d["args"]["content"])         # 完整脚本源码
```

本例在 `system_log.jsonl` 第 10193 行命中，取回 `audit_effect5_v3.py` 全文，才看到 `df["axis"] = ...` 那一行。

## 6. 撤回话术（用户会拿旧汇报逐字对照，必须点名）

> **我上一轮给你的那批数必须撤回**：「每效应×轴 = 133，含 ExOld 16 / T2D 3 / ExYoung 2」—— 这三个数字全部来自 **10 格小族**，不是生物轴族。族越小门槛越低，所以它们才「显形」。真生物轴族（~31 格）下：ExOld 0 / T2D 0 / ExYoung 0。

配套三动作：
1. 旧表 `os.replace()` → `archive_superseded/effect5_effsize_v3_fdr_sensitivity_pre_v2.csv`
2. 新表 `effect5_effsize_v3_fdr_sensitivity_v2.csv`（列：`prog`/`axis`/`q_all`/`q_eff`/`q_prog`/`q_e_prog`/`q_axis`/`q_e_axis`/`qp_eff`/`qp_e_axis`）
3. `session_memory(add, kind=finding, pinned=True)` 写「⚠️FDR口径更正」条目