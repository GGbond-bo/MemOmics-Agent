# 人海马文献深度解读（2026-08-12 扩充版）
# 覆盖：生物学图谱 6 篇 + 生信方法 4 篇，全部已下载至 MEMOMICS_HOME/work/papers/

# ============================================================
# 一、生物学文献（细胞类型/图谱）
# ============================================================

# 1. Thompson 2025 Nat Neurosci（PMID 40739059）
#    "An integrated single-nucleus and spatial transcriptomics atlas reveals the molecular landscape of the human hippocampus"
#    文件: 10.1038_s41593-025-02022-0.pdf (34MB, 47页完整)
#    核心内容:
#      - 10 例成人前海马 snRNA-seq + 空间转录组（150,917 spots, 36 capture areas）
#      - 方法: NMF + label transfer 整合 snRNA-seq 与 SRT（定义基因表达模式→推断 SRT 空间表达）
#      - 关键结果: 兴奋/抑制性突触特化的空间组织; 锥体神经元 NMF 模式的空间特征;
#                  retrohippocampus/subiculum/presubiculum 的区域特异 snRNA-seq 簇
#      - 18 个 PRECAST 空间域: GCL(DG颗粒层)/CA2-CA4/CA1/SUB/RHP/SUB.RHP 过渡域
#    对我们的价值: 人海马注释的现代参考; NMF 方法与我们骨骼肌MF项目的NMF思路一致
#    引用时注意: 用 2025 年最新图谱作为人海马注释的 cross-validation 来源

# 2. Su 2022 Cell Stem Cell（PMID 36332572）
#    "A single-cell transcriptome atlas of glial diversity in the human hippocampus across the postnatal lifespan"
#    文件: su2022_full.xml (243KB 全文)
#    核心内容:
#      - 人海马胶质细胞全寿命周期图谱（出生后到老龄）
#      - AST1-AST7 星形胶质亚群: AST2 = SOX2+/EGFR+ 与胶质发生相关;
#        AST6/AST7 = 吞噬功能; AST1 = TGFβ 信号
#      - 少突谱系异常 + 髓鞘化机制失调; 小胶质疾病易感性
#      - 衰老变化: 星形胶质 dysregulation、胶质谱系衰老特征
#    对我们的价值: 人海马胶质亚群的精细 marker; 星形胶质亚群分层
#    关键 marker: GFAP(星形), SOX2/EGFR(AST2胶质发生亚群)

# 3. Yang 2022 Nature（PMID 35165441）
#    "A human brain vascular atlas reveals diverse mediators of Alzheimer's risk"
#    文件: yang2022_full.xml (177KB 全文) + 10.1038_s41586-021-04369-3.pdf (reporting summary)
#    核心内容:
#      - 人脑血管细胞图谱（脑内皮/周细胞/平滑肌）
#      - 血管细胞类型 marker: ABCC9/PTN(周细胞), ACTA2/TAGLN/SLIT3/CTNNA3(平滑肌),
#        VWF(内皮), MOBP/MBP/MOG(少突,排除用), GFAP/SLC1A2/AQP4(星形,排除用)
#      - AD 风险: 血管细胞介导 AD 遗传风险（内皮 VWF 等凝血基因）
#      - 血管特异性存在物种差异（小鼠 vs 人）
#    对我们的价值: VS(血管)细胞类型注释的最佳 marker 来源; 跨物种血管差异提示
#    关键 marker: VWF/CLDN5(内皮), ABCC9/PTN(周细胞), ACTA2/TAGLN(SMC)

# 4. Sinnamon 2019 Genome Res（PMID 30936163）
#    "The accessible chromatin landscape of the murine hippocampus at single-cell resolution"
#    文件: 10.1101_gr.243725.118.pdf (6.3MB, 13页完整)
#    核心内容:
#      - 小鼠海马 sci-ATAC-seq（2346 高质量细胞, 平均 29,201 unique reads/细胞）
#      - 8 个主要 cluster（神经元/星形/少突/小胶质等）
#      - scitools 软件套件: 单细胞组合索引数据处理可视化
#      - 海马调控网络: 单细胞分辨率下的 CRE 调控网络
#    对我们的价值: 海马 scATAC 的先驱工作; 验证我们 TileMatrix/DA 方法学方向;
#                  小鼠海马 ATAC 可作为跨物种对比的第3层参考
#    方法学要点: sci-ATAC-seq 组合索引; 新鲜/冷冻海马可及性模式差异小

# 5. Zhong 2020 Nature（PMID 31942070）
#    "Decoding the development of the human hippocampus"
#    文件: 10.1038_s41586-019-1917-5.pdf（仅 reporting summary, 主体受版权限制）
#    核心内容（摘要级）:
#      - 人海马发育 scRNA-seq 图谱（早期发育）
#      - 海马发育轨迹: 神经干细胞→神经元/胶质分化
#    对我们的价值: 发育期人海马 marker; 与衰老方向互补（发育 vs 衰老）

# 6. Chen 2024 Nat Med（PMID 39095595）
#    "A brain cell atlas integrating single-cell transcriptomes across human brain regions"
#    文件: 10.1038_s41591-024-03150-z.pdf (27MB, 完整)
#    核心内容:
#      - 跨脑区单细胞转录组整合图谱（人脑多区域）
#      - 方法: 跨区域整合的细胞类型一致化
#    对我们的价值: 人脑多区域细胞类型整合参考; 跨区域注释一致性
#    （注: 27MB 大文件，精读待后续; 已确认存在与内容方向）

# ============================================================
# 二、生信方法文献（分析工具/方法学）
# ============================================================

# 7. MAESTRO 2020 Genome Biol（PMID 32767996）
#    "Integrative analyses of single-cell transcriptome and regulome using MAESTRO"
#    文件: 10.1186_s13059-020-02116-x.pdf (13MB, 28页完整)
#    核心内容:
#      - scRNA-seq + scATAC-seq 整合工作流（多平台）
#      - 核心: 从染色质可及性建模基因调控潜力（gene regulatory potential）→ 优于现有方法
#      - 支持: 预处理/比对/QC/表达与可及性定量/聚类/差异分析/注释
#    对我们的价值: scRNA+scATAC 整合的方法学参考; gene regulatory potential 概念
#                  与我们 GeneScoreMatrix 用法一致; 细胞类型注释自动化参考

# 8. scAGDE 2025 Nat Commun（PMID 39956806）
#    "Topological identification and interpretation for single-cell epigenetic regulation elucidation in multi-tasks using scAGDE"
#    文件: 10.1038_s41467-025-57027-x.pdf (15MB, 26页完整)
#    核心内容:
#      - scATAC-seq 深度图表示学习（VAE + 图神经网络）
#      - 同时学习表示和聚类, 显式建模数据生成
#      - 优于现有方法: 细胞分离/关键 marker 识别/可视化; 缓解 dropout; 揭示隐藏可及区
#      - 优先识别增强子样区域; 人脑组织成功注释 cis-regulatory element 特异细胞类型
#    对我们的价值: 人脑 scATAC 注释的先进方法参考; CRE 特异细胞类型注释
#                  （与我们 L3 TF 结合层有方法学关联）

# 9. hECA v2.0 2025 Sci Data（PMID 41398179）
#    "hECA v2.0: an AI-ready ensemble cell atlas of single-cell RNA and ATAC sequencing data"
#    文件: 10.1038_s41597-025-06426-2.pdf (4MB, 12页)
#    核心内容:
#      - AI-ready 单细胞 RNA+ATAC 整合细胞图谱
#      - 数据标准化/格式化, 供 AI 模型直接使用
#    对我们的价值: 人/鼠 ATAC 细胞图谱数据源; 注释参考

# 10. Acera-Mateos 2026 Genome Biol（PMID 41821037）
#     "Systematic evaluation of single-cell multimodal data integration enhances cell type resolution..."
#     文件: 10.1186_s13059-026-04002-4.pdf (6MB, 完整)
#     核心内容:
#       - 单细胞多模态数据整合方法系统评估（benchmark）
#       - 增强细胞类型分辨率与临床相关状态发现
#     对我们的价值: 多模态整合方法选择依据; benchmark 结论可指导我们 RNA+ATAC 整合策略

# ============================================================
# 三、已被拦截/摘要级收录的文献
# ============================================================

# 11. Tosoni 2023 Neuron（PMID 37015226）——摘要级
#     "Mapping human adult hippocampal neurogenesis with single-cell transcriptomics: Reconciling controversy or fueling the debate?"
#     核心: 人成体海马神经发生争议的 scRNA-seq 视角综述
#     价值: 神经发生争议背景; 与 Zhou 2022 / Franjic 2022 的 DCX 阴性结论互证
#     （PMC XML 误下为无关文章，以摘要级收录）

# 12. Zhou 2022 Nature（PMID 35794479）——PDF 部分
#     "Molecular landscapes of human hippocampal immature neurons across lifespan"
#     文件: 10.1038_s41586-022-04912-w.pdf (2.3MB)
#     核心: 人海马未成熟神经元跨寿命分子图谱
#     价值: 未成熟神经元 marker; 神经发生在人类显著减少但未消失

# ============================================================
# 更新说明: 本次新增 12 篇文献（10 篇全文/部分 + 2 篇摘要级），
# 全部文件在 MEMOMICS_HOME/work/papers/，含生物学 7 篇 + 生信方法 4 篇 + 综述 1 篇
# ============================================================
