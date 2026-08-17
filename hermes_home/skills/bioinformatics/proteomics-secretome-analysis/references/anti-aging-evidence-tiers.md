# Anti-Aging Evidence Tiers — 抗衰老蛋白三级证据体系

## 设计原则

从分泌蛋白组中筛选抗衰老候选蛋白需要三重交叉验证：
1. **数据库注释**（UniProt official）
2. **知识库确认**（MemOmics KB 衰老基因集）
3. **文献支撑**（PubMed 功能研究）

分级后按**丰度排名**（而非差异倍数），因为 technical replicates 不做差异分析。

---

## Tier 1 — 强证据 (Strong Evidence)

触发条件（满足 ≥2 项）：

| 证据来源 | 示例 |
|----------|------|
| UniProt 官方 "aging" / "longevity" 注释 | CLU = "Aging-associated gene 4 protein" |
| KB 衰老基因集（liver_aging_up/down）中出现 | C3, CAT, SOD1 |
| ≥2 篇 PubMed 文献直接关联衰老 | HSPD1 线粒体衰老 [PMID:31226289] |
| 衰老 hallmark 通路核心组分 | 蛋白稳态 (HSPD1/HSPA8), 抗氧化 (PRDX1), IGF 通路 (IGFBP2) |

### Tier 1 基因清单（人）

```
HSPD1, PRDX1, HSPA8, CLU, APOE, IGFBP2, FSTL1, HPX, SERPINA1, AHSG, HSPE1
```

---

## Tier 2 — 良好证据 (Good Evidence)

触发条件：KB 衰老基因集确认 + 已知衰老通路关联

### Tier 2 基因清单（人）

```
C3, CAT, SOD1, HSP90AA1, TXN, HSPA5, MIF, PRDX6
```

---

## Tier 3 — 潜在 (Potential)

ECM/代谢/补体等间接关联衰老，需进一步验证。

### Tier 3 基因清单（人）

```
CST3, SPARC, RBP4, COL1A1, COL6A1, SERPINC1, TTR, FN1, APOC3, APOA4, AFP, CFI
```

---

## 纳入报告时的格式

每个候选蛋白报告：
- 丰度排名 + 绝对值
- CV（>0.3 需标注）
- 存在形式分类（Free/Dual/EV）
- 至少 1 条文献引用
- Tier 级别 + 颜色标记

---

## 证据来源速查

| 数据源 | 用途 | 速率限制 |
|--------|------|----------|
| UniProt REST API | 信号肽、亚细胞定位、官方注释 | 0.2s/req |
| MemOmics KB | 物种/组织/方向特异性衰老基因集 | 无 |
| PubMed / Semantic Scholar | 文献交叉验证 | 视 API 而定 |
| ExoCarta / Vesiclepedia | EV 蛋白定位确认 | 本地数据库 |
