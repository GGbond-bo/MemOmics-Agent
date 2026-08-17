# ATAC-CRECS — 纯 ATAC-seq 跨物种 CRE 保守性评估方法

> 2026-07-28 · 基于本会话用户需求（「我不需要 RNA，我只要 ATAC」）开发的纯 ATAC 三层框架
> 与 `cross-species-replaceability-methodology.md`（RNA 版 S200-S500）互补

---

## 何时用这个框架

用户说「我只有 ATAC 数据」「不需要 RNA」「做纯 ATAC 的 CRE 保守性评估」「ATAC 算法专利」时启用。

---

## 与 RNA 版框架的本质区别

| 维度 | RNA 版（S200-S500） | ATAC 版（L1-L4） |
|------|-------------------|-----------------|
| 分析单元 | 基因 × 细胞类型 | 每个 CRE（调控元件） |
| 核心数据 | scRNA-seq UMI count | ATAC-seq Tn5 insertion |
| 细胞类型注释 | 直接有基因表达 → marker-based | GeneScore（基因活性代理） — 不需要 RNA |
| B 类定义 | 「表达保守但调控分歧」 | 「序列+可及性保守但 TF 结合分歧」 |
| 统计引擎 | pseudobulk + mixed model on expression | pseudobulk + mixed model on accessibility |
| 独权覆盖 | 基因级可代替性 | CRE 级保守性 |

---

## 三层框架

```
L1: 序列保守性层（不需要测序数据）
  ├─ liftOver 坐标映射（rheMac10 → hg38）
  ├─ phastCons/phyloP 保守性评分提取
  └─ JASPAR motif 扫描 + 跨物种比较
  输出: S_seq ∈ [0,1]

L2: CRE 可及性保守性层 ⬅️ 核心（用 ATAC 数据）
  ├─ peak 重叠率（Jaccard 指数）
  ├─ 信号强度 Spearman ρ
  ├─ 细胞类型特异性可及性一致性
  └─ 衰老动态 🔑: accessibility ~ species + age_scaled + species:age_scaled + (1|individual_id)
  输出: S_cre ∈ [0,1]

L3: TF 结合模式保守性层
  ├─ TF footprinting（TOBIAS / HINT-ATAC）
  ├─ motif 富集 — 衰老变化一致性
  └─ 结合强度跨物种比较
  输出: S_tf ∈ [0,1]

L4: CRECS 综合判定层
  ├─ CRECS = w₁×S_seq + w₂×S_cre + w₃×S_tf
  ├─ 权重通过进化锚点校准法（逻辑回归 + 黄金标准训练集）
  └─ A/B/C/D 四级分类:
      A: 全层保守 → ✅ 猴模型可用
      B: 序列+可及保守但 TF 结合分歧 🔑 核心创新
      C: 序列保守但可及分歧
      D: 序列分歧 → ❌ 排除
```

---

## B 类 CRE — ATAC 版的灵魂

纯序列工具（phastCons/GERP）只能看 L1 → 如果序列保守就给高分，**对 L2-L3 完全失明**。

B 类 CRE = L1 高 + L2 高 + L3 低：
- 序列完全保守（phastCons=0.95）
- 染色质可及性也保守（peak overlap 好，信号强度高）
- 但结合的是完全不同的 TF

→ 纯序列工具判 A 级「完全保守」
→ ATAC-CRECS 判 B 级「隐形炸弹」— 药企不能用猴模型研究这个 CRE

---

## 关键工具链

| 步骤 | 工具 | 环境 |
|------|------|------|
| ATAC 全流程（QC/降维/聚类/peak calling） | ArchR | R ≥ 4.5.0（Windows 双 R 环境） |
| 备选 ATAC 流程 | Signac | R 4.4.x |
| 序列保守性 | liftOver + phastCons bigWig | UCSC 工具 |
| motif 扫描 | FIMO (MEME suite) + JASPAR | 命令行 |
| TF footprinting | TOBIAS 或 HINT-ATAC | Python |
| 差异可及性 + mixed model | DESeq2/edgeR + lme4 | R |
| 权重训练 | 逻辑回归（scikit-learn） | Python |

---

## Windows 双 R 环境（重要技术细节）

ArchR 需要 R ≥ 4.5.0，但用户可能已有 R 4.4.x 用于 Seurat/Signac。

**解决方案**：
1. 安装 R 4.5+ 到独立目录（如 `C:\Program Files\R\R-4.6.1\`）
2. 安装时不添加到系统 PATH
3. ArchR 脚本显式调用：`"C:/Program Files/R/R-4.6.1/bin/Rscript.exe" archr_atac.R`
4. Seurat/Signac 脚本用默认 R：`Rscript seurat.R`
5. 跨环境通信通过磁盘文件（RDS/HDF5）

**⚠️ 用户偏好：不要默认装到 C 盘。先问用户要装哪个盘。**

---

## 细胞类型注释（无 RNA 的解决方案）

ArchR 和 Signac 都支持通过 **GeneScore（基因活性评分）** 注释细胞类型：
- 原理：基因 TSS 附近的染色质可及性 → 推断基因表达 → 和已知 marker 比较
- ArchR: `addGeneScoreMatrix()` → `addImputeWeights()` → marker-based annotation
- Signac: `GeneActivity()` → `NormalizeData()` → `ScaleData()` → marker-based annotation

**不需要真实的 RNA-seq 数据。**

---

## 验证设计

### 进化锚点（三层梯度）
| 物种对 | 进化距离 | 预期 CRECS |
|--------|---------|:---:|
| 人 vs 黑猩猩 | ~600 万年 | > 0.85 |
| 人 vs 恒河猴 | ~2500 万年 | 0.65-0.80 |
| 人 vs 小鼠 | ~9000 万年 | < 0.50 |

### 金标准 CRE
- 已知高度保守 CRE（如 SOX2 调控区）→ 应判 A 级
- 已知灵长类特异性 CRE（HARs）→ 应判 B/C/D 级
- 随机非 peak 区域 → 应集中于 D 级

---

## 独权撰写要点

按 `bioinfo-patent-drafting-guide.md` 公式：

```
独权 = [数据: 单细胞 ATAC-seq Tn5 插入计数矩阵]
     + [不可替代组件: L1 liftOver + L2 mixed model species×age + L3 footprinting 三层递进]
     + [具体步骤: S1→S2→S3→S4 锁定计算机实现]
     + [可验证效果: 输出 CRECS + A/B/C/D 分类]

从权 9: RNA-seq 增强层（你不做但留口子，防止别人绕开）
从权 10: Hi-C 增强层（同上）
```

---

## A25 防御（五锚点）

| 锚点 | 内容 |
|------|------|
| 数据绑定物理结构 | 「Tn5 转座酶插入位点计数矩阵」— 来自高通量测序仪的物理测量 |
| CRE 是分子实体 | 每个 CRE = 基因组具体坐标（如 chr17:12,345,678-12,346,000），可由 ChIP-qPCR 独立验证 |
| 计算机不可省略 | 「23 万细胞 × 10 万 CRE × mixed model → 人脑无法手动完成」 |
| 产业技术效果 | 「直接输出 B 类 CRE 清单，避免药物转化失败」（具体，非抽象） |
| 错误检测机制 | 「L2 含细胞类型对齐验证，失败时主动标记」 |

---

## 常见陷阱

| 陷阱 | 正确做法 |
|------|---------|
| 用户说「只有 ATAC」但 Agent 还在推荐 SCENIC/regulon | 立即停止。纯 ATAC 方案不包含任何 RNA 依赖工具 |
| 假设 Windows 不能跑 ArchR | ArchR 可通过双 R 环境在 Windows 运行。不要假设不可行 |
| 默认安装到 C 盘 | 先问用户安装路径偏好 |
| 专利方案生成前不加载 patent-analysis/research-plan skill | **必须加载**。本会话用户明确指出了这个遗漏 |
