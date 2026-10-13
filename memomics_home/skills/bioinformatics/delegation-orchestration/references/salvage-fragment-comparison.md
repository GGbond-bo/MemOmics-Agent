# 散件 ↔ store 全字段比对：形状与字段集的两个静默陷阱

配套：SKILL.md §二 0 / 0-ter / 0-quater。首次实测 2026-10-09（`deleg_c617920e` replay#2 + `deleg_58d8c19a` replay#5 清算轮）。

## 1. 为什么会有「散件」这一层

重放轮做对账时，`卡片 store（cards.json）` 不是唯一证据源：每批子代理/补派批次的**落盘件**在目录里平铺，
文件名编码批次与分片（`deep_cards_round2_t0a.json` / `_t1.json` / `deep_cards_deleg_<id>.json`）。
它们才是能做**逐字 diff** 的源（回执正文与 live log 都被截断，见 §二 第 1 条与 §五）。

## 2. 陷阱一：形状不统一 → 静默 0 条

同一目录（本例 `results/<sid>/data/`）实测三种形状共存：

| 文件 | `type(data)` | `type(data["cards"])` 或等价 | 迭代方式 |
|---|---|---|---|
| `cards.json`（终态 store） | `list`（31） | — | `for c in data`（n 在元素里） |
| `deep_cards_round2_t0a.json`（3 卡） | `dict`，keys=`['cards']` | **`dict`**（键 `'1','2','14'`） | `data["cards"].items()` |
| `deep_cards_round2_t0b.json`（3 卡） | 同上 | `dict` | 同上 |
| `deep_cards_round2_t1.json`（5 卡） | 同上 | `dict` | 同上 |
| `deep_cards_round2_t2.json`（5 卡） | 同上 | `dict` | 同上 |
| `deep_cards_deleg_15d8b24b.json`（15 卡） | `dict`，**键就是 n**（`'4'…'45'`） | — | `data.items()` |
| `deep_cards_deleg_58d8c19a.json`（16 卡） | `dict`，keys=`['cards','evidence','parse_report']` | `list`（**这里才是 list**） | `data["cards"]` |

⚠️ 同名前缀 `deep_cards_*` 下**既有 dict-of-dict 也有 list-of-dict**（`..._58d8c19a.json` 的 cards 是 list）
⇒ 不能按文件名前缀推断形状，**必须逐个 `print(type(...).__name__)`**。

失败模式：`v = [x for x in data.values() if isinstance(x, list) and x and isinstance(x[0], dict)]`
对 dict-of-dict 返回 `[]` —— 不抛异常、打印 `0 cards`。脚本"成功"，结论全错。
（若写成 `for x in v` 后直接 `x.get("n")`，则在迭代字符串时崩 `'str' object has no attribute 'get'`，
那是**幸运**的暴露；更常见的是走了 `continue` 静默跳过。）

三形状通吃读法：

```python
def pairs_of(path):
    d = json.load(open(path, encoding="utf-8"))
    v = d.get("cards", d) if isinstance(d, dict) else d
    if isinstance(v, dict):
        return [(int(k), x) for k, x in v.items()]
    return [(x["n"], x) for x in v]
```

## 3. 陷阱二：升级片段只含 9 个深字段

深读升级片段内 `name` / `team` / `goal` 全为 `None`（升级轮只要深字段）：
拿 12 字段（9 深 + name/team/goal）做 diff ⇒ 16/16 卡各报 3 个假差异。

实测对照（n=1 / n=2）：

```
n=1 name   src: None      sto: Robin
n=1 team   src: None      sto: FutureHouse (San Francisco) 联合 University of Oxford、Fordham University；…
n=1 goal   src: None      sto: 把实验生物学的假设生成与实验数据分析串成连续闭环，…
```

⇒ 正确结论是「**store 侧元数据完整保留，片段未采集**」——不是冲突、不是缺失、不构成新工作。
**diff 集合按片段类型选**：升级片段 9 深字段；全量卡全字段。报差异后先 print 两侧原值再定性。

## 4. 本轮的实证结论（可作模板）

- 形状修正后：`deep_cards_round2_t{0a,0b,1,2}` = 3+3+5+5 = **16 卡**（n=1,2,14,15,16,17,19,20,21,22,23,24,26,27,29,31）
  × 9 深字段 vs store ⇒ **16/16 逐字全等，差异 0**。
- 补派链：`deleg_c617920e` Task1 自报「blocked before file write」的 6 篇 = `t0a`(n=1,2,14；21,729 B)
  + `t0b`(n=15,16,17；19,286 B)（01:27 / 01:26 落盘）⇒ 自报为真但**不构成数据缺口**，不重派。
- `deleg_58d8c19a` 落盘件 16 卡是 **round1 源**，其 9 深字段与 store 不同属**代次取代**（预期）；
  `name/team/goal` 与 store 一致 ⇒ 两段证据方向相反正是「升级轮覆盖深字段、保留元数据」的指纹。
- 闭环不变量：**31 = 16(round2, 2026-10-08) + 15(round1-deep, 2026-10-07)**；`deep_read` 31×True；thin(<300) 0。
- 字段健康（<25 字 + 合法短值白名单）：**0 真缺陷**；`architecture` 775–1,587（中位 1,182）；`limitations` 最短 132 字。
- 交付物指纹当场对齐定稿：DOCX 793,395 B / HTML 1,233,970 B / positioning_full.md 299,145 B / evidence.csv 97 行 38,600 B。

## 5. 顺序建议（省 token）

1. 台账 `grep -n "deleg_" notes.md`（一跳；命中本批 + 交付物字节一致 ⇒ 直接定案）；
2. 未命中才做散件 ↔ store **逐字段** diff（用 §2 读法 + §3 字段集）；
3. 同一轮顺手跑字段健康扫描（§二 ⓪-d）；
4. 全程**只读**；结论与指纹追加 `notes.md`，主数据与交付物一个字节不动。