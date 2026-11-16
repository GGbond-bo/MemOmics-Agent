# Seurat v5 `JoinLayers` 大对象内存爆炸 —— 源码级记录

> 核实日期 **2026-10-24**（时点版本：Seurat 5.6.0 / SeuratObject 5.4.0）。
> 触发：用户报「单核 + 320 GB 内存、50 万细胞，JoinLayers 没跑成功」。
> 本文件是 `seurat-large-object-memory-management` 的证据底座；SKILL.md 给结论与代码，这里给依据与命令。

---

## 0. 一句话结论（可直接作为回复开头）

`JoinLayers` 撑不住**往往不是内存不够**，而是 SeuratObject 里一个**32 位整数溢出 bug**：
合并多层时把所有层的非零元素个数累加进 `int`，超过 2³¹（≈21.5 亿）就变负数 →
`reserve()` 收到负数转成巨大无符号值 → 标准库抛 `std::length_error`
（Linux 显示 `Error: vector::reserve`，macOS 显示 `Error: vector`）。
**该 bug 在 2026-10 时点仍未修复**（证据见 §4），所以「加内存」解决不了。

---

## 1. 机制：逐条有源码依据

| # | 机制 | 源码位置（均于 2026-10-24 实测 grep 到） |
|---|---|---|
| 1 | 默认并 **counts + data + scale.data** 三类层 | `SeuratObject/R/assay5.R:1059-1097`（`layers <- layers %||% c('counts','data','scale.data')`） |
| 2 | 逐层 stitch 时用 `StitchMatrix(x, y, rowmap, colmap)` | `R/assay5.R:2870-2910`（`JoinSingleLayers`） |
| 3 | 同一 feature ⇒ `cbind` 快路；**不同 feature ⇒ C++ 路径** | `R/utils.R:1565-1593`：`use.cbind <- all(duplicated(all.rownames)[2:n])`；else `lapply(all.mat, as, "RsparseMatrix")` → `RowMergeMatricesList()` |
| 4 | C++ 里每层再拷成 Eigen RowMajor 稀疏矩阵 | `src/data_manipulation.cpp:83`（`Rcpp::as<Eigen::SparseMatrix<double, RowMajor>>(mat_list.at(i))`） |
| 5 | triplet 列表 = **16 B / 非零元** | `src/data_manipulation.cpp:12`（`typedef Eigen::Triplet<double> T;`）+ `:96-98` |
| 6 | **溢出点**：非零总数累加进 signed int | `src/data_manipulation.cpp:79` `int num_nZero = 0;` / `:93` `num_nZero += mat_vec[i].nonZeros();` / `:98` `tripletList.reserve(num_nZero);` |
| 7 | 磁盘层走**独立**实现（不物化） | `R/utils.R:2251-2274`（`StitchMatrix.IterableMatrix`：`rbind` + `Reduce(cbind)`，缺行用 `SparseEmptyMatrix` 补齐）；内存层是 `R/utils.R:2229-2245`（`StitchMatrix.dgCMatrix` → `RowMergeSparseMatrices`） |

**为什么有人踩有人没踩**：只有「各层 rownames 不一致」（合并不同基因集的数据集、不同参考版本、
过滤后 feature 不同）才进 C++ 那条路径；同 feature 的 split/join 走 `cbind`，
所以 split 自己数据的人碰不到，攒一堆 study 的人必踩。

## 2. 量级校验（用于判断「320 GB 都不够」是否合理）

| 项 | 估算 |
|---|---|
| 500k 细胞 counts 非零元 | 细胞数 × 2000~3000 ≈ **1~1.5e9**（单看 < 2³¹） |
| 单个合并后 dgCMatrix | nnz×12 B + 4 B×ncol ≈ **15~20 GB** |
| 峰值（走 C++ 路径） | 老层 + 新矩阵 + 每层 CSR/Eigen 拷贝 + triplet 列表（nnz×16 B） ≈ **60~100 GB** |

⇒ **320 GB 理论上装得下** ⇒ "内存不够"这个解释本身反常。最可能是：
报错被误当成内存问题（其实是溢出），或层数/细胞数被放大——**两两 `merge` 造成
重复细胞与超长层名**（issue #8208 里层名长到十几层后缀）、**多 assay**、
把 data+scale.data 一起并、feature 数 >4 万（这些都按层累加进同一个计数器）。
**先要报错原文再定性。**

## 3. 判错表（全量）

| 报错原文 | 真实含义 | 走哪条 |
|---|---|---|
| `Error: vector::reserve`（Linux）/ `Error: vector`（macOS） | int32 溢出 bug，**与内存无关**（#10009 / seurat-object#298） | 方案 B/C/D |
| `p[length(p)] cannot exceed 2^31-1`、`long vectors not supported yet` | 结果超 dgCMatrix 上限（#9763 / #9786） | 只能 D/E，加内存无效 |
| `sparse->dense coercion: allocating vector of size X GiB` + `cannot allocate vector of size Y Gb` | 被强制转稠密；或 `merge.default` 分发错误（把矩阵当对象传，#9125；识别标志 = traceback 出现 `merge.default`、`add.cell.ids` 被静默忽略） | A/B |
| 进程被 OOM killer 杀掉、无 R 报错 | 真的峰值不够 | A + C + D |
| 不报错但几小时不返回 | 层数太多 / 层名异常，在 C++ 里逐 feature 做哈希 | B/C |
| `Cannot merge matrices with different data type`（磁盘层） | 各层存储类型不一致（float vs double，同一脚本也可能产生，#9073） | `convert_matrix_type(layer, "double")` 后再 join |

## 4. 「修复了没有」三点核验（命令 + 实测结论）

```bash
# ① 开发分支源码是否仍有 bug
curl -s "https://raw.githubusercontent.com/satijalab/seurat-object/main/src/data_manipulation.cpp" \
  | grep -n -A6 -B2 "num_nZero"
# ② 修复 PR 状态
curl -s "https://api.github.com/repos/satijalab/seurat-object/pulls/320" \
  | python -c "import sys,json;d=json.load(sys.stdin);print(d['title'],d['state'],d['merged'],d.get('merged_at'),d['created_at'])"
# ③ 用户实际能装到的版本
curl -s "https://cran.r-project.org/web/packages/SeuratObject/index.html" | grep -oE "Version:</td>\s*<td>[0-9.]+"
curl -s "https://api.github.com/repos/satijalab/seurat-object/releases?per_page=3" \
  | python -c "import sys,json;[print(r['tag_name'],str(r['published_at'])[:10]) for r in json.load(sys.stdin)]"
```

**2026-10-24 实测**：
- ① `main` 第 79 行**仍是** `int num_nZero = 0;`；
- ② 修复 PR **#320 仍 `state=open, merged=False`**（draft，2026-09-01 建；它取代了 #295/#297/#298/#310，
  #298 已于 2026-09-01 因被取代而关闭——**关闭 ≠ 合并**）；
- ③ CRAN SeuratObject **5.4.0**（2026-04-11）；Seurat 最新 release v5.6.0（2026-10-03）；
  SeuratObject `NEWS.md` 的 `Unreleased` 段**未列**该修复。
⇒ **bug 在已发布版本里仍然活着，升级修不掉。**

## 5. 方案完整代码（详见 SKILL.md §方案；此处只记适用前提）

- **A** 只并 counts + assay 级调用：任何情况的安全起点；`data` 层用 `NormalizeData` 重算更便宜。
- **B** 手工 `cbind` 重建 counts：**前提 = 各层 rownames 一致 且 总非零元 < 2³¹**；
  必须先 `stopifnot(all(vapply(mats[-1], ... identical(rownames(m), rownames(mats[[1]])))))`
  （不一致时 cbind 会按位置拼基因，语义错），最后 `[, colnames(obj)]` 按对象细胞顺序重排。
  社区实证：2.6 秒完成（issue #8208 评论里的手工重建配方）。
- **C** v3 assay 回退 / 一次性 merge：根治分层；⛔ 不要两两 merge。
- **D** BPCells 磁盘层：`write_matrix_dir()` → `open_matrix_dir()` → 赋回 `obj[["RNA"]]$counts`；
  保存用 `SaveSeuratRds()`；回内存用 `as(layer, Class="dgCMatrix")`；
  ⭐ **关键**：磁盘层 join 走 `StitchMatrix.IterableMatrix`（不物化），天然绕开溢出 bug；
  层间类型不一致先 `convert_matrix_type()`。
- **E** sketch / subset 后 join（官方 1.3M、1M 细胞 vignette 路径）。
- **F** 装 draft PR #320：只让报错变明确，**>2³¹ 非零元的 dgCMatrix 仍造不出来**。

## 6. 交付口径（本轮被用户接受的形状）

1. **一句话结论**先给，并纠正前提（"这不是内存不够"）；
2. 机制配 **Mermaid + 源码文件:行号**（用户会追问依据）；
3. **判错表必给**（报错原文 → 含义 → 方案），它决定下一步动作；
4. 方案给**可直接粘贴的 R 代码** + 适用前提 + 实测证据；
5. 收尾**索要三样**：完整报错原文 / `sessionInfo()` + `packageVersion()` /
   诊断脚本输出（方案 0）——拿到即可给精确判决；
6. 参考来源逐条列可点链接。

## 7. 参考来源

- 源码：`SeuratObject/R/assay5.R:1059-1097`、`R/assay5.R:2870-2910`、`R/utils.R:1565-1593`、
  `R/utils.R:2218-2300`、`src/data_manipulation.cpp:12/79/83/93/98`
- Issue：[seurat#10009](https://github.com/satijalab/seurat/issues/10009)（vector::reserve，2025-07 起 open）·
  [seurat-object#298](https://github.com/satijalab/seurat-object/issues/298)（根因 + 修复，被 #320 取代）·
  [seurat-object PR #320](https://github.com/satijalab/seurat-object/pull/320)（draft，未合并）·
  [#9763](https://github.com/satijalab/seurat/issues/9763) · [#9786](https://github.com/satijalab/seurat/issues/9786) ·
  [#9125](https://github.com/satijalab/seurat/issues/9125) · [#9073](https://github.com/satijalab/seurat/issues/9073) ·
  [#8208](https://github.com/satijalab/seurat/issues/8208) · [#9713](https://github.com/satijalab/seurat/issues/9713) ·
  [#10406](https://github.com/satijalab/seurat/issues/10406)
- 文档：[Sketch-based analysis](https://satijalab.org/seurat/articles/seurat5_sketch_analysis.html) ·
  [Using BPCells with Seurat objects](https://satijalab.org/seurat/articles/seurat5_bpcells_interaction_vignette.html) ·
  [Essential commands](https://satijalab.org/seurat/articles/seurat5_essential_commands.html)