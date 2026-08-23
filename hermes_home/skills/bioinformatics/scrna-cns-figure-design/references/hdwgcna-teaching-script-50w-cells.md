# hdWGCNA 教学脚本 + 50 万细胞规模化（2026-08-01 骨骼肌 MF 实测）

## 背景
用户要求："给我你跑hdWGCNA的脚本，在脚本，要求代码有间隔，让我知道每一步。并且对代码解释这些代码是什么，我要了解代码和用你的代码跑我50万的细胞。"

交付物：`results/memomics-2f229850/hdwgcna/hdwgcna_50w_teaching.R`（407 行，16 个【STEP】块，12 个断点，103 表达式，已通过 hermes-verify 13/13 + 锚点 `log/verify_teaching_status.txt`）。

## 用户脚本交付偏好（本会话明确表达，后续复用）
1. **代码有间隔**：每个逻辑步骤用 `# ---- STEP N. 名称 ----` 分隔，步间留白。
2. **每步解释**：每段代码前用中文注释讲清"这一步在做什么、为什么、关键参数含义、50万细胞时怎么调"。
3. **交付即教学**：用户要拿脚本去集群跑，所以脚本要能独立运行 + 有断点续跑说明 + 有内存/时间预算表。不要只给一个"能跑"的脚本，要"看得懂 + 改得动"的脚本。
4. 用户拿到脚本后会**自己读代码**并追问每一行的目的——脚本注释要写到"能被当教材用"的程度。

## 50 万细胞 hdWGCNA 参数映射（20K → 500K）
| 参数 | 20K 细胞 | 50 万细胞 | 原因 |
|------|---------|----------|------|
| target_metacells | 1500 | **3000-5000** | metacell 数量不足 = 假平坦（见下方教训） |
| k (metacell 内细胞数) | 25 | 25-50 | 细胞越多，k 可越大 |
| min_cells | 50 | 50-100 | 太少的亚群×条件组合跳过 |
| gene_select | fraction 0.05 | fraction 0.05 或 top_variable 8000 | 控制 TOM 计算量（与基因数平方相关） |
| soft_power | 自动 sp$Power[which.max(SFT.R.sq)] | 同左 | 永远数据驱动，不硬编码 |
| minModuleSize / mergeCutHeight | 50 / 0.2 | 50 / 0.2 | 官方默认即可 |

## 内存/时间预算（50 万细胞、5000 metacells）
| 阶段 | 时间 | 内存峰值 |
|------|------|---------|
| STEP 3 基因选择 | 5-10 min | 8-16 GB |
| STEP 4 Metacells | 30-60 min | 16-32 GB |
| STEP 7 软阈值 | 10-20 min | 16 GB |
| STEP 8 网络构建 (TOM) | 60-120 min | 16-32 GB（最重） |
| STEP 9-10 Eigengene+Connectivity | 20-40 min | 16-32 GB |
| STEP 11-15 下游+出图+富集 | 20-40 min | 8-16 GB |
| **总计** | **2.5-5 小时** | R 需 64 位，≥32 GB（50 万 ≥64 GB 更稳） |

**必须后台跑 + 断点续跑**：每个 STEP 结束 saveRDS `stepN_obj.rds`；断点续跑 = readRDS 后从 N+1 步继续。教学脚本内置 9 个断点。

## 教学脚本结构（16 步）
STEP 0 加载包+配置 / STEP 1 路径配置 / STEP 2 加载数据+NormalizeData / STEP 3 SetupForWGCNA（基因选择）/ STEP 4 MetacellsByGroups（50万核心，聚合 metacells）/ STEP 5 Normalize+Scale metacells / STEP 6 SetDatExpr（提取 datExpr）/ STEP 7 TestSoftPowers（软阈值，关键参数）/ STEP 8 ConstructNetwork（最耗时，TOM）/ STEP 9 ModuleEigengenes（模块活性）/ STEP 10 ModuleConnectivity（kME/hub 基因）/ STEP 11 模块×五效应关联（核心产出）/ STEP 12 模块 UMAP / STEP 13 Hub 基因+网络图 / STEP 14 GO/KEGG 富集 / STEP 15 保存+收尾。

## ⚠️ 50 万细胞特别警告
1. **假平坦教训**：早期在 1500 metacells + 旧 datExpr 上跑出 R²=0.72、单模块，误判"MF 网络平坦"；官方 v0.4.12 + 6524 metacells → R²=0.98 @ power=10、11 模块。**网络"平坦"先查 metacell 数量，再谈生物学**。
2. **R 脚本别放 /tmp**：MSYS 虚拟路径下 Rscript 读脚本 segfault（exit 139）。脚本写 ASCII 工作目录，`Rscript --vanilla ./script.R` 从工作目录跑（--vanilla 也绕过被污染的 .Rprofile 库路径）。
3. **enrichR 联网卡死**：`library(hdWGCNA)` 在 maayanlab.cloud 不可达时挂起。用 `loadNamespace("hdWGCNA")` + `hdWGCNA::` 前缀。
4. **统计**：metacell 级相关（n≈6500）功效过剩、p 几乎全显著。正式投稿必须按个体聚合（n=24）再检验，教学脚本 STEP 11 注释里已内置该警告。
5. **集群注意**：50 万细胞 h5ad/rds 读取需几分钟，R 内存 ≥64 GB；MetacellsByGroups 与 ConstructNetwork 两处最容易 OOM，分步跑 + 断点续跑。

## 辩论/结论/自进化 审计（用户 4 问）
用户审计模式："你这些参数辩证了吗？结论产生了吗？进行多agent辩论了吗？自进化了吗？"
- **参数辩证**：soft_power 等关键参数应由数据驱动（TestSoftPowers 自动选择），并走 debate_analysis 多角色辩论。本会话 debate_analysis 服务连续 6 次 LLM API 故障失败 → 用结构化 pro/con 替代并如实标注，不静默跳过。
- **结论产生**：交付必须"结论先行"（一句话生物学结论），不能只给文件清单。
- **多 agent 辩论**：debate 失败时给 pro/con 结构化裁决 + 置信度，并注明"正式裁决待服务恢复后补"。
- **自进化**：跑通后必须 record_run（本会话 hdWGCNA 4 次 record_run 全部落库）+ 失败记录 record_error（早期假平坦错误已记录并在新 reference 中更正）。
