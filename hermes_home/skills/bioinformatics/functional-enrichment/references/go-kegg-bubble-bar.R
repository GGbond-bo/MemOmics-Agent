# GO/KEGG Bubble + Bar Combined Plot (Publication-Grade)
# =============================================================================
# Use case: 2-15 enrichment entries across GO (BP/CC/MF) + KEGG, per subcluster
# When to use combined plot: entries ≤ 15 total, gene counts similar across categories
# When to facet: entries > 15 OR gene counts wildly different (e.g. KEGG 200+ vs GO CC 5)
# =============================================================================

library(readxl)
library(dplyr)
library(stringr)
library(ggplot2)

# --- 1. Data import & category mapping ---
raw <- read_excel("input.xlsx", sheet = "Sheet1")
colnames(raw) <- c("Category", "Description", "Hits", "neg_log_q", "Subcluster")

raw <- raw %>%
  mutate(Category = case_when(
    Category == "GO Biological Processes" ~ "BP",
    Category == "GO Cellular Components"  ~ "CC",
    Category == "GO Molecular Functions"  ~ "MF",
    Category == "KEGG Pathway"            ~ "KEGG",
    TRUE ~ Category
  ))

# --- 2. Processing function ---
process_data <- function(df, sub_name) {
  df %>%
    mutate(
      GeneCount = str_count(Hits, "\\|") + 1,
      Top10Genes = sapply(Hits, function(x) {
        genes <- unlist(strsplit(as.character(x), "\\|"))
        paste(head(genes, 10), collapse = "/")
      }),
      Category = factor(Category, levels = c("BP", "CC", "MF", "KEGG")),
      Description = ifelse(nchar(Description) > 55,
                           paste0(substr(Description, 1, 52), "..."),
                           Description)
    ) %>%
    group_by(Category) %>%
    arrange(desc(neg_log_q), .by_group = TRUE) %>%
    ungroup() %>%
    mutate(
      sort_index = row_number(),
      Description = factor(Description, levels = rev(unique(Description)))
    )
}

# --- 3. Plot function ---
make_bubble_bar_plot <- function(df, sub_name, out_path) {
  df$y_num <- as.numeric(df$Description)
  
  cat_ranges <- df %>%
    group_by(Category) %>%
    summarise(
      y_min = min(y_num) - 0.4,
      y_max = max(y_num) + 0.4,
      y_mid = mean(y_num),
      .groups = 'drop'
    )
  
  colors_scheme <- c(
    "BP"   = "#5B9BD5",
    "CC"   = "#63B5A0", 
    "MF"   = "#88C4E8",
    "KEGG" = "#E8836E"
  )
  
  x_max_bar <- max(df$neg_log_q) * 1.5
  size_range <- c(4, 14)
  
  p <- ggplot(df, aes(y = Description)) +
    # Left category blocks
    geom_rect(
      data = cat_ranges,
      aes(xmin = -3.5, xmax = -2.5, ymin = y_min, ymax = y_max, fill = Category),
      inherit.aes = FALSE, alpha = 0.88
    ) +
    geom_text(
      data = cat_ranges,
      aes(x = -3.0, y = y_mid, label = Category),
      inherit.aes = FALSE, size = 3.8,
      color = "white", fontface = "bold", angle = 90
    ) +
    # Bubbles (no gene count label inside — size + legend suffices)
    geom_point(
      aes(x = -1.3, size = GeneCount, fill = Category),
      shape = 21, color = "grey30", stroke = 0.4
    ) +
    # Bars
    geom_bar(
      aes(x = neg_log_q, fill = Category),
      stat = "identity", width = 0.65, alpha = 0.85
    ) +
    # Pathway names
    geom_text(
      aes(x = 0.15, label = Description),
      hjust = 0, size = 3.6, color = "grey20", fontface = "bold"
    ) +
    # Gene list (dynamic positioning at bar end)
    geom_text(
      aes(x = neg_log_q + 0.2, label = Top10Genes, color = Category),
      hjust = 0, vjust = 0.5, size = 2.3, show.legend = FALSE
    ) +
    scale_fill_manual(
      values = colors_scheme, name = "Category",
      labels = c("BP"="Biological Process", "CC"="Cellular Component",
                 "MF"="Molecular Function", "KEGG"="KEGG Pathway")
    ) +
    scale_color_manual(values = colors_scheme) +
    scale_size_continuous(
      range = size_range, name = "Gene Count",
      breaks = pretty(df$GeneCount, n = 4)
    ) +
    scale_x_continuous(
      expand = expansion(mult = c(0.02, 0.30)),
      limits = c(-4.0, NA)
    ) +
    # Category separator lines
    geom_hline(
      yintercept = c(head(cat_ranges$y_max, -1) + 0.1),
      linetype = "dashed", color = "grey80", linewidth = 0.3
    ) +
    theme_minimal(base_size = 11) +
    theme(
      plot.background  = element_rect(fill = "transparent", color = NA),
      panel.background = element_rect(fill = "transparent", color = NA),
      axis.title.x     = element_text(size = 12, face = "bold", margin = margin(t = 8)),
      axis.title.y     = element_blank(),
      axis.text.y      = element_blank(),
      axis.text.x      = element_text(size = 9, color = "grey30"),
      axis.line.x      = element_line(linewidth = 0.6, color = "grey40"),
      panel.grid.major.x = element_line(color = "grey92", linewidth = 0.35),
      panel.grid.major.y = element_blank(),
      panel.grid.minor   = element_blank(),
      legend.position  = "right",
      legend.title     = element_text(size = 9, face = "bold"),
      legend.text      = element_text(size = 8),
      legend.key.size  = unit(0.6, "cm"),
      plot.margin      = margin(15, 10, 15, 10),
      plot.title       = element_text(size = 14, face = "bold", hjust = 0.5, margin = margin(b = 10))
    ) +
    labs(
      x = expression(-log[10](q-value)),
      title = paste0("GO & KEGG Enrichment — ", sub_name)
    )
  
  # Transparent PDF
  ggsave(out_path, plot = p, device = "pdf",
         width = 12, height = max(5, nrow(df) * 0.55 + 2),
         bg = "transparent")
}

# --- 4. Run per subcluster ---
for (sub in c("RSS", "SMF")) {
  sub_df <- raw %>%
    filter(Subcluster == sub) %>%
    process_data(sub)
  make_bubble_bar_plot(sub_df, sub, paste0("GO_KEGG_", sub, ".pdf"))
}
