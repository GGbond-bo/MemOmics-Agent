# Term / gene selection worksheet — ready-to-run recipe

Purpose: when the user must **choose** which terms and which genes appear in a curated
enrichment heatmap, dump the complete candidate list first. Agent picks layout only.

Source session: 2026-09-15, `MF_SMF_GO_select.xlsx` (68 rows / 15 clusters / 48 unique
terms / 337 unique genes / 13 cross-cluster shared terms).

## 1. R snippet (runs one-shot in `execute_r`, R 4.5.3 has `openxlsx`)

```r
suppressMessages(library(openxlsx))
d <- read.xlsx("D:/path/to/selected_GO.xlsx", sheet = 1)   # cols: Cluster | Path | Genes | Log(q-value)

d$val <- round(-as.numeric(d$`Log(q-value)`), 1)            # -log10(q), positive
d$gn  <- gsub("|", ", ", d$Genes, fixed = TRUE)             # ⚠️ fixed=TRUE — see pitfall
d$sh  <- ave(seq_len(nrow(d)), d$Path, FUN = length)        # how many clusters share this term

out <- c("# term selection worksheet", "")
for (cl in unique(d$Cluster)) {                             # xlsx order = user's column order
  s <- d[d$Cluster == cl, ]
  out <- c(out, paste0("## ", cl, " (", nrow(s), " terms)"))
  out <- c(out, "| term | -log10q | shared | genes (full pool) |", "|---|---|---|---|")
  for (i in seq_len(nrow(s))) {
    tag <- if (s$sh[i] > 1) paste0(s$sh[i], " clusters") else "-"
    out <- c(out, sprintf("| %s | %.1f | %s | %s |", s$Path[i], s$val[i], tag, s$gn[i]))
  }
  out <- c(out, "")
}
writeLines(out, "results/<sid>/data/terms_full_list.md")
```

Then `read_file` that markdown and paste the tables into the reply, followed by a
shared-term summary table, followed by the sizing plan.

## 2. Pitfall — gene-string split

`gsub("\\|", ", ", x)` fails inside `execute_r` with
`'\' is an unrecognized escape in character string` (tool-layer backslash escaping
collides with R string escaping). **Always use `fixed = TRUE`:**
`gsub("|", ", ", x, fixed = TRUE)`.

## 3. Aesthetic sizing rule (agent decides these; user decides content)

```
cell_w, cell_h   <- 0.36, 0.28          # inches — flat cells, wide > tall
plot_w           <- n_clusters * cell_w  # 15 clusters -> 5.4 in
plot_h           <- n_rows     * cell_h  # rows drive height -> natural portrait
rownames_w       <- 3.6                  # term + "(gene1, gene2)" ~60 chars max
colnames_h       <- 1.1                  # angle_col = 45
total_w          <- 7.5
total_h          <- n_rows * 0.28 + 2.2  # 24 rows -> 8.9 in (portrait OK)
png(res = 300, width = max(3800, total_w*300), height = total_h*300)
```

Keep width pinned near 7.5 in and let height grow with row count — that is what makes
the figure read as **portrait** for a 15-cluster × 20-30-term matrix (the user's
explicit requirement: *"亚群只有15个，词条却是有几十个。所以肯定是偏长的形状"*).

## 4. Shared-term merge reminder

13 terms recur across clusters in the reference dataset (`muscle structure development` ×6,
`myofibril assembly` ×3, `supramolecular fiber organization` ×3, `oxidative phosphorylation` ×3,
plus 9 terms ×2). Merged rows take **4 genes** (overlap genes preferred) instead of 2-3.
