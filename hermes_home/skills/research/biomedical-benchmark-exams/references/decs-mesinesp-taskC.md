# MESINESP TaskC 实测（2026-08-02, memomics-731658a3）

> 试卷3_多语言检索MESINESP：4 篇西班牙语医学文献 → 输出 DeCS 编码（gold 为数字 ID）。
> 本文件记录 DeCS 端点探测全过程与最终可用配方。

## 关键结论（速查）

| 目标 | 可用端点/方法 | 失败端点 |
|------|--------------|---------|
| DeCS ID → 描述符名+树号 | `https://decs.bvsalud.org/ths/resource/?id={did}`（解析正文，勿信 h1） | `https://decs.bvsalud.org/ths/?filter=ths_regid&q={did}&lang=es`（返回反馈页）；`/E/{did}/`、`/en/ths?filter=...` 同 |
| MeSH 词 → UID | `query_ncbi(db="mesh")` 或 eutils `esearch.fcgi?db=mesh&term=X[MeSH]&retmode=json` | —（但只给 UID 不给名称） |
| UID → 树号 | eutils `efetch.fcgi?db=mesh&id={uid}&retmode=xml` → 抓 `Tree Number(s):` 行 | — |
| 多语言名 | `/ths/resource/?id=` 正文含 `Descritor em português/inglês/espanhol/francês` | — |

## DeCS 端点探测记录

试过的 URL 形态（全部 HTTP 200 但**内容错误**，返回网站反馈页）：
```
https://decs.bvsalud.org/ths/?filter=ths_regid&q=20174&lang=es     → h1=Queremos a sua opinião...
https://decs.bvsalud.org/E/20174/                                   → 同上
https://decs.bvsalud.org/en/ths?filter=ths_regid&q=20174            → 同上
https://decs.bvsalud.org/ths/resource/?id=20174                     → h1/title 仍是反馈页！
```
反馈页标志：`<title>DeCS</title>` + `Queremos a sua opinião sobre o novo sitio web do DeCS/MeSH` / `We want your feedback on the new DeCS / MeSH website`。

**⚠️ 关键：`/ths/resource/?id=` 的 h1 是反馈页，但页面正文确实包含描述符信息**——必须用正则从正文提取，不能靠 h1/title/meta。

## 可用配方

### 1) DeCS ID → 名称 + 树号（正文解析）
```python
import requests, re

def get_decs_desc(did):
    url = f"https://decs.bvsalud.org/ths/resource/?id={did}"
    txt = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"}).text
    fields = {}
    for lang_key, label in [("pt","português"),("en","inglês"),("es","espanhol"),("fr","francês")]:
        m = re.search(r'Descritor em\s*'+label+r':[^<]*</[^>]+>\s*<[^>]+>(.*?)</', txt, re.S)
        if not m:
            idx = txt.find(f'Descritor em {label}:')
            if idx > 0:
                m2 = re.search(r'<td[^>]*>(.*?)</td>', txt[idx:idx+800], re.S)
                if m2: fields[lang_key] = re.sub(r'<[^>]+>','',m2.group(1)).strip()
        else:
            fields[lang_key] = re.sub(r'<[^>]+>','',m.group(1)).strip()
    trees = list(dict.fromkeys(re.findall(r'([A-Z]\d+(?:\.\d+)+)', txt)))
    return fields, trees
```
实测：20174 → ES=Anciano / EN=Aged / trees=M01.060.116.100, M01.060, ...（与 gold 的 20174=Anciano(Aged) 一致）。
按 gold 的 DeCS ID 建 name→ID 映射时，每请求间 `time.sleep(0.4)`。

### 2) MeSH 词 → UID（query_ncbi db=mesh 即可）
`query_ncbi(db="mesh", query="Mediastinal Neoplasms")` → uid=68008479。注意只给 UID 不给名称。

### 3) MeSH UID → 树号（eutils efetch）
```python
def fetch_trees_by_ui(uid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + \
          urllib.parse.urlencode({"db":"mesh","id":uid,"retmode":"xml"})
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    for a in range(4):
        try:
            txt = urllib.request.urlopen(req, timeout=30).read().decode()
            m = re.search(r"Tree Number\(s\):\s*(.+)", txt)
            return [t.strip() for t in m.group(1).split(",")] if m else []
        except Exception: time.sleep(4*(a+1))
    return []
```
实测：68001706 → Biopsy trees=['E01.370.225.500.384.100', 'E01.370.225.998.054', 'E01.370.388.100', 'E04.074', 'E05.200.500.384.100', ...]。
- **新 UID 前缀 68xxxxx**（D001706 → 68001706、D001803 → 68001803、D013536 → 68013536）。
- eutils 裸 curl 会超时（120s 实测挂），必须 Python urllib + UA + 退避重试 + 请求间 sleep。

## TaskC 作答建议
1. 对每篇西语文献提取 Descriptor 名（疾病/干预/机制/结局/人群，西语优先）。
2. MeSH 词先 query_ncbi(db=mesh) 拿 UID → efetch 拿树号 → 与 gold 的 DeCS ID 树号比对。
3. 直接按名字查 DeCS resource 页拿 ID 反向验证。
4. 评分时 ID 精确匹配（gold 是纯数字编码），名称匹配只作辅助。
