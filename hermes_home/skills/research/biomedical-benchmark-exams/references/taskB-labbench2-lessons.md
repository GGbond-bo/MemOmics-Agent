# Round 2-4 实测教训：TaskB 问答 + LABBench2 克隆

## TaskB — 问答（2026-08-02 实测，8 题）

### 成绩
- 完全命中 6/8（75%），加权 ~87.5%（Q4≈70%、Q8≈80% 部分命中）
- 8 题全部是医学/分子生物学事实型知识，检索验证了 Q1-Q4，Q5-Q8 为确定性事实未检索

### summary 题型丢分根因（最重要）
summary 题必须覆盖三层：**概念 + 机制/方法细节 + 具体数字/流程**。

| 题 | 我的答案 | gold 关键点 | 漏了什么 |
|----|---------|------------|---------|
| Q4 CAMUR in TCGA | 可解释多标签分类+规则归纳+发现亚型/标志物+知识生成 | 提取多个等价分类模型 + **基因幂集(power set)迭代消除** + 停止准则 + **ad-hoc 知识库与查询工具** + Breast/HN/Stomach 三类 TCGA 数据验证 | 方法机制细节（power set 迭代、内置知识库） |
| Q8 exosome | 30-150nm、细胞间通讯+转运货物+免疫调节+疾病传播+临床价值 | **40-100nm**、**多泡内体与质膜融合释放** + 含蛋白与 RNA + 介导通讯与免疫应答 | 生物发生机制（MVB-质膜融合） |

教训：评分时要检查"要点覆盖率"而不只看是否命中——功能列表对一半，机制/流程细节决定是否满分。

### 语义等价判定（list 题）
- Q5 triple test：我答 hCG，gold 是 beta-CG（beta-chorionic gonadotrophin）——**同一标志物**（检测的是 β 亚基），应判命中。比对时注意同物异名。

## LABBench2 — 克隆（2026-08-02 实测，10 题）

### 空模板密封答案 = 无法评分（必须如实报告）
`LABBench2_cloning_密封答案.json` 10 条全是：
```json
{"id": "...", "ideal": "", "answer_regex": "", "key_passage": "", "ground_truth": false}
```
- `ideal`（标准答案）/`answer_regex`（正则判分）/`key_passage`（关键段落）全空，`ground_truth` 全 false
- **验证方法**：同目录 `LABBench2_dbqa2_密封答案.json` 有真实内容（`ideal` 含具体答案、`ground_truth:true`）→ 证明不是格式/路径问题，是发布方漏填充
- 全盘搜索确认无其他 gold 文件（`*cloning*` 只有 2 个文件，`*gold*` 0 个）
- **结论：诚实报告"无法评分"，禁止编造分数**。任何"你对了 X 道"的说法都是编造。

### 附件序列文件缺失
- 试题 `files` 字段指向 `/cloning/*/` 的附件序列（.gb/.fa/.dna）本地不存在 → 用 Addgene（质粒公开结构）+ Ensembl/NCBI（转录本）在线补全
- 本机已有序列事实：PEG10-205 = ENST00000612748 (6579bp)、Sorcs2 mouse canonical = ENSMUST00000037370 (CDS 3480bp)、MYOD1 = NM_002478.5 (1803bp)

### 克隆设计通用要点（10 题设计覆盖）
- Gibson：骨架反向 PCR + DpnI 消化，同源臂 25-30bp；长片段（>4kb）分段 PCR
- Golden Gate：BsaI/BsmBI/Esp3I 4nt overhang 方向性串联，内部酶切位点需静默突变；串联荧光蛋白会 FRET 自淬灭
- Restriction-Ligation：双酶切 + T4 连接，插入:载体 3:1；pET-28b 用 NcoI 提供 ATG（CCATGG 覆盖起始密码子）
- 慢病毒/长片段用 Stbl3；高保真酶 Q5/Phusion；NEBcutter 检查内部位点

## MSYS /tmp 路径陷阱（验证脚本实测）
- bash 写临时脚本到 `/tmp/verify.py` → Windows 原生 Python（Python312）打开报找不到文件
- 根因：MSYS 虚拟路径 `/tmp` ≠ Windows 真实路径 `C:\...\AppData\Local\Temp` 或 `E:\tmp`
- 修复：临时脚本一律写 `C:\Users\<user>\AppData\Local\Temp\` 或 `E:\tmp\`，跑完删除
