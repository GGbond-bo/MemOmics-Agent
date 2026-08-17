---
name: Heart Conference Monitor
description: Monitor and analyze heart conference presentations
category: General Utility
tags: [heart, conference, monitor]
when_to_use: "心脏会议监控：追踪心脏病学会议→提取关键发现→监控研究趋势→生成报告"
---
# Heart Conference Monitor Pipeline

## Overview
Automated Python pipeline to monitor 24 major cardiology/cardiovascular conferences,
retrieve abstracts via PubMed API + web scraping, cluster by topic using NLP,
generate AI summaries per cluster, and render an interactive HTML dashboard.

## Conference Coverage (24 total)

| # | Short | Conference Name | Dates | Location | Abstract Source | Est. Total | Est. Saved | Sampling |
|when_to_use: "[heart-conference-monitor] 需使用heart conference monitor功能，适用于相关生信分析场景"
---|-------|----------------|-------|----------|-----------------|-----------|-----------|---------|
| 1 | ACC | ACC Annual Scientific Session | Mar 28–30, 2026 | Chicago, IL | PubMed (J Am Coll Cardiol) + scrape | ~2,500 | ~188 | 100% |
| 2 | ESC | ESC Congress | Aug 28–31, 2026 | Munich | PubMed (Eur Heart J Suppl) + scrape | ~5,000 | ~500 | **10%** |
| 3 | AHA | AHA Scientific Sessions | Nov 6–9, 2026 | TBD | Ovid scrape (Circulation Suppl) | ~4,200 | ~420 | **10%** |
| 4 | HRS | HRS Annual Meeting | Apr 23–26, 2026 | TBD | PubMed (Heart Rhythm) + scrape | ~1,200 | ~448 | 100% |
| 5 | HFSA | HFSA Annual Scientific Meeting | Oct 9–12, 2026 | TBD | PubMed (J Card Fail) + scrape | ~400 | ~114 | 100% |
| 6 | EHRA | EHRA Congress | Apr 12–14, 2026 | Paris | PubMed (Europace) | ~1,000 | ~800 | 100% |
| 7 | ESC_HF | ESC Heart Failure Congress | May 9–12, 2026 | Barcelona | PubMed (Eur J Heart Fail) | ~1,400 | ~140 | **10%** |
| 8 | EAPC | ESC Preventive Cardiology | Apr 23–25, 2026 | Ljubljana | PubMed (Eur J Prev Cardiol) | ~500 | ~496 | 100% |
| 9 | HFA_WINTER | HFA Winter Research Meeting | Jan 27–29, 2026 | Berlin | PubMed (Eur J Heart Fail) | ~80 | ~80 | 100% |
| 10 | FCVB | Frontiers in CardioVascular Biomedicine | Apr 17–19, 2026 | Leuven | ESC 365 scrape | ~200 | ~200 | 100% |
| 11 | BCVS | AHA BCVS Scientific Sessions | Jul 13–16, 2026 | Boston | PubMed (Circ Res) | ~600 | ~500 | 100% |
| 12 | ATVB | Vascular Discovery (ATVB) | May 13–16, 2026 | Bellevue, WA | PubMed (Arterioscler Thromb Vasc Biol) | ~500 | ~400 | 100% |
| 13 | EAS | EAS Congress | May 24–27, 2026 | Athens | PubMed (Atherosclerosis) | ~600 | ~500 | 100% |
| 14 | ISHR_NAS | ISHR North American Section | May 31–Jun 3, 2026 | Minneapolis | PubMed (J Mol Cell Cardiol) | ~400 | ~300 | 100% |
| 15 | ISHR_ES | ISHR European Section | Jun 22–25, 2026 | Birmingham | PubMed (J Mol Cell Cardiol) | ~400 | ~300 | 100% |
| 16 | ISA | International Symposium on Amyloidosis | Nov 15–18, 2026 | Montevideo | PubMed (Amyloid) | ~600 | ~530 | 100% |
| 17 | IVBM | International Vascular Biology Meeting | Sep 6–10, 2026 | Adelaide | HTML scrape (ivbm2026.com) | ~300 | ~300 | 100% |
| 18 | SHVM | Society for Heart and Vascular Metabolism | Oct 26–29, 2026 | Osaka | HTML scrape (shvm2026.azuleon.org) | ~200 | ~200 | 100% |
| 19 | AMYLOIDOSIS_FORUM | Amyloidosis Forum Annual Meeting | Oct 22, 2025 | FDA White Oak | None (1-day workshop) | 0 | 0 | — |
| 20 | KEYSTONE_CARDIOMET | Keystone: Cardiometabolism | Jan 26–29, 2026 | Keystone, CO | None (invite-only) | 0 | 0 | — |
| 21 | KEYSTONE_FIBROSIS | Keystone: Fibrosis | Feb 2–5, 2026 | Banff | None (invite-only) | 0 | 0 | — |
| 22 | KEYSTONE_TCELLS | Keystone: T Cells | Jan 11–14, 2027 | Banff | None (invite-only) | 0 | 0 | — |
| 23 | GRC_CARDIAC | GRC Cardiac Regulatory Mechanisms | Jun 28–Jul 3, 2026 | New London, NH | None (invite-only) | 0 | 0 | — |
| 24 | ELRIG | ELRIG Cell-based Screening | May 6–7, 2026 | Gothenburg | None (no public abstracts) | 0 | 0 | — |

**Total estimated abstracts saved: ~5,916** (across 18 active conferences; 6 stubs return [])

### Sampling Policy
Large conferences (>1,000 abstracts) are sampled at **10%** to save time:
- ESC Congress: ~5,000 total → ~500 saved
- AHA Scientific Sessions: ~4,200 total → ~420 saved
- ESC Heart Failure: ~1,400 total → ~140 saved

If not yet held in 2026, the pipeline falls back to the most recent available year
(e.g. ISHR_NAS uses 2024 Long Beach data until 2026 Minneapolis abstracts are published).

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

---

## Architecture

```
run_pipeline.py          ← CLI orchestrator
├── scheduler.py         ← Date-aware trigger logic
├── retrieval/
│   ├── pubmed_fetcher.py  ← PubMed E-utilities (all PubMed-indexed conferences)
│   └── web_scraper.py     ← Per-conference scrapers + stubs
├── processing/
│   ├── deduplicator.py    ← 3-tier dedup + SQLite cache
│   ├── clusterer.py       ← BERTopic + LDA fallback
│   └── summarizer.py      ← OpenAI gpt-4o-mini + sumy fallback
└── dashboard/
    └── builder.py         ← Plotly HTML dashboard
```

---

## Usage

```bash
# Run all due conferences (scheduler decides based on dates)
python run_pipeline.py

# Force a specific conference + year
python run_pipeline.py --conference ACC --year 2026

# Run all conferences for a specific year
python run_pipeline.py --year 2026

# Skip clustering/summarization (fetch only)
python run_pipeline.py --conference EHRA --year 2026 --no-cluster
```

---

## Key Technical Details

### PubMed Fetcher
- Endpoint: NCBI E-utilities (esearch + efetch)
- Rate limit: 0.35s delay (3 req/s without API key; 0.1s with NCBI_API_KEY)
- Batch size: 200 PMIDs per efetch call
- Retries: 3 with exponential backoff
- Sampling: `random.seed(42)` for reproducibility when `sample_pct < 1.0`
- Skips: `abstract_source == "none"` or `abstract_source == "scrape"` or missing `pubmed_journal`

### Web Scrapers
- **AHA**: Crossref DOI discovery → Ovid abstract fetching (ahajournals.org is Cloudflare-blocked)
  - Ovid URL: `https://www.ovid.com/journals/circ/fulltext/10.1161/circ.<vol>.suppl_3.<ID>`
  - AHA 2025 = Circulation Vol 152 Suppl_3 (~4,221 DOIs)
  - AHA 2026 volume mapping TBD (update `vol_map` in `_discover_aha_dois()` when announced)
- **ESC / FCVB**: ESC 365 JSON API → HTML fallback
  - FCVB reuses `scrape_esc()` with `event_slug="fcvb-{year}"`
- **IVBM**: HTML scraper for `ivbm{year}.com`
- **SHVM**: HTML scraper for `shvm{year}.azuleon.org`
- **Stubs** (return []): KEYSTONE_CARDIOMET, KEYSTONE_FIBROSIS, KEYSTONE_TCELLS, GRC_CARDIAC, ELRIG, AMYLOIDOSIS_FORUM

### AHA Ovid Parsing Patterns
```python
# Title: strip "Abstract NNNNNN: " prefix
title = re.sub(r'^Abstract\s+[\w]+:\s*', '', h1.get_text(strip=True)).strip()
# Abstract: collect <p> tags with section labels
if re.match(r'^(Introduction|Background|Hypothesis|Objective|Methods|Results|Conclusion)', text):
# Authors: span.lww-article__contributor (reversed — Ovid lists last-to-first)
name = re.sub(r'([a-z])([A-Z])', r'\1 \2', span.get_text(strip=True))
authors = list(reversed(authors))
```

### Deduplication (3-tier)
1. PMID exact match
2. SHA-256 of first 80 chars normalized title
3. Jaccard similarity ≥ 0.85

### BERTopic Configuration
```python
UMAP(n_neighbors=min(15, len(valid_docs)-1), n_components=2, min_dist=0.0,
     metric="cosine", random_state=42, low_memory=True)
HDBSCAN(min_cluster_size=5, min_samples=3, metric="euclidean",
        cluster_selection_method="eom", prediction_data=True)
CountVectorizer(ngram_range=(1,2), stop_words="english", min_df=2, max_features=10000)
embedding_model = "all-MiniLM-L6-v2"
```

**UMAP Bug Fix (CRITICAL):**
```python
# CORRECT: read from umap_model.embedding_ directly after fit_transform()
if hasattr(umap_model, "embedding_") and umap_model.embedding_ is not None:
    umap_2d = umap_model.embedding_
else:
    embeddings = topic_model.embedding_model.encode(valid_docs, show_progress_bar=False)
    umap_2d = umap_model.transform(embeddings)
```

### Summarization
- Primary: OpenAI gpt-4o-mini, max 20 abstracts/cluster, max_tokens=300, temperature=0.3
- Fallback: sumy TextRank (4 sentences)
- Small clusters (<3): simple truncation

### SQLite Schema
```sql
id, title_hash, pmid, conference, year, title, abstract, authors, journal,
pub_year, pub_month, mesh_terms, doi, source, url, fetched_at,
topic_label, topic_id, summary
```
Note: umap_x/umap_y are NOT stored (computed in-memory at dashboard build time).

### Volume Number Helpers
```python
def _acc_jacc_vol(year): return 87 + (year - 2026)   # JACC vol 87 = 2026
def _hrs_vol(year):      return 23 + (year - 2026)   # Heart Rhythm vol 23 = 2026
def _hfsa_vol(year):     return 32 + (year - 2026)   # JCF vol 32 = 2026
# AHA: Circulation vol 152 = 2025 (Suppl_3); vol 150 = 2024 (Suppl_1)
# AHA 2026: volume not yet determined — update vol_map in _discover_aha_dois()
```

---

## Topic Taxonomy (12 categories)

| Category | Key Terms |
|----------|-----------|
| Heart Failure | heart failure, hfref, hfpef, sglt2, sacubitril, bnp, ntprobnp |
| Coronary Artery Disease | myocardial infarction, stemi, pci, cabg, atherosclerosis, ffr |
| Arrhythmia | atrial fibrillation, ablation, pacemaker, icd, electrophysiology |
| Cardiomyopathy | hypertrophic, dilated, amyloidosis, myocarditis, takotsubo |
| Valvular Heart Disease | aortic stenosis, tavr/tavi, mitral regurgitation, tricuspid |
| Imaging & Diagnostics | echocardiography, cardiac mri, troponin, biomarker, strain |
| Prevention & Risk Factors | hypertension, diabetes, statin, pcsk9, lipoprotein |
| AI & Digital Health | machine learning, deep learning, wearable, remote monitoring |
| Amyloidosis | transthyretin, attr, tafamidis, al amyloid, cardiac amyloidosis |
| Vascular Biology | endothelial, thrombosis, hemostasis, peripheral artery disease |
| Other / Emerging | catch-all |

---

## Dashboard Colors
```python
TAXONOMY_COLORS = {
    "Heart Failure": "#0279EE", "Coronary Artery Disease": "#FF9400",
    "Arrhythmia": "#75A025", "Cardiomyopathy": "#FD9BED",
    "Valvular Heart Disease": "#E9ED4C", "Imaging & Diagnostics": "#9B59B6",
    "Prevention & Risk Factors": "#E74C3C", "AI & Digital Health": "#1ABC9C",
    "Amyloidosis": "#8B4513", "Vascular Biology": "#20B2AA",
    "Other / Emerging": "#95A5A6", "Uncategorised": "#BDC3C7",
}
```

---

## File Paths
- Source code: `/mnt/shared-workspace/heart_conference_monitor/` (persistent)
- Results: `/mnt/results/` (persistent)
- Worker scratch: `/workspace/` (ephemeral — lost on worker termination)
- SQLite cache: `/workspace/heart_conference_monitor/cache/abstracts.db` (ephemeral)
- AHA DOI lists: `/mnt/shared-workspace/aha2025/doi_list_full.json` (4,221 DOIs)
- Dashboard: `/mnt/results/dashboard_heart_disease_abstracts.html`
- ZIP: `/mnt/results/heart_conference_monitor_pipeline.zip`

---

## Known Issues & Workarounds

| Issue | Resolution |
|-------|-----------|
| UMAP coordinates all 0.0 | Read from `umap_model.embedding_` not re-encode + transform |
| NLTK punkt_tab missing | punkt available; sumy falls back to simple extractive |
| SQLite tuple index bug | Use `existing[0]` not `existing["id"]` |
| `--year` flag not respected | Rewrote CLI argument handling |
| Worker-0 terminated, SQLite cache lost | Load from persistent CSVs in `/mnt/results/` |
| Background scrape PermissionError on `/mnt/shared-workspace/` | Use `/workspace/` for checkpoint files |
| `ahajournals.org` returns 403 Cloudflare | Use Ovid with browser-like headers |
| ZIP build fails on S3-backed path | Build in `/tmp/`, then copy to `/mnt/results/` |
| F-string backslash syntax error | Replaced with intermediate variable |
| S3-backed paths don't support Write tool | Use ExecuteCode with `open(..., "w")` instead |

---

## Scraping Settings
- Delay: 2.0s between requests per domain
- Timeout: 15s (20s for Ovid)
- Pipeline User-Agent: `"HeartConferenceMonitor/1.0 (research pipeline; contact: research@example.com)"`
- Ovid User-Agent: `"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"`
- Ovid Referer: `"https://www.ovid.com/"`

---

## Scheduler Logic
- Trigger date = conference start − trigger_offset_days
- Skip if last run < 30 days ago (stored in `cache/last_run.json`)
- Force override: `--conference <SHORT>` bypasses date check
- `--year` flag: always respected if provided
- Conference window: trigger_date ≤ today ≤ conf_end + 60 days
- Fallback year: if conference not yet held in current year, use most recent available year


---

## 🗣️ 辩论机制（debate_analysis）

本 skill 在执行后，如果涉及**参数选择、方法决策、结果判断**等不确定环节，**必须**调用  工具进行多角色辩论。

### 辩论规则
- **正方 3 位专业编辑**（各自独立，互相看不到）：生物学编辑 / 统计学编辑 / 生信编辑
- **反方 4 位专业编辑**（各自独立，互相看不到，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
- **裁判**：看到所有 7 方论点后给出裁决 + 置信度（高/中/低）
- **上下文隔离**：每个编辑是独立的 LLM API 调用，messages 只包含自己的 prompt
- **分科知识库**：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
- **辩论结果自动归档**到 results/.../log/debate_*.json

### 触发场景
- 参数选择有多个合理选项时（如分辨率 0.4 vs 0.6 vs 0.8）
- 结果可能受方法选择影响时（如不同注释方法给出不同结果）
- 生物结论需要验证可靠性时
- QC 阈值不确定时（如 MT% 阈值 10% vs 15% vs 20%）

### 不触发场景
- 参数有明确知识库推荐且无争议时
- 纯计算步骤（如保存文件、读取数据）
