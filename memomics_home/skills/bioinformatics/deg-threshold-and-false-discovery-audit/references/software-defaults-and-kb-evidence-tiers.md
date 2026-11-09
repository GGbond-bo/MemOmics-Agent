# 软件官方默认值台账 + 知识库参数证据级别读法

> 2026-10-27 实测复核。用途：被问「这个阈值有出处吗 / 默认值是多少 / 知识库怎么说」时**直接查表**，
> 不用重新翻源码；以及把知识库条目按证据级别分层交付，避免把种子默认值包装成文献实证。

## 1. 软件官方默认值台账（均经源码或官方页逐字复核）

| 软件 | 入口 | 参数 | 官方默认 | 取证位置 |
|---|---|---|---|---|
| Seurat **v4.3.0** | `FindMarkers.default` | `logfc.threshold` | **0.25** | `raw.githubusercontent.com/satijalab/seurat/v4.3.0/R/differential_expression.R` |
| Seurat **v4.3.0** | `FindMarkers.default` | `min.pct` | **0.1** | 同上 |
| Seurat **v5.6.0 / main** | `FindMarkers` | `logfc.threshold` | **0.1** | 官方参考页 `https://satijalab.org/seurat/reference/findmarkers` + `main` 分支源码 |
| Seurat **v5.6.0 / main** | `FindMarkers` | `min.pct` | **0.01** | 同上 |
| DESeq2 | `results()` | `alpha` | **0.1** | `raw.githubusercontent.com/thelovelab/DESeq2/main/R/results.R` |
| DESeq2 | `results()` | `lfcThreshold` | **0**（不按效应量过滤） | 同上 |
| DESeq2 | `results()` | `altHypothesis` | `greaterAbs` | 同上 |
| MAST | `zlm()` | 效应量阈值 | **无此参数** | 见 `parameter-provenance-and-mast-thresholds.md` |

**两条由此固定的结论**：
1. 「0.25」的合法血统 = **Seurat v3/v4 出厂默认**（v5 已改 0.1，脚本必须显式写死）。
2. 「0.5」**不是任何软件默认值** = pseudobulk 组间比较的领域惯例切点；DESeq2 本身对效应量完全沉默。
   ⇒ 写 methods 只能写「自定最小生物学意义效应」或「沿用惯例」，⛔ 不能写「软件默认」。

附带证据（官方口径支持组间比较走 pseudobulk）：Seurat `FindMarkers` 官方页原文 ——
「differential expression between groups (e.g. treatment conditions) should account for biological
variation across samples, e.g. by using pseudobulk expression profiles」。

## 2. 知识库参数条目的证据级别读法

参数条目路径：`memomics/knowledge_base/<species>/<tissue>/<direction>/03_测序方法/<assay>/<method>.yaml`。
**每个数值都带 `source` + `confidence`，且文件尾还有一个文件级 `source`**：三处都要读。

| 层级 | 允许取值 | 交付时能说什么 |
|---|---|---|
| 文件级 `source` | `default_seed` | 只能说「惯例 / 种子默认」 |
| 文件级 `source` | `literature` | 可说「文献驱动」，但仍需查是否带 DOI evidence |
| 文件级 `source` | `data_driven` | 可说「本项目实测」 |
| 字段级 `source` | `default_value` | 「软件出厂默认」 |
| 字段级 `source` | `domain_convention` | 「领域惯例，无单一出处」 |
| 字段级 `source` | `data_driven` | 「实测推导」——唯一可当实证引用 |
| `confidence` | low / medium / high | low/medium 必须与溯源类型**同时**报出 |

### 实测样例（本仓库当前状态）

`Homo_sapiens/skeletal_muscle/aging/03_测序方法/RNA/deg.yaml`（date 2026-06-29，文件级 `source: default_seed`）：

| 方法 | 参数 | 值 | confidence | source |
|---|---|---|---|---|
| pseudobulk DESeq2 | padj_threshold | 0.05 | medium | domain_convention |
| pseudobulk DESeq2 | logfc_threshold | 0.5 | medium | domain_convention |
| pseudobulk DESeq2 | min_detection_rate | 0.1 | **high** | **data_driven** |
| pseudobulk DESeq2 | design_formula | `~ 0 + type` | medium | domain_convention |
| MAST | padj_threshold | 0.05 | medium | domain_convention |
| MAST | ebayes | TRUE | low | default_value（Seurat 侧源码不传 `ebayes`，无法核） |

⇒ 交付句式：「KB 的 pseudobulk 口径是 padj<0.05 + |log2FC|≥0.5 + 最小检出率 0.1；其中只有
`min_detection_rate=0.1` 是 `data_driven/high`，其余为 `domain_convention/medium`，文件级 `default_seed`
⇒ 这是惯例而非文献实证，该方向 KB 尚无数值级 DOI 证据条目。」

**「某口径有没有进库」的核查法**：在组织目录下 `search_files` grep 参数名/数值
（本轮 `coef|0.25|logFC` 在 `Homo_sapiens/skeletal_muscle` 全目录命中 **0 文件** ⇒ 用户项目里跑过的
`|coef|≥0.25` 并未入库，不能作为 KB 依据引用）。

## 3. 取证手法：`browser_console` 直接 fetch 源文件取 formals

渲染页可能整页空白（`satijalab.org/seurat/archive/v4.3/findmarkers` 返回 empty page），页面快照又动辄
数万字符。只要默认值就绕开渲染层，一次表达式取完（可同轮并发多个仓库）：

```js
(async () => {
  const out = {};
  const r = await fetch('https://raw.githubusercontent.com/satijalab/seurat/v4.3.0/R/differential_expression.R');
  const t = await r.text();
  const m = t.match(/FindMarkers\.default[\s\S]{0,700}/);
  out.v4 = m ? m[0].match(/logfc\.threshold\s*=\s*[0-9.]+|min\.pct\s*=\s*[0-9.]+/g) : 'not found';
  const r2 = await fetch('https://raw.githubusercontent.com/thelovelab/DESeq2/main/R/results.R');
  const t2 = await r2.text();
  out.deseq2 = t2.match(/(alpha|lfcThreshold)\s*=\s*[0-9.]+/g);
  return JSON.stringify(out);
})()
```

**纪律**：
- 用**带 tag 的 URL**（`@v4.3.0`）才能证明「那个版本」的默认值；`main`/`master` 只代表当下。
- 正则先定位函数名再在窗口内取参数，别全文 grep 数字（同文件多个方法各有默认值）。
- 取不到就当「未核实」写进交付，⛔ 不要用记忆里的数字补位。