# Functional enrichment: clusterProfiler — session 2026-07-04

## Human skeletal muscle aging, 1,119 sig DEGs (padj<0.05)

### Proven workflow

```r
library(clusterProfiler)
library(org.Hs.eg.db)
library(enrichplot)

# 1. Convert SYMBOL to ENTREZID (10-18% may fail to map)
entrez <- bitr(gene_list, fromType="SYMBOL", toType="ENTREZID", OrgDb=org.Hs.eg.db)

# 2. GO enrichment
ego_bp <- enrichGO(gene=entrez$ENTREZID, OrgDb=org.Hs.eg.db, ont="BP",
                   pAdjustMethod="BH", qvalueCutoff=0.05, readable=TRUE)
ego_mf <- enrichGO(gene=entrez$ENTREZID, OrgDb=org.Hs.eg.db, ont="MF",
                   pAdjustMethod="BH", qvalueCutoff=0.05, readable=TRUE)
ego_cc <- enrichGO(gene=entrez$ENTREZID, OrgDb=org.Hs.eg.db, ont="CC",
                   pAdjustMethod="BH", qvalueCutoff=0.05, readable=TRUE)

# 3. KEGG (online, may be slow)
ekegg <- enrichKEGG(gene=entrez$ENTREZID, organism="hsa",
                    pAdjustMethod="BH", qvalueCutoff=0.05)

# 4. Reactome (requires ReactomePA package — NOT in clusterProfiler!)
if (requireNamespace("ReactomePA", quietly=TRUE)) {
  ereact <- ReactomePA::enrichPathway(gene=entrez$ENTREZID, organism="human",
                                       pAdjustMethod="BH", qvalueCutoff=0.05, readable=TRUE)
}

# 5. Visualize
dotplot(ego_bp, showCategory=20)
barplot(ego_bp, showCategory=20)
cnetplot(ego_bp, showCategory=10, circular=FALSE, colorEdge=TRUE)
```

### Results summary
- Old-up (363 genes): "response to reactive oxygen species" (228 GO BP), "Malaria" (KEGG)
- Old-down (427 genes): "muscle system process" (224 GO BP), "Cytoskeleton in muscle cells" (KEGG)

### Errors & fixes

| Error | Fix |
|-------|-----|
| `AnnotationDbi >= 1.73.0 required by org.Hs.eg.db` | `BiocManager::install('org.Hs.eg.db', force=TRUE)` from source |
| `enrichPathway` not found | `enrichPathway` is in ReactomePA package, not clusterProfiler; use `ReactomePA::enrichPathway` or skip |
| KEGG top term "Malaria" (biologically irrelevant) | Background gene set bias — all annotated genes used; should filter to tissue-expressed genes only |
| 228 GO BP terms (too many, redundant) | Use `simplify()` or `rrvgo` to collapse redundant GO terms |

### Known traps
- **Background gene set**: default uses all org.Hs.eg.db genes → spurious terms like "Malaria". Use tissue-specific expressed genes as background.
- **GO redundancy**: parent-child term overlap inflates counts; always apply `simplify()` post-hoc.
- **KEGG is slow**: fetches online from KEGG REST API; cache results.