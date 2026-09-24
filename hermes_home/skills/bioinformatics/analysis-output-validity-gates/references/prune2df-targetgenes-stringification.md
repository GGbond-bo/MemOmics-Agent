# 案例：pySCENIC 静默产出无效 —— TargetGenes 字符串化 → regulon 变字符 → AUCell 全 0

（2026-09-24 真机定位；人骨骼肌 snRNA-seq，2132 nuclei × 5277 模块 → 264 regulons）

## 症状（不报错、文件齐全、内容是垃圾）
- 全流程 `exit 0`，日志正常：`264 regulons identified / 2132 cells scored / ✓ AUCell scoring completed`
- `aucell_matrix.csv` 2132×264 = **562,848 个值全部为 0**；`aucell_summary.csv` 的
  `mean/std/max_activity` 全 0.0、`n_active_cells` 全 0
- `regulons.csv` 的 `target` 列是**单字符**：`[`、`(`、`'`、`E`、`B`…（11278 行 / 264 regulons ≈
  每 regulon 45 个"靶基因" = 该 regulon 字符串 repr 的**去重字符集**）
- `pickle.load(regulons.pkl)[0].genes` = `('[', '(', "'", 'H', 'I', 'V', ...)`；
  `gene2weight` = `{'[': 1.0, '(': 1.0, ...}`（键是字符，权重全 1.0）
- **60 模块的小规模 smoke run 同样复现** → 与规模无关，不是"数据太大"问题

## 根因链（读源码 + pickle 实查，逐环可复现）
1. `pyscenic.prune.prune2df()` 返回的 DataFrame 中，`('Enrichment', 'TargetGenes')` 列的值是**字符串**：
   ```
   "[('HIVEP2', np.float64(1.3553418140699536)), ('FOXP2', np.float64(1.300032683910589)), ...]"
   ```
   （`np.float64(...)` 包装 = numpy≥2 的 repr 风格，说明被人 `str()/repr()` 过）
2. `pyscenic.transform.df2regulons()` → `_regulon4group()` → `row2regulon()`：
   `Regulon(..., gene2weight=row[COLUMN_NAME_TARGET_GENES], ...)` —— **原样透传，不校验类型**
3. `ctxcore.genesig.Regulon.__init__` 的 `__attr_converter_gene2weight(val)` 把 str 当
   「无权重基因列表」语义（与 `from_gmt` 同族）→ **逐字符**生成 gene2weight，权重 1.0
4. AUCell 拿到字符级基因集 → 与表达矩阵（2904 个 HGNC 符号）零交集 → 全 0
   （AUCell 会为每个 regulon 打印 `Less than 80% of the genes in <TF>(+) are present in the expression
   matrix.` —— **264 行刷屏就是这个 bug 的信号**，不要当"正常 warning"忽略）

## 定位实验（A/B 两条 client 路径，5 模块、<1 分钟）
```python
modules = pickle.load(open("modules.pkl", "rb"))[:5]
# A: prune2df(dbs, modules, MOTIF_TBL, client_or_address="dask_multiprocessing", num_workers=2)
# B: prune2df(dbs, modules, MOTIF_TBL, client_or_address=<dask.distributed Client>, num_workers=2)
# 各自 probe：type(motif_df["TargetGenes"].iloc[0]) → str 还是 list[tuple]
#            + df2regulons 后 regulon.genes 与表达矩阵基因的交集数
```
结论：**字符串化与 client 路径无关**（`dask_multiprocessing` 与 `distributed Client` 都会），
是 `prune2df` 聚合层的固有行为 → 别指望换调度器解决，必须在 `df2regulons` 之前归一化。

## 修复
```python
import re
import numpy as np
import pandas as pd
from pyscenic.prune import df2regulons

# 兼容 ('G', 1.23) 与 ('G', np.float64(1.23))
TG_RE = re.compile(r"\('([^']+)',\s*(?:np\.float64\()?([0-9eE+\-.]+)")

def normalize_target_genes(v):
    """TargetGenes → [(gene, weight), ...]；list 原样、字符串则反解析"""
    if isinstance(v, str):
        out = []
        for g, w in TG_RE.findall(v):
            try:
                out.append((g, float(w)))
            except ValueError:
                out.append((g, 1.0))
        return out
    return [(str(g), float(w)) for g, w in v]

if motif_df.columns.nlevels == 2:
    motif_df.columns = motif_df.columns.droplevel(0)      # → AUC/NES/.../TargetGenes/RankAtMax
motif_df = motif_df.copy()
motif_df["TargetGenes"] = [normalize_target_genes(v) for v in motif_df["TargetGenes"]]
regulons = df2regulons(motif_df)                          # 此时才得到真实 HGNC 基因集
```

## 修复后必做自证（任一不过就不许进下游、不许写结论）
```python
ex_cols = set(pd.read_csv("gene_subset_hvg_tf.txt", header=None)[0])   # AUCell 实际输入基因
hits = np.array([len(set(r.genes) & ex_cols) / max(1, len(r.genes)) for r in regulons])
assert hits.mean() > 0.9, "regulon 基因与表达矩阵不重叠 → TargetGenes 仍是字符串"
auc = pd.read_csv("aucell_matrix.csv", index_col=0)
assert (auc.values > 0).mean() > 0.5, "AUCell 大面积 0 → 回到 regulon 基因集校验"
```

## 顺带踩到的坑
- **`motif_df` 没有 `TF` 列**：列是 8 个 `('Enrichment', X)`，X ∈ `AUC / NES / MotifSimilarityQvalue /
  OrthologousIdentity / Annotation / Context / TargetGenes / RankAtMax`。自写审计表里 `motif_df["TF"]`
  → `KeyError: 'TF'`，而且是在 **9 分钟剪枝跑完之后**的导出步才崩（最亏）。
  动手前先 `print(list(motif_df.columns))`；需要 TF 就从 regulon 对象上取
  （`regulon.transcription_factor`）。
- **修复只需要重跑 cisTarget**：`adjacencies.csv`（GRNBoost2 产物，最贵）与 `modules.pkl` 已在盘上
  可直接复用，别从 GRNBoost2 重新跑起。
- **旧产出先挪走再重建**：把未被正确解析的中间产物移到 `_old_*/` 子目录留痕，避免与修复版混淆
  （用户会核对文件来源）。