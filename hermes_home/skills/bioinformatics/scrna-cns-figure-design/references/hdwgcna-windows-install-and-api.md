# hdWGCNA Windows 安装 + release v0.4.12 API 实战记录

> 2026-08-01 人骨骼肌 MF 20K 细胞（10 亚群 × 2000，6 条件 Y/O/OD × Pre/Post）实测。
> **本记录推翻了 `hdwgcna-mf-validated-negative-result.md` 的旧结论**（旧结论说 MF 数据 hdWGCNA R²=0.719 单模块不可用——那是 dev 分支 bug + 过期 datExpr 的产物）。

## 1. 实测结果：hdWGCNA 在 MF 数据完全可用

| 指标 | 值 |
|------|-----|
| metacells | 6482（10 亚群 × 6 条件 × 25 聚合，MetacellsByGroups k=25, target=1500） |
| 基因 | 10176（SetupForWGCNA gene_select="fraction", fraction=0.05） |
| **软阈值** | **power=10, R²=0.98**（标准 scale-free） |
| 模块 | **9 个有义模块** + grey 6281 未分配 |
| marker→模块验证 | red=快肌(8/9 marker)、brown=慢肌(10/10)、blue=RP_high(8/8)、green=OTUD1+系、turquoise=RSS(5/6) |

**效应故事（module-trait correlation, 模块×5效应）：**
- **black 模块**（185 基因, 血管/能量代谢）: Aging=−0.51, T2D=−0.25, ExYoung=+0.27, **ExOld=−0.23** → 衰老强下调、年轻运动恢复、**老年运动反而继续下调** = "运动逆转靶点"
- **magenta 模块**（55 基因, ECM/信号）: Aging=+0.39, T2D=+0.29, ExYoung=−0.20, **ExT2D=+0.11** → 衰老糖尿病点燃、年轻运动压制、**糖尿病+运动仍上调** = "不可逆损伤"
- blue 模块（氧化磷酸化）: Aging=−0.26/ExYoung=+0.12；green 模块（OTUD1+系, 肌细胞分化）: Aging=+0.26/ExOld=+0.21

**方法论教训**：网络"平坦性"判断必须在 metacell 聚合后做。单细胞层面直接看相关性或跑 dev 分支 bug 管道得到的"全基因一个模块"是 pipeline 状态问题，不是生物学属性。

## 2. Windows 安装（release v0.4.12，不要用 dev 分支）

dev 分支 API 与 release 不一致（MetacellsByGroups 不存 wgcna_name、函数签名漂移），**不要修 dev 的坑，直接换 release**。

```bash
# 下载 release v0.4.12 tarball（~204MB 含文档数据）
curl -k -sL -o hdwgcn_release.tar.gz "https://codeload.github.com/smorabit/hdWGCNA/tar.gz/refs/tags/v0.4.12"
mkdir -p /e/MemOmics-Agent/hdwgcn_src
tar -xzf hdwgcn_release.tar.gz -C /e/MemOmics-Agent/hdwgcn_src/
```

```r
# 依赖: Seurat, WGCNA, UCell, GeneOverlap, tester, Biobase 等
# 装 UCell/GeneOverlap 用 codeload 源码包（BiocManager 版本映射可能故障）:
#   https://codeload.github.com/carmonalab/UCell/tar.gz/refs/heads/master
# tester 是硬依赖但在运行中实际用 tester::is_numeric_dataframe —— 若装不上可造 fake 包
install.packages("E:/MemOmics-Agent/hdwgcn_src/hdWGCNA-0.4.12", repos=NULL, type="source")
```

## 3. 两套 R 库路径（本机反复踩坑）

- **execute_r 工具** → `C:/Users/23136/AppData/Local/R/R-4.4.2/library`
- **terminal Rscript** → `C:/Users/23136/R/R-4.4.2-library`（还有 R-4.5.3-library, R-4.6.1-library）

装包前先 `execute_r` 里 `.libPaths()` 确认目标；跨环境同步用 `cp -r <src>/<pkg> <dst>/` 比重装快。
`/tmp`（MSYS）路径 execute_r 的 R 看不到——解压到 Windows 路径再 install。

## 4. release v0.4.12 API 关键差异（与旧 skill 函数名不同）

| 旧写法（过时） | release 0.4.12 正确写法 |
|---|---|
| SetUpWGCNA | `SetupForWGCNA(obj, gene_select="fraction", fraction=0.05, wgcna_name="MF_wgcna")` |
| FindWGCNAModules | `ConstructNetwork(obj, tom_outdir="data/TOM", networkType="signed", soft_power=10, minModuleSize=50, mergeCutHeight=0.25, wgcna_name="MF_wgcna")` |
| CorrelateModules | 自写 `cor(ME, trait_design)` + `cor.test`（见下） |

### 必踩坑列表

1. **MetacellsByGroups** 需要 `ident.group` 是 group.by 之一：
   `MetacellsByGroups(obj, group.by=c("annotation_L3","type"), ident.group="annotation_L3", k=25, target_metacells=1500, wgcna_name="MF_wgcna")`
2. **SetDatExpr** 的 `group_name` 传**具体值的向量**全选（不要传列名，不要用 multi_group_name=NULL——`%in% NULL` 返回空）：
   `SetDatExpr(obj, group_name=all_grps, group.by="annotation_L3", assay="RNA", layer="data", wgcna_name="MF_wgcna")`
3. metacell 对象可能只有 counts 层 → 先 `NormalizeData(GetMetacellObject(obj, wgcna_name=...))`
4. **ModuleEigengenes(group.by.vars=...) 检查的是主对象 @commands 的 ScaleData 记录**（不是 metacell）：
   先 `obj <- ScaleData(obj, features=GetWGCNAGenes(obj, wgcna_name="MF_wgcna"))`
5. **模块在 `obj@misc$<wg>$wgcna_modules`**，用 `GetModules(obj, wgcna_name=...)` 读取；极简提取时 `readRDS` 后 `wg$wgcna_modules`（列: gene_name, module, color）
6. `TestSoftPowers` 的结果可能不存进对象 → `ConstructNetwork` 显式传 `soft_power` 参数
7. **enrichR 联网检查**：hdWGCNA `library()` 会触发 enrichR .onAttach curl 超时——纯读结果时不要加载 hdWGCNA，base R `readRDS` 即可
8. TOM 计算 >900s → **`terminal(background=true)` + `Rscript script.R > log 2>&1`**，notify_on_complete；`data/TOM/*.rda` 是中间产物可续跑（blockwiseModules 第一阶段 TOM 完成、第二阶段模块切割被杀后可续）

## 5. 模块-性状关联（自写，释放核心价值）

```r
# me = GetMEs(obj, wgcna_name)  # 返回主对象细胞数（如 20000）的模块 eigengene！
# trait: 5 效应 dummy (Aging/T2D/ExYoung/ExOld/ExT2D) 对齐主对象 meta
effect_design <- function(d) {
  m <- matrix(0, nrow=nrow(d), ncol=5)
  colnames(m) <- c("Aging","T2D","ExYoung","ExOld","ExT2D")
  m[,1] <- ifelse(d$type %in% c("O_Pre","O_Post","OD_Pre","OD_Post"), 1, 0)
  m[,2] <- ifelse(d$type %in% c("OD_Pre","OD_Post"), 1, 0)
  m[,3] <- ifelse(d$type=="Y_Post", 1, 0)
  m[,4] <- ifelse(d$type=="O_Post", 1, 0)
  m[,5] <- ifelse(d$type=="OD_Post", 1, 0)
  rownames(m) <- rownames(d); as.data.frame(m)
}
trait_mat <- effect_design(obj@meta.data)
me_df <- me[rownames(trait_mat), , drop=FALSE]
me_df <- me_df[, !grepl("^MEgrey$", colnames(me_df)), drop=FALSE]
mod_trait_cor <- cor(me_df, trait_mat, method="pearson", use="pairwise.complete.obs")
# p 值循环 cor.test，跳过 sd==0 列（isTRUE 包装），pheatmap 设 cluster_rows/cols=FALSE 防 NA 聚类报错
```

**注意**：`GetMEs` 返回的是**主对象细胞数**（如 20000）的 eigengene，不是 metacell 数——trait 设计矩阵必须对齐主对象 meta，否则全 NA（本次踩坑）。

## 6. 与 NMF 的定位（用户反馈驱动）

- NMF（pooled）找**身份程序**——对"条件效应"问题用户说"没感觉"
- hdWGCNA 的 module-trait correlation **内置效应关联**——直接回答"哪个模块响应哪个效应"，用户认可
- 两者都保留：NMF 程序×条件箱线图 + hdWGCNA 模块×效应热图，Jaccard 重叠 = 多方法验证叙事
