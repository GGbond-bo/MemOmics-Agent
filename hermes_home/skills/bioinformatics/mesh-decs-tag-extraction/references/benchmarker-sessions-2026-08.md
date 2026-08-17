# Benchmarker 三轮试卷实测记录（2026-08-02）

三张试卷：TaskA（语义索引，5篇→MeSH主要标签）、TaskB（问答8题）、TaskC（MESINESP 多语言检索，4篇西班牙语文献→DeCS编码）。
原始文件位于 E:\benchmarker\exams\。

## TaskA（语义索引）— F1 = 69.0%
- 预测 44 标签，命中 40，错误 4；gold 72 标签
- Precision 90.9% / Recall 55.6% / F1 69.0%
- 命中全对（无错误标签）的文献：细菌生物发光（7/7 完美）
- **失败模式**：
  1. 只抓 MajorTopicYN="Y" → 系统性漏掉人口学限定词（Humans/Male/Female/Aged/Middle Aged），共 30+ 个占 gold 近一半
  2. 误用 Publication Type（Randomized Controlled Trial）当 MeSH 词
  3. 从摘要推断 Cohort Studies/Cardiovascular Diseases 等词，gold 中没有
- **修正**：efetch 全部 DescriptorName（含 MajorTopicYN=N 限定词）→ 剔除 PublicationType → 语义截断。预计 Recall 可到 80%+

## TaskB（问答）— 硬正确率 75%（加权 ~87.5%）
- 8 题：6 完全命中 + 2 部分命中（Q4 CAMUR ~70%、Q8 外泌体 ~80%）
- Q1 Qsymia = phentermine + topiramate ✅
- Q2 sonidegib BCC = yes ✅（SMO/hedgehog 通路）
- Q3 儿科脑肿瘤 R 包 = MethPed ✅
- Q4 CAMUR 在 TCGA = 部分（漏：等价分类模型 power set 迭代消除、内置知识库查询工具、3 类癌症验证细节）
- Q5 三联筛查 = AFP + beta-CG(hCG) + uE3 ✅（语义等价判定命中）
- Q6 TAD = transcription activation domain ✅
- Q7 lncRNA 功能 = 全覆盖 ✅
- Q8 外泌体 = 部分（漏：40-100nm 尺寸表述、多泡内体-质膜融合释放的生物发生机制）
- **失败模式**：summary 题只给功能列表，漏机制/方法细节/具体数字三层中的后两层

## TaskC（MESINESP 多语言检索）— 语义 F1 28.1% / 严格格式 0%
- 预测 29 标签，语义命中 9；gold 35 标签（4 篇：11/7/7/10）
- **最严重问题：格式完全错误** — 我给了 MeSH 树号（E04.928.760），gold 要求 DeCS 数字 ID（23039）
  - DeCS 数字 ID = BIREME 注册号，与 MeSH 树号不同体系
  - 若按题面 decsCodes 严格判分 = 0 分
- 语义命中 9 个：文献1=4/11、文献2=3/7、文献3=1/7、文献4=1/10
- **失败模式**（与 TaskA 同根因 + 新错误）：
  1. 再次系统性漏掉人口学限定词（Humanos 21034 / Femenino 21030 / Masculino 21044 / Anciano 20174 / Mediana Edad 9062）— TaskA 教训没复用
  2. 假设 DeCS 与 MeSH 树号通用 → 输出格式错误
  3. 从摘要推断主题词（Biopsia/Fiebre/Carcinoma Escamoso）vs 官方标引（Enfermedades del Ciego/Placa Hemolítica/Ictericia）差异巨大，6 个推断词全军覆没
- **修正**：从 BIREME/LILACS 官方记录拉完整 DeCS 标引 → 输出 decsCodes 数字 ID → 必含人口学限定词

## DeCS ID ↔ 名称映射（TaskC gold 全部 28 个唯一 ID，可复用）
- 20174=Anciano(Aged)、9562=Neoplasias(Neoplasms)、24375=Tomografía Computarizada por Rayos X、9062=Persona de Mediana Edad(Middle Aged)、14341=Neoplasias del Timo(Thymus Neoplasms)、8650=Mediastino(Mediastinum)、21034=Humanos(Humans)、21030=Femenino(Female)、21044=Masculino(Male)、23039=Toracotomía、238=Adenocarcinoma
- 52571=Leucemia-Linfoma Linfoblástico de Células Precursoras、24501=Dolor Abdominal、2466=Enfermedades del Ciego(Cecal Diseases)、23872=Leucemia(Leukemia)、38044=Enterocolitis Neutropénica
- 29563=Ciencia del Laboratorio Clínico、22359=Tipificación y Pruebas Cruzadas Sanguíneas、29197=Técnica de Placa Hemolítica、916=Anticuerpos(Antibodies)、6613=Hemólisis(Hemolysis)、7734=Ictericia(Jaundice)
- 4419=Quimioterapia Combinada(Drug Therapy, Combination)、6071=Glosectomía、13883=Cirugía General、22593=Neoplasias de Oído Nariz y Garganta、22700=Neoplasias de la Lengua(Tongue Neoplasms)、14449=Lengua(Tongue)

## 评分比对技巧
- 名称先归一：去重音（NFD）、去括号注释、小写、词序 token 匹配（重叠率 ≥0.75 判等价）
- 严格字符串匹配会误判（"Neoplasias de la Lengua" vs "Neoplasias de la Lengua (Tongue Neoplasms)"）
- DeCS 题先解析 gold 数字 ID（resource/?id= 页面）再语义比对，否则数字 vs 树号无法对齐
