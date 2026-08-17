# MetaboAnalyst 参数参考（metabolomics-full-pipeline 依据）

> 来源：MetaboAnalyst 5.0 官方文档（https://www.metaboanalyst.ca）+ 文献。
> 本 skill 的简化流程与 MetaboAnalyst 的对应关系：

| 本 skill 步骤 | MetaboAnalyst 对应功能 | 参数差异说明 |
|:----|:----|:----|
| QC 过滤 | Data Integrity Check (缺失率/CV) | MetaboAnalyst 默认缺失 20% 过滤；本 skill 默认 80% 保留(min_fraction=0.8) |
| 归一化 | Normalization (总峰面积/中位数) | 与 MetaboAnalyst "Normalization by sum" 一致 |
| 缺失值填充 | Missing value imputation | MetaboAnalyst 默认 1/2 最小值；本 skill 一致 |
| 差异分析 | t-test/ANOVA + FDR (BH) | 与 MetaboAnalyst 默认 BH-FDR 一致 |
| 富集 | MSEA / ORA | 本 skill 为简化 KEGG 映射，未实现 MSEA 全套 |
| 可视化 | Volcano plot / Heatmap | 本 skill 出 volcano.png + heatmap.png |

## 关键文献

1. Chong J, Wishart DS, Xia J. Using MetaboAnalyst 4.0 for Comprehensive and
   Integrative Metabolomics Data Analysis. Curr Protoc Bioinformatics. 2019.
2. Pang Z, Chong J, et al. MetaboAnalystR 3.0: Toward an Optimized Workflow for
   Global Metabolomics. Metabolites. 2020.

## 已知简化（诚实声明）

- 未实现 MSEA 代谢物集富集（需 SMPDB 数据库）→ 富集部分为 KEGG 简化映射
- 未实现 mummichog 通路推断（需通路拓扑）→ 后续版本补充
- 未实现 PLS-DA/OPLS-DA（分类模型）→ 差异分析只做单变量
