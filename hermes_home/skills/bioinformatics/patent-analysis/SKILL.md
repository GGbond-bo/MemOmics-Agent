---
name: patent-analysis
description: "生物信息学/方法类专利深度分析：竞品拆解、权利解读、规避策略、创新点空白识别"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [patent, patent-analysis, 专利分析, 竞品拆解, IP, intellectual-property]
    difficulty: advanced
    language: Python
    category: Literature
prerequisites:
  r_packages: []
  python_packages: [pymupdf]
---

# 专利深度分析

对生物信息学/方法类专利进行竞品拆解：阅读全文 → 提取技术路线 → 权利要求解读 → 识别创新空白 → 规避建议。

## When to Use

用户说"分析这篇专利""拆解这个专利""专利详细解读""解读专利""分析权利要求""竞品专利分析"等时触发。

## 触发级别

🟡 **讨论触发** — 用户提到专利分析时触发 skill_view。用户明确要求详细拆解时进入执行流程。

## 适用场景

- 正在准备自己的专利申请，需要了解竞品保护范围
- 需要确定某技术方案是否侵权
- 需要在现有专利中寻找创新空白
- 毕业/评职称需要专利产出

---

## 执行流程

### Step 1: 定位专利文件

用户通常提供 .caj 文件（CNKI知网格式）或专利号。

**CAJ 文件处理（重要）**：
- .caj 是 CNKI 专有二进制格式，**无法直接解析**（strings/zlib 提取均失败）
- **必须回退到 Google Patents 下载 PDF**：URL 模式 `https://patentimages.storage.googleapis.com/{hash}/CN{number}A.pdf`
- 优先从用户提供的 .caj 文件名提取专利号（如 `一种跨物种单细胞注释方法_阮航.caj`），然后搜索在线 PDF

**PDF 下载后**：
```python
import fitz  # PyMuPDF
doc = fitz.open(pdf_path)
for page in doc:
    text = page.get_text()
```

### Step 2: 结构化拆解（必须覆盖的 6 个模块）

每篇专利解读必须包含以下全部模块：

1. **基本信息卡**：专利号、申请人、申请日、状态（审中/已授权）、IPC分类
2. **背景与问题陈述**：它要解决什么痛点？它点名批评了哪些现有技术？
3. **核心方法逐步骤拆解**：用 Mermaid flowchart 画出 S1→S2→... 的技术路线
4. **权利要求逐条分析表**：每项权利要求 + 保护内容 + 独立/从属 + 对你的影响评级
5. **实验验证数据**：用了什么数据集？对比了什么方法？结论是否可信？
6. **与用户项目的交叉分析**：
   - ✅ 它没覆盖的（用户的创新空间）
   - ⚠️ 需要规避的方法要素 + 替代方案
   - 📋 必须引用的现有技术声明

### Step 3: 输出格式

- 交互框中展示完整结构化解读
- 同时保存为 Markdown 报告到 `results/{session_dir}/patents/{专利号}_analysis.md`
- 如果用户有多篇专利需要横向对比，追加对比总表（维度 × 专利矩阵）

---

## 专利解读质量标准（交付前自检）

- [ ] 基本信息卡完整（专利号/申请人/日期/状态/IPC）
- [ ] 技术路线图使用 Mermaid flowchart 呈现
- [ ] 权利要求 ≥80% 条目的解读（不只是前几条）
- [ ] 每项权利要求标注独立/从属 + 对用户项目的影响（🔴🟡🟢）
- [ ] 明确列出用户必须规避的方法要素 + 具体替代方案
- [ ] 如有实验验证数据，列出数据集和对比结果
- [ ] 保存 Markdown 文件到 results/

---

## ⚠️ 常见陷阱

| 陷阱 | 说明 |
|------|------|
| .caj 文件无法直接读取 | 不要花时间尝试解析 CAJ 二进制格式。直接用 Google Patents 下载 PDF |
| 只分析前几条权利要求 | 必须覆盖所有权利要求，从属权利要求中的细节往往是规避的关键 |
| 忽略"审中vs已授权"的区别 | 已授权专利的保护范围需更严格规避；审中专利的保护范围可能缩小 |
| 不区分独立/从属权利 | 独立权利要求保护范围最宽，从属权利可被绕开 |
| 用学术语言写商业专利 | 🔑 专利必须回答"企业为什么用？"而非"方法怎么算？"。企业不关心IRS公式，关心"能帮我省多少钱/避开哪个坑"。每个专利方案必须先写场景A（企业具体怎么用），再写技术细节 |
| 没有澄清"可代替性"的本体论 | 🔑 "可代替性"容易误解为器官替代而非研究结论转移。必须在说明书第一段精确定义：本方法评估的是"用动物模型做实验得到的结论能否预测人类结果"，而非器官或物种的物理替代 |
| 🔴 生成专利方案前未加载 skill | 用户说"专利方案"/"交底书"/"写专利"时，Agent 必须先 skill_view("patent-analysis") + skill_view("research-plan") 加载后再生成方案。本会话中 Agent 凭内生知识直接生成，用户主动追问"你触发 skill 了吗？"才暴露遗漏。漏掉的后果：独权不按公式、A25 防御不到位、专利检索三轮未执行、"可代替性"未精确定义。铁律：写专利方案前必须加载 patent-analysis + research-plan 两个 skill |
| 🔴 评估方案"真的可以吗"时不检索最新高影响论文 | 2026-08-04 评估跨物种 ATAC CRE 方案时，第1轮检索发现 Phan et al. Nat Genet 2025（PMID 40425826）已公开 TFBS shuffling + 跨物种 footprinting + IC 元件概念，直接部分占位"B类CRE检出"核心创新。专利数据库滞后，**最强现有技术往往是最新高影响论文（近2年 Nat Genet/Nature Methods/Science）**。评估新颖性/创造性前必须把"最新论文检索"加进第1轮，不能只看专利库；关键论文要下载全文逐页核实，不能只看摘要 |
| 🔴 只算细胞数不算个体数 | 混合效应模型类独权（如 species×age 交互）的实施例可行性看**个体数×年龄组数**，不看细胞总数。3 个 Arrow（1Old+2Young）无论细胞多少都支撑不了交互项 → 审查员按 A26.3 打"实施例无法证明技术效果"。用户说"数据有几十万细胞"时必追问：多少个体？多少年龄组？ |

---

## 🧬 生信方法专利授权铁律

### 能授权的共同模式（已验证：郭国骥/阮航/周展）

| 要素 | 为什么重要 | 缺少的后果 |
|------|-----------|------|
| 🔑 数学绑定到具体数据结构 | 审查员不保护数学公式，保护"公式+特定数据对象" | "加权求和"→A25驳回；"对ESM-2嵌入pseudobulk加权"→可能授权 |
| 🔑 有一个不可替代的"技术组件" | 这是创造性的唯一来源 | 所有子步骤都是已知方法 → A22.3驳回 |
| 🔑 有可量化的技术效果 | 证明解决产业问题 | "评估可代替性"太抽象；"IRS预测转化失败率精度78%"→具体 |
| 🔑 步骤锁定为计算机实现 | 防御A25"智力活动规则" | "降维"→驳回；"PCA取30PC后投UMAP"→技术方案 |

### 审查员三类驳回及防御

| 驳回 | 法律 | 话术模板 | 防御 |
|------|------|---------|------|
| 智力活动规则 | A25 | "全是数学统计方法的组合" | 强调具体技术手段(ESM-2嵌入/pseudobulk聚合/批次残差化)+产业效果 |
| 显而易见 | A22.3 | "D1+D2+D3+D4组合是显而易见的" | 证明组合产生单个步骤不具备的协同效果 |
| 不清楚 | A26.4 | "权重如何确定？可代替性的技术含义？" | 定义SDI公式,权重通过留一交叉验证网格搜索确定 |

### 专利检索三轮策略（防漏检）

| 轮次 | 范围 | 说明 |
|:---:|------|------|
| 1 | 具体技术圈 | 如"单细胞 跨物种 注释" |
| 2 | 抽象方法圈 | 去掉技术词，搜"跨物种 可代替性 评估" — 比第1轮更重要 |
| 3 | IPC分类号 | G16B 40/00, G16B 20/00 — 找关键词漏网的 |
| + | 软著库 | 国家版权保护中心 |
| 0 | **最新高影响论文（近2年）** | ⚠️ 最重要：专利库滞后，最强现有技术常是最新论文（Nat Genet/Nature Methods/Science）。2026-08 Phan 2025 Nat Genet 部分占位 B 类 CRE 概念即为例证。评估方案前先做这一轮，关键论文下载全文核实 |

### 权利要求撰写公式

```
独立权利要求 = [数据输入形式] + [不可替代技术组件] + [具体步骤(计算机实现)] + [可验证技术效果]

✅: "基于ESM-2蛋白质嵌入的跨物种scRNA可代替性评估方法：S1基因→ESM-2共享嵌入；S2 pseudobulk按个体聚合；S3拟合expression~species+age+species:age+(1|id)混合效应模型；S4计算SDI并分类..."

❌: "一种评估动物模型可代替性的方法，计算多个指标的加权和..."
```

---

## References

- `references/ruanhang-cn118298926a.md` — 阮航跨物种单细胞注释方法专利（CN118298926A）完整拆解
- `references/patent-comparison-matrix.md` — 5份跨物种单细胞方法专利横向对比
- `references/bioinfo-patent-drafting-guide.md` — 生信方法专利撰写指南：审查员驳回逻辑+权利要求公式+检索策略
- `references/cross-species-replaceability-methodology.md` — 跨物种脑组织可代替性 S200-S500 完整方法论（pseudobulk+Mixed Model+SDI+ABCD分类）
- `references/patent-architecture-a-plus-c.md` — A+C 双专利架构与同日提交策略（3个月受理时间线）
- `references/multi-llm-patent-evaluation.md` — 多LLM专利方案评审框架（Kimi K3 + DeepSeek + MemOmics 三方裁决模式）
- `references/atac-crecs-methodology.md` — 🔑 纯 ATAC-seq 跨物种 CRE 保守性评估三层框架（L1 序列→L2 可及性→L3 TF 结合→L4 CRECS）。用户说"只要 ATAC/不需要 RNA/纯 ATAC 专利"时启用。不需要 scRNA-seq，用 GeneScore 做细胞类型注释
- `references/atac-crecs-plan-evaluation-2026-08.md` — 🔴 跨物种 ATAC CRE 方案"真的可以吗"评估实录：Phan 2025 Nat Genet 现有技术警报、判定表、独权重心调整、数据功效核查（详见 cross-species-atac-conservation skill references/prior-art-2025-plan-evaluation.md）
