# MemOmics Agent — 项目上下文

## 项目路径
- 项目根目录：MEMOMICS_HOME/
- Hermes 框架：MEMOMICS_HOME/hermes-agent/
- 知识库：MEMOMICS_HOME/memomics/knowledge_base/ (90个YAML)
- 技能库：~/.hermes/skills/bioinformatics/ (241个SKILL.md)
- 分析结果：MEMOMICS_HOME/hermes-agent/results/

## 数据库
- 用户数据：D:/我的下载/Migule_lai_24 _new.h5ad (人类骨骼肌 scRNA-seq, 324,434 cells, 已注释)
- 物种：Homo sapiens
- 组织：骨骼肌 (skeletal muscle)
- 方向：衰老 (aging) — 年轻 vs 老年

## 环境
- Python: <auto-detected>
- R: Rscript (4.4.x, Seurat v5.5.0, CellChat, monocle3 等)
- 模型: deepseek-v4-pro (DCS Cloud)
- 包管理: BiocManager (R), pip (Python)

## 默认分析参数
- 细胞数：默认 subset 60,000
- QC 过滤：nFeature 200-6000, MT% < 15%
- 标准化：SCTransform v2, conserve.memory=TRUE
- 批次校正：Harmony
- 降维：PCA 50PCs → UMAP 30 dims
- 聚类：Leiden, resolution=0.5
- 注释：SingleR + FindAllMarkers

## 工作流约定
1. 分析前先 scan_data 扫描数据
2. 分析前先 search_knowledge 搜索知识库
3. 分析结果按 results/<模块>/<方法>/{figures,results,scripts,data} 存储
4. 每个子分析执行前后铁轨审查
5. 待办完成后标记 completed
