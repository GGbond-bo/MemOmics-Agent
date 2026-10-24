# 远端 `.rds` 对象「身份核对」——不下载大文件，判断哪个对象对上用户描述

**场景**：用户在集群上有一堆多 GB 的 Seurat `.rds`，只给一段口头描述（「示例组织 snRNA、60 万细胞、
23 个注释、不是 ATAC」），要你确认**哪个文件是它**。
实测来源：2026-10-18 `/cluster/share/liuyuxuan3/Muscle/`（node1）。

## 三步：盘点 → 估选 → 读一次核对

### ① 盘点：一条 `run` 拿全候选（名字 + 大小 + 日期）
```bash
find <DIR> -maxdepth 2 -type f \( -name "*.rds" -o -name "*.RDS" -o -name "*.h5ad" \
     -o -name "*.csv" -o -name "*.tsv" -o -name "*.txt" \) \
  -printf "%10s  %TY-%Tm-%Td  %p\n" | sort -k3
echo "---- dirs ----"; ls -la <DIR>/<子目录A>/ <DIR>/<子目录B>/ 2>&1 | head -60
```
- 本集群 GNU findutils 支持 `-printf`（实测可用）。
- **先盘点再读**：拿到一个路径就 `readRDS` 是浪费（每个几分钟起步）。
- **把子目录 `ls` 拼进同一条命令**；拆成多轮 `run` 巡检会被判「循环失控」强制干预（见 SKILL 铁规 6）。

实测输出形态（Muscle 目录，23 个条目）：
```
Muscle_All.rds 7.6G | MF.rds 23.5G | Muscle_All_seRNA.rds 3.6G
scRNA_scATAC_integrated_harmony.rds 21.4G | ..._harmony2.rds 21.4G
MuSC.rds 0.7G | FAP.rds 1.8G | Immune.rds 0.8G | EC.rds 0.9G
Output/snATAC_cellColData_Level1.csv 124M | Output/snATAC_UMAP_coords_metadata.csv 23M
Merge/{Merge_MF 11.1G, Exer_MF 1.5G, FSHD_MF 1.1G, Merge_MuSC 2.1G, ...}
```

### ② 估选候选（算，不是猜）
稀疏表达矩阵 `dgCMatrix` 粗估：`nnz ≈ 细胞数 × 每细胞检出基因数`（snRNA ≈ 2000–3000），
存储 ~16 B/nnz（`i` int32 4B + `p` 4B + `x` double 8B），rds 再 gzip 压 2–3 倍。

| 文件大小 | 大致对应细胞数 | 实测锚点 |
|---|---|---|
| 7–12 GB | 50–70 万 | **604,244 细胞 → 7.07 GB**（本次） |
| 20–25 GB | 150–200 万 | `MF.rds` 23.5 GB（未读） |

⚠️ **文件名只作参考**：`Muscle_All` / `MF` / `seRNA` 都可能是"全量"，也可能一个是子集。
`Muscle_All.rds` 是"All"却也只 11 类；**以维度实测为准**。

### ③ 读一次、一直用：`session_start` → `session_exec`
```text
remote_cluster(action="session_start",
               input="/cluster/.../Muscle_All.rds",   # 大 rds 路径
               object="muscle_all",                    # 会话里的对象名
               env="R4.4.1_zb",
               rscript="/cluster/share/user/envs/R4.4.1_zb/bin/Rscript",
               title="...")
```
实测回报（关键行）：
```
load: seconds 225.2 | 已读入 … -> muscle_all（225.2 秒）
      维度/类型: 51227 x 604244  Seurat        <-- 细胞数就在这里
mem_note: 节点内存：总 3023GB / 可用 875GB；输入 7.07GB
```
- **7.07 GB / 225 秒**（R 4.4.1，node1）；会话 RSS 约 37 GB（3 TB 节点无压力，但仍应问用户要不要收）。
- 之后同会话 `session_exec` 复用内存对象，**不再回读文件**（`readrds_calls` 审计恒为 1）。

随后 `session_exec` 跑 `scripts/probe_rds_meta.R`：打维度 / assay / reductions / **每列元数据基数与取值**，
注释列及其类目数一眼可见。

## 本次实测结论（对照用户描述）
用户说：「整个 RNA 是 60 万细胞，但是有 23 个注释，不是 ATAC。」

`Muscle_All.rds`：
- `51227 基因 × 604244 细胞`、assay = `RNA`（✅ 不是 ATAC）、reductions `Xpca_ / Xpcaharmony_ / Xumap_`、meta 27 列
- `Annotation` = **10**（Adipocyte/RSS/MuSC/FAP/EC/TypeI/Myeloid/TypeII/Pericyte/Lymphocyte）
- `celltype` = **11**（+MastCell）；`Annotation_Level1` = **6**；`leiden_1` = **18** 簇（0–17）
- `samplename` = 48（24 人 × Pre/Post）、`library` = 96、`age` = 15、`type` = 6 组

→ **细胞数对上（60 万 ✅），但没有任何一列是 23 类**。交付时如实分列"匹配了什么 / 缺了什么"。

## 纪律（都是这次踩出来的）
1. **用户描述的元数据可能对不上 —— 如实报差异，别硬套**。不要把"600k"套上就宣布"找到了"；
   用户说的"23 个注释"可能指另一个对象（亚群 / 整合对象）或另一列。报完差异后**列出未读候选（附大小日期）
   让用户点**，而不是自己接着把 20+ GB 全读一遍。
2. **别全部读**：一次只读最可能的一个；剩下按体积/日期排序列给用户。
3. **轮次合并**：`locate` → 盘点 → `session_start` 是**不同动作**、不会判重复；
   但**连续同类 `run` 巡检**会被判循环失控（本次仍触发了强制干预）。盘点内容一次拼进同一条 `run`。
4. **会话别忘收**：核对完问一句要不要 `session_stop`（7 GB 对象 → RSS 37 GB）。
5. **连接瞬断先重试再下结论**：本次首轮三入口全 `timed out`/proxy-jump banner 超时 →
   用户说"再试试"后，`action="nodes"` + `action="locate"` 一次就全通了。
   → 抖动/跳板瞬断很常见，**不要**据此宣告"集群连不上、要你手动修"，**重试一次再报**。

## 交付骨架（用户满意的那一版）
1. 一句话结论（找到没找到、哪里不符）；
2. 对象卡片（维度 / assay / 降维 / meta 列数 / 样本分层）；
3. **注释列表格**（列名 → 类目数 → 取值）；
4. **未读候选表**（文件 / 大小 / 日期 / 猜测）；
5. 下一步二选一 + 明确问"点哪个"。