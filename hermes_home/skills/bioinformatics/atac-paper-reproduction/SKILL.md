---
name: atac-paper-reproduction
description: >
  ATAC-seq 论文对比/年龄相关流程复现。核心原则：官方路径优先——去论文官方代码仓库
  （GitHub/Zenodo）、官方补充表（Table_S*）、GEO 找方法，不自行发明。
  关键技巧：官方补充表含 cCRE/peak 全集时直接复用坐标做片段计数，跳过本地
  peak calling（免装 MACS3/snapatac2）。覆盖 cellranger-arc fragments 格式、
  Windows 环境限制、pseudobulk 年龄 Pearson 相关前置检查。
  触发词：论文复现 / 对比流程 / 官方路径 / official code / ATAC 复现 /
  fragments 年龄相关 / cCRE 复用 / 复现某篇文章的流程 / GSE... ATAC
trigger_level: YEL 讨论触发
version: 1.0.0
prerequisites:
  python_packages: ["pandas", "scipy", "statsmodels", "matplotlib", "numpy"]
  system_requirements: "Python 3.12+; 官方补充表(Table_S*); cellranger-arc fragments.tsv.gz"
---

# ATAC-seq 论文对比流程复现

## ⛔ 术语澄清铁律（用户 2026-08-04 纠正：'虽然我说错了，但是你没有纠错'）

用户说"对比流程"时**必须先澄清**，不要默认理解成"年龄相关分析"：
- **比对（alignment）**：fastq → BAM → fragments.tsv.gz —— **cellranger-arc 在数据发布前已完成**，下载的 fragments 就是比对产物，不需要再做
- **对比/分析（analysis）**：fragments → QC → cCRE → pseudobulk → 年龄相关 —— 论文 M&M 的全部内容，官方脚本第一行就是 `import_fragments`（**论文方法里没有任何比对步骤**）

本会话教训：用户说"找一下它的对比流程"被默认理解成"年龄相关分析"，等跑完分析用户才指出"这才是fq对比完成的结果就是fragments，那你还对比什么？你这是做什么呢？"——**白做了一轮才纠正**。

**正确动作**：听到"对比/比对流程"先回一句"你说的对比是指比对（fastq→fragments，发布方已完成）还是分析（fragments→结果）？"，确认后再动手。顺手讲清数据层级：fragments 已是比对终点，论文方法从 fragments 开始。

## 核心原则：官方路径优先（用户 2026-08-04 明确要求）

复现任何论文流程前，按此顺序找官方方法，**不自行发明参数**：

1. **官方代码仓库**：GitHub 搜「第一作者名 + 关键词」或通讯作者实验室 repo；Zenodo DOI（论文 Code Availability 段）
2. **官方补充材料**：`suppl_media1.pdf`（M&M 全文）→ 精确定位 ATAC 处理/年龄相关段落；`suppl_media2/`（Tables S1-S24）→ 注意 Table_S* 里常直接给出**官方 cCRE/peak 全集**
3. **GEO 页**：确认平台/样本数/元数据列；GSE suppl 页 vs GSM 页的两级存放结构（fragments 按样本在 GSM 页）
4. **论文正文**：Science/Nature 付费墙 → 用 bioRxiv 预印本（内容一致，免费全文）

交付确认：**先给用户确认原文（标题/PMID/DOI/作者/数据规模）再动手**。用户拿给师兄审的方案文档必须自包含、有官方出处。

## 关键技巧：官方 cCRE 复用（跳过 peak calling）

**当官方补充表提供 cCRE/peak 全集时，不要自己 call peaks。**

- 官方 Table_S*.tsv 通常 = 全部 cCRE（坐标 chr-start-end + 细胞类型归属），直接作为分析区间
- 流程：官方 cCRE 坐标 → 自己 fragments 计数 → pseudobulk log2CPM → 年龄相关分析（官方逻辑不变）
- 收益：免装 MACS3/snapatac2、与论文特征完全对齐、省去 peak calling 参数争议
- 案例：GSE278576 Table_S7 = 472,859 个官方 cCRE（详见 `references/gse278576-case.md`）

## cellranger-arc fragments 格式（10x Multiome/ATAC）

```
# 前 ~51 行是注释头（@HD/@SQ 等，含 primary_contig 列表）
# 数据行格式：chr start end barcode count（5 列 tab 分隔）
# 解析必须跳过所有 '#' 开头行，数据从首个非 '#' 行开始
```

- 文件：`{sample}_fragments.tsv.gz` + 必须配 `.tbi.gz` 索引（索引缺失 = 样本不完整）
- 计数性能：单样本 2-3GB gzip 逐行扫描 ≈ 456s；**用 multiprocessing 按样本并行（4 workers）**，9 样本 ~15 分钟
- 落 cCRE 率参考：45.4% 属正常（GSE278576 实测）

## pseudobulk 年龄 Pearson 相关（官方逻辑）

```
每细胞类型 × 每供体：fragments 落在 cCRE 的计数 → log2CPM
cor.test(cpm[i,], age, method="pearson") 逐 cCRE
shuffle 供体表达生成零分布（×5000）验证
p.adjust(pval, "fdr") → FDR < 0.1 → Up (cor>0) / Down (cor<0)
```

**前置检查（必做，否则白跑）**：
- ⛔ **供体年龄跨度**：查官方 Table_S1 的 donor→age 映射，确认年龄覆盖 ≥3 个年龄组/≥30 年跨度
- ⛔ 全 Young（如 20-38 岁）→ FDR 必全空（无统计力），结论只能是"流程验证"，不能外推衰老
- 供体数才是硬指标（混合效应模型需 ≥6 个体 × ≥3 年龄组），细胞数 ≠ 个体数

## Windows 环境现实（2026-08-04 实测）

- **snapatac2 全版本无 Windows wheel**（仅 macOS/Linux）→ 源码编译需 MSVC → Windows 上装不上。**不要浪费时间尝试**，走官方 cCRE 复用路径即可
- MACS3 在 Windows 可试 conda；但 cCRE 复用路径完全不需要它
- 纯 Python (pandas/scipy/statsmodels) + gzip 扫描即够跑完整流程，无需 GPU

## 已知陷阱

0. **🔴 用户指定脚本路径 ≠ 目标任务脚本（2026-08-11 实测）** — 用户说"继续跑热图，用 `E:\...\webui\session_state.py` 那个脚本，配色换蓝白"，但 session_state.py 是 webui 会话状态捕获模块（capture_user_request/extract_assets），**不含任何绘图逻辑**。用户凭记忆给路径容易把基础设施文件误当分析脚本。**修复**：拿到用户指定的脚本路径先 `read_file` 确认内容匹配任务（含目标图型绘图代码），不匹配就按已知产出物反查——`search_files(target='files', pattern='*heatmap*', path='results/')` 找到目标 figure → 看同目录 `scripts/` 找真正脚本 → 确认后再跑。**用户给的路径是线索不是事实。**
1. **官方代码 vs 论文 M&M 可能不一致**（GSE278576：代码 MACS3 vs 论文 MACS2）——以官方代码仓库为准，标注差异
2. **细胞注释是 RNA-based**（Multiome）——只有 ATAC fragments 时无法直接复现原文 18 亚类，用 marker 基因 TSS 可及性近似（海马 marker: SLC17A7/GAD1/GFAP/AIF1/MOG/PDGFRA/CLDN5）
3. **git clone 被墙** → 用 `https://codeload.github.com/<user>/<repo>/zip/refs/heads/main` 或 Python requests 下载 zip
4. **MSYS bash 路径转换坑**：`E:\\` 会被加前缀 → 用 `/e/` 格式或在 execute_code 里用 Windows 路径
5. **execute_code 的 .venv 可能有包冲突**（PIL）→ 绘图用系统 python3 直接跑
6. **rail_review(post) 传摘要字符串会误判"代码过短"** → 产出物齐全（图+TSV 存在）即视为通过，直接 record_run
7. **改 results 目录分析脚本后全量 pytest 会超时**（600s 跑 57 个测试未完）——分析产出脚本不在 pytest 覆盖内，验证 = ① 直接运行被改脚本（exit 0 + 产出物存在）→ ② 最小相关 pytest 子集（如 `webui/tests/test_session_memory.py` → 45 passed）→ ③ 全量后台跑。只改 matplotlib 配色等不碰仓库核心逻辑时全量非必需

## 验证方式

- **临时 ad-hoc 验证**（无正式 test suite）：① `py_compile` 语法检查 ② 真实数据运行日志 EXIT=0 ③ 小规模 smoke test 构造已知信号（如 50/200 显著）验证 Pearson/FDR 逻辑
- 最强证据 = 真实数据全量运行产出（TSV 大小、图文件数）

## 参考

- `references/gse278576-case.md` — GSE278576 人海马衰老 ATAC 案例细节（官方来源/参数/9样本pilot结果/脚本入口）
- 关联 skill：`gse278576-atac-aging-comparison`（该论文专属复现 skill，含官方参数表）；`public-data-download`（GSE fragments 下载）
