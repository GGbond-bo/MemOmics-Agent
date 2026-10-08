# 创造性答辩论据工具箱（A22.3 / A26.4 实战补强）

> 来源：跨物种衰老可替代性专利（纯 ATAC 跨物种 CRE 保守性评估）实审补强，2026-09-05。
> 四类可复用反驳技术，全部由真实数据复现验证，数字可审计。

## 1. A22.3 对比实验法：证明"现有方法不可用"而非"换写法"

审查员典型质疑："你的公式只是把已知方法换个写法，改进显而易见。"

反驳套路：**同一数据集、同一套效应量，让旧法与本方法正面 PK，量化旧法的漏检率/误杀率。**

实例（对称 min vs 主-参考非对称）：
- 旧对称 min `S = min(|Z₁|,|Z₂|)` 仅检出 **37** 个核心元件；
- 新主-参考非对称 `S = Z₁ × w(Z₂)` 检出 **336** 个 → 旧法**漏检 299 个 = 89%**。
- 关键：漏杀的 299 个全是"大样本侧可靠强效应 + 小样本侧方向可信但强度被小样本压低"的真实信号。旧法因小样本侧测不准（年龄标签 shuffle 富集仅 1.17、p≈0.267）却硬卡对称强度阈值，系统性误杀。

**结论措辞要落在"把不可用修复为可用的实质改进"，而非"换写法"。** 改名是商标不是发明；用对比实验把"换写法"驳成"唯一可用实现"。

## 2. "问题→方案→效果"闭环：把软肋翻成论据

单独任何一条数字都可能被挑软肋，必须绑定成完整闭环：

- **整体 ρ≈0（软肋当作"问题"）**：全体同向比例 0.4155 < 0.5、r≈−0.06 → 证明"整体不可替代"，必须**元件级分层**。软肋变成发明的前提。
- **元件级富集 12.5×（"效果"）**：某候选集里噪声期望命中 ≈ N×5%（期望 ≈26.9），实际命中 336 → 富集 12.5× → 证明分层后有真实、可量化、超随机的跨物种同向信号，而非"同源基因天然同向"的废话。
- 两者夹住中间"评分 + 方向门控 + 置换定阈值 + 分级输出"的方法，构成完整创造性争辩。

## 3. A26.4 "元件 vs 基因"口径统一：三阶映射表

独权动词对象是"元件"（CRE），实施例却输出"基因清单" → 审查员打 A26.4 不清楚。

解法：明确三单元映射，全文一致锚定，凡出现"元件/基因/tile"都锚回此表：

| 术语 | 定义 | 方法链位置 |
|---|---|---|
| 数据单元 = 候选调控元件（CRE） | 500bp 固定窗口 tile，或开放染色质峰（peak） | S1 输入、S3 评分原子对象 |
| 分析单元 = 元件年龄效应量 | tile 级 Pearson → `Z=sign(r)×Φ⁻¹(1−p/2)` | S2 逐元件计算 |
| 呈现单元 = 基因锚定的核心元件 | tile 锚定基因 ±2kb 内 Stouffer `Z_agg=ΣZᵢ/√n` 聚合 | S5 输出清单 |

"同源对应关系"统一声明两种方式之一：同源基因锚定 或 全基因组比对链（chain liftover），落到从属权要里，消除歧义。

## 4. News&Views → 原始研究 定位法（prior art 身份核实）

News & Views / 评论文章的作者 ≠ 它评述的原始研究作者。要精确引用，用 PubMed efetch XML 拿评论文章的 ReferenceList，找指向**同刊同期原始研究**的 Citation：

```bash
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=<评论PMID>&rettype=xml" \
  | grep -A6 "Reference\|ArticleTitle\|ELocationID"
# 在 <ReferenceList> 里找自然引用对象，识别其 DOI/PMID
```

实证案例（Nat Genet 2025;57(6)）：
- **评论**（News & Views）= de Mendoza A., "Genome synteny reveals hidden enhancer conservation", 1328-1329, PMID **40425825**, DOI 10.1038/s41588-025-02194-2。
- **原始研究** = Phan MHQ et al., "Conservation of regulatory elements with highly diverged sequences across large evolutionary distances", 1524-1534, PMID **40425826**, DOI 10.1038/s41588-025-02202-5（synteny-based "interspecies point projection"，小鼠/鸡胚胎心脏 ATAC，通讯 Daniel Ibrahim）。

教训：nei 之前记忆里"prior art 非 Phan 2025"是错的——Phan 2025 正是原始研究，de Mendoza 只是评论者。核实身份只看 PMID 所属文章类型（Comment/News vs Journal Article 原始研究），不能凭记忆。