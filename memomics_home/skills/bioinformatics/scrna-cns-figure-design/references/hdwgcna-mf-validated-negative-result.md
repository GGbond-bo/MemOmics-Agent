# hdWGCNA on Myofibers — ~~Validated Negative Result~~ **RETRACTED (2026-08-01, same day)** + Windows Install + dev-API Quirks

> ⚠️ **⚠️ THIS FILE IS SUPERSEDED — see `hdwgcna-module-extraction-and-hub.md` instead.**
> The "negative result" below was an ARTIFACT of (a) buggy hdWGCNA **dev-branch** pipeline
> (MetacellsByGroups does not persist wgcna_name; TestSoftPowers returns object not test$data)
> and (b) a **stale 4659-metacell datExpr**. With **release v0.4.12 + a fresh 6482-metacell
> object**, the SAME muscle MF data gives **soft-power R²=0.98 @ power=10 and 9 meaningful
> modules** (black=angiogenesis, blue=OxPhos, brown=sarcomere, red=fast-twitch 8/9 markers,
> turquoise=RSS 5/6), with a module-trait correlation that directly answered the user's
> effect-response question. **A flat soft-threshold + single module is a red flag for PIPELINE
> STATE, not a property of terminally-differentiated biology.**
>
> The install path (section 2) and dev-API quirks (section 3) remain valid and useful for
> anyone forced onto the dev branch; the biological decision rule (section 4) is REVERSED.

## 1. The artifact that was initially interpreted as a negative result (2026-08-01, human skeletal muscle MF, 20000 cells → 4659 metacells × 10176 genes, top3000 MAD genes)

| Signal | Value | Meaning |
|--------|-------|---------|
| Soft-threshold scale-free R² | **max 0.719 at power=1**, never reaches 0.8 across power 1-30 | Network does not satisfy scale-free assumption |
| `blockwiseModules` (signed, bicor, minModuleSize=30) | **all 3000 top-variance genes → single turquoise module** (mergeCloseModules: "less than two proper modules") | No module discrimination at all |
| Independent recompute (pickSoftThreshold + blockwiseModules from raw datExpr) | topR2=0.719@1, mods=1 — identical to first run | Deterministic, not a fluke |

Same data with NMF (RcppML, k=6, MALAT1/MT/RPL/TTN excluded): clean 6 programs, P3=RSS aging program (BMPR1B), program×condition separation. **NMF >> hdWGCNA for terminally differentiated myofibers — confirmed empirically, not just predicted.**

Root cause: MF terminal-differentiated transcriptional programs are highly coordinated (slow/fast/metabolic genes share one axis) → co-expression network is flat → WGCNA cannot cut independent modules. This is a property of the biology, not the parameters (tested power 1-30, signed/bicor, minModuleSize 30).

## 2. Windows install path that worked (R 4.4.2) — only attempt this if hdWGCNA is truly required

Context: remotes::install_github fails on GitHub API network; pak::pak fails trying to rebuild Bioc deps; BiocManager fails with "Bioconductor version map cannot be validated"; dev-branch tarball/zip is >120MB (repo contains test data; main branch doesn't exist, default IS dev).

1. `install.packages("WGCNA", repos="https://mirrors.tuna.tsinghua.edu.cn/CRAN/")` (binary OK) + Bioc deps impute/preprocessCore
2. Sparse clone (few MB): `git clone --depth 1 --branch dev --filter=blob:none --sparse https://github.com/smorabit/hdWGCNA.git && git sparse-checkout set R src man`
3. Missing deps:
   - UCell (Bioc, mirrors 404): download zip from `codeload.github.com/carmonalab/UCell/zip/refs/heads/master` → install source
   - GeneOverlap (Bioc): download source tarball from `bioconductor.org/packages/release/bioc/src/contrib/`
   - **tester** (author-internal, not on GitHub) → **create a dummy package** satisfying the Imports declaration: DESCRIPTION (Package/Version/Title/Authors@R/Description/License/Encoding/LazyData/Depends R>=3.5) + NAMESPACE with explicit `export(is_numeric_dataframe)` + `export(is_numeric_matrix)` + R/dummy.R implementing both. hdWGCNA only uses these 2 functions. ⚠️ `exportPattern("^[^\\\\.]")` breaks on Windows with an escape error — use explicit export() list.
4. Install source from Windows path (MSYS `/tmp/...` is rejected as "没有设定程序包"): `install.packages("C:/Users/<user>/AppData/Local/Temp/<src>", repos=NULL, type="source")`

## 3. dev-version API differences (all hit in one run)

| Pitfall | Truth |
|---------|-------|
| `Assays(obj)` returns S4 SimpleAssays in Seurat v5.5 | Cannot paste/`%in%`/as.vector — don't print assay lists; use `DefaultAssay(obj)` directly |
| `MetacellsByGroups` does NOT persist wgcna_name into the object | Pass `wgcna_name="xxx"` explicitly to EVERY hdWGCNA function |
| `NormalizeMetacells/ScaleMetacells/RunPCAMetacells/RunUMAPMetacells` | Operate on the ORIGINAL Seurat object (they internally Get/SetMetacellObject), NOT on the object returned by `GetMetacellObject()` |
| `RunUMAPMetacells` | Parameter is `dims` not `dimensions` |
| `TestSoftPowers` | Returns the **Seurat object itself** (not `test$data`); retrieve with `GetPowerTable(obj, wgcna_name=...)` |
| `GetMetacellObject()` returns an object with EMPTY misc | It is a plain Seurat object — don't expect wgcna params on it |

## 4. Decision rule (REVISED 2026-08-01 — reverse of the original conclusion)

For terminally differentiated / transcriptionally coordinated tissue (myofibers, hepatocytes, mature neurons):
- **Do NOT skip hdWGCNA on the basis of "flat network"** — the flatness was an artifact of dev-branch bugs + too-few metacells. Use **release v0.4.12**, rebuild metacells (enough to hit scale-free: 6482 worked where 4659 failed), then test soft power before judging.
- **hdWGCNA's module-trait correlation is the stronger tool when the question is "which modules respond to which effect"** (five-effect axes) — on muscle MF it produced the F2e heatmap + hub networks the user actually wanted.
- NMF/cNMF remains the choice when you need **cell-level loadings** (program×condition boxplots, UMAP feature plots) and soft membership; hdWGCNA needs metacell aggregation and gives metacell-level eigengenes.
- Ideal pairing: **NMF in main figure (cell-level loadings), hdWGCNA in supplementary (module-trait correlation + hub genes, independent validation)**; high Jaccard overlap = "two independent methods agree".
- F4-after-DEG organization (merge DEGs → modules → name "aging-response / exercise-reversal / irreversible") remains a strong hdWGCNA use.

> This retraction complements `nmf-vs-hdwgcna-vs-hotspot.md` (literature comparison) and
> `hdwgcna-module-extraction-and-hub.md` (corrected positive result + extraction/hub/p-value pitfalls).
