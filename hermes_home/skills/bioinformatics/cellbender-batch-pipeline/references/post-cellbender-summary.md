# Post-CellBender Summary Table Generation

## When to Use

After all CellBender samples complete, generate a before/after comparison table from the `*_metrics.csv` files.

## Data Source

Each sample directory contains `{sample}_raw_output_metrics.csv` with these key fields:

| Metric | Meaning |
|--------|---------|
| `total_raw_counts` | Total UMI counts in input |
| `total_output_counts` | Total UMI counts after background removal |
| `total_counts_removed` | UMIs removed as ambient RNA |
| `fraction_counts_removed` | % of UMIs removed |
| `found_cells` | Number of cells detected |
| `found_empties` | Droplets classified as empty (out of 25,000 analyzed) |
| `expected_cells` | CellBender's initial cell count estimate |
| `convergence_indicator` | < 5 = normal convergence |
| `output_average_counts_per_cell` | Mean UMI per cell after cleanup |
| `average_counts_removed_per_cell` | Mean ambient UMI removed per cell |
| `overall_change_in_train_elbo` | Training convergence metric |

## Extraction Script

```python
from hermes_tools import terminal
import json

samples = ["2309H_3", "2309H_4", "3506H_1", "3506H_2", "3506H_3", "3506H_4"]
base = "PROJECT_DATA_DIR/cellbender_output"

for s in samples:
    metrics_path = f"{base}/{s}/{s}_raw_output_metrics.csv"
    result = terminal(f"cat \"{metrics_path}\"", timeout=5)
    # Parse lines: "metric_name,value"
    for line in result["output"].strip().split("\n"):
        if not line.startswith("Metric"):
            print(f"{s},{line}")
```

## Summary Table Template

### UMI Counts (before → after)

| Sample | Raw UMI | Removed | Retained | % Removed |
|--------|--------:|--------:|---------:|:---:|
| ... | ... | ... | ... | ... |
| **Total** | **sum** | **sum** | **sum** | **avg%** |

### Cell Detection (25,000 droplets analyzed)

| Sample | Expected | Found Cells | Empty | Cell % | Verdict |
|--------|:---:|:---:|:---:|:---:|:---:|
| ... | ... | ... | ... | ... | ✅/⚠️ |

### Per-Cell Metrics

| Sample | Pre Mean UMI | Post Mean UMI | Removed/Cell | Convergence |
|--------|:---:|:---:|:---:|:---:|
| ... | ... | ... | ... | ... |

## Red Flags to Flag

| Signal | Threshold | Interpretation |
|--------|-----------|----------------|
| `fraction_counts_removed` > 25% | Too aggressive | May be removing real signal; check `--fpr` |
| `fraction_counts_removed` < 3% | Too conservative | May not be removing enough ambient RNA |
| Empty droplets > 50% (e.g. 14,000/25,000) | Low cell concentration sample | Not a quality issue — explained by cell count |
| `convergence_indicator` > 5 | Possible non-convergence | Check ELBO trajectory in PDF report |
| `ratio_of_found_cells_to_expected_cells` > 7 | Initial estimate far off | Common for low-cell-concentration samples |

## Output

Save to `{output_dir}/summary/CellBender_去除背景汇总表.md` for user review before proceeding to Stage 4 (ptrepack → seurat_h5) or scRNA analysis.
