# 论断 → 引用匹配（claim-to-citation）与支撑分级

**触发**：用户给一句/一段论断说「给这个结论找引用 / 看看能引哪几篇 / 这句话有没有文献支持」；
或审稿要求补引用；或自己写完结论要先自证有据。

**核心原则：先拆子论断，再逐条配文献并分级；没有摘要级证据的部分必须明说缺口，不许用"相关标题"凑数。**

---

## 1. 五步流程

1. **拆句**：把原句拆成 **2-4 个可独立引用的子论断**（一句话常含两个机制断言，证据强度往往不同）。
   例：「卫星细胞衰老中自我更新能力下降、不对称分裂增加」→ A=自我更新下降 / B=不对称分裂增加。
2. **转英文检索式**：每个子论断 2-4 条（精确词 / 同义词 / 广背景 / 方法或模型词）。
3. **检索**：`search_papers`（发现用）+ `query_ncbi(db='pubmed')`（精确标题/作者直查，防漏检）。
4. **摘要级核实与分级**（必须，见 §2、§3）：候选一律拉到摘要原文再定级。
5. **交付**：句 → 文献 → 支撑等级 → 建议插入位置；末尾附**缺口段**（哪半句无直接证据 / 只有综述 / 只有小鼠）。

## 2. 支撑分级口径（保守）

| 等级 | 判据 |
|---|---|
| strong | 原始实验论文，直接测同一关系/机制，结果支持该子论断 |
| partial | 支持子论断的一部分、相关模型，或更窄的条件 |
| background | 只支撑领域背景，不支撑具体断言 |
| limiting | 与断言冲突或收窄其适用范围 |
| metadata-only | 只有标题/元数据相关，**未核摘要** ⇒ 不得当作支撑引用 |

- **综述只作 context 引用**：不得用综述替原始实验证据（如用 Feige 2018 Cell Stem Cell 说明"衰老影响分裂模式"，需标注 review）。
- **断言强于证据时改写措辞**，而不是硬找文献。例：把"不对称分裂增加"改为"分裂模式向不对称偏移、对称性自我更新扩增减少"，或指明需回原文图核对页码。

## 3. 摘要批量取回（一次脚本搞定，别逐个查）

`search_papers` / `query_ncbi` **都不回传摘要**（只有标题/期刊/年/DOI/PMID）⇒ 摘要锚定必须显式走 Europe PMC REST。
**把"已知候选 PMID 列表"一次性批量取回**（`EXT_ID` 用 `OR` 拼接），不要一个 PMID 一次调用：

```python
import json, urllib.parse, urllib.request
def epmc(query, n=10, core=True):
    url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?query="
           + urllib.parse.quote(query)
           + f"&resultType={'core' if core else 'lite'}&pageSize={n}&format=json")
    with urllib.request.urlopen(url, timeout=40) as r:
        return json.load(r)

pmids = ["23023126", "24531379", "24531378", "27376579", "17540178"]
res = epmc(" OR ".join(f"EXT_ID:{p}" for p in pmids), n=10, core=True)
for x in res["resultList"]["result"]:
    print(x.get("pmid"), x.get("journalTitle"), x.get("pubYear"), "|", x.get("title"), "|", x.get("doi"))
    print((x.get("abstractText") or "").replace("\n", " ")[:1400])
```

- 开放获取综述/全文：`https://www.ebi.ac.uk/europepmc/webservices/rest/PMC<id>/fullTextXML` → 去标签后按句子切分，grep 关键词组合（如 `asymmetr|polarity` 与 `ag(e|ed|ing)`）定位可引用原句。

## 4. 接口/字段实测坑（2026-09-25 实测）

| 现象 | 处理 |
|---|---|
| `FULL_TEXT:"asymmetric division" AND ...` **固定 0 命中**（换 3 种写法都 0） | Europe PMC 没有 `FULL_TEXT:` 字段 ⇒ 全文检索一律用 **`body:"..."`**（同义查询立刻 42 命中）；零命中的新写法**不要反复改写**，换字段一次即可 |
| `search_papers` 返回 `abstract: ""` 全是空 | 该工具只回元数据 ⇒ 不能据此判支撑等级，必须补 §3 的 EPMC 摘要调用 |
| Semantic Scholar `graph/v1/paper/search` 连续 **429** | 公共端点限流 ⇒ 检索主力用 Europe PMC/PubMed，别在同一轮里反复重试 S2 |
| `.../PMC<id>/fullTextXML` 偶发 **HTTP 500** | 重试 1-2 次；仍失败就退回摘要级证据并在交付里说明"未核全文" |
| `web_extract` 报 "search-only backend and cannot extract URL content" | 后端是 ddgs ⇒ 改用 `urllib/curl` 直取 API/页面（§3 模板即可） |

## 5. 循环控制（本轮被平台强制干预的教训）

同一轮里连发 7 次近似的检索调用（换词重查）→ 触发平台**循环检测强制干预**（要求停止重复动作）。

- 检索轮数上限 **2-3 轮**：第 1 轮宽搜拿候选，第 2 轮批量取摘要定级；再查不出新东西就**转交付**。
- 多查询/多 PMID **合并到一次脚本**（列表 + for 循环打印），不要"一次调用一个查询"。
- 某子论断查不到直接证据 ⇒ 这一轮的产出就是**如实报缺口**，不是继续换关键词续命。

## 6. 工作示例：骨骼肌卫星细胞衰老论断（已核验，可直接复用）

原句：「骨骼肌卫星细胞在衰老过程中自我更新能力下降、不对称分裂增加。」

| # | 文献 | 支撑 | 等级 |
|---|---|---|---|
| 1 | Chakkalakal 2012, *Nature* — aged niche（Fgf2）驱动卫星细胞脱离静息并**丧失自我更新能力**；PMID 23023126 / 10.1038/nature11438 | A | strong |
| 2 | Bernet 2014, *Nat Med* — FGFR1–p38α/β 介导**细胞自主性**自我更新丧失，可药理改善；PMID 24531379 / 10.1038/nm.3465 | A | strong |
| 3 | Cosgrove 2014, *Nat Med* — 2/3 老年 MuSC 内在缺陷、**重建干细胞库能力下降**（移植入年轻肌也不能救）；PMID 24531378 / 10.1038/nm.3464 | A | strong |
| 4 | Lukjanenko 2016, *Nat Med* — 衰老龛 fibronectin↓ → MuSC 数量丢失 + 整合素–FAK–p38 失调控，补 FN 恢复年轻样再生；PMID 27376579 / 10.1038/nm.4126 | A（摘要未提分裂模式） | strong(A) |
| 5 | Kuang 2007, *Cell* — apical–basal **不对称分裂**产生 Pax7⁺/Myf5⁻ 干细胞 + 祖细胞；PMID 17540178 / 10.1016/j.cell.2007.03.044 | B 的机制定义（非衰老证据） | strong(机制) |
| 6 | Shinin 2006, *Nat Cell Biol* — 模板 DNA 链共分离 + Numb 不对称分配；PMID 16799552 / 10.1038/ncb1425 | B 机制背景 | background |
| 7 | Feige 2018, *Cell Stem Cell* — 综述：极性与不对称分裂在稳态/衰老/疾病中的扰动；PMID 30388423 / 10.1016/j.stem.2018.10.006 | B 的**综述**引用 | review/context |

**缺口（必须如实交付）**：摘要级检索**未找到**"衰老使卫星细胞不对称分裂比例升高"的**原始实验论文**（`body:"asymmetric division"` × aged × satellite cell 命中全是综述/旁支）。要保留该强断言，需回 Lukjanenko 2016 或 Feige 2018 综述所引原始文献的**图内定量**逐条核页码。另：A 部分证据物种为**小鼠**为主，人类样本证据需另补（未核摘要不做推荐）。