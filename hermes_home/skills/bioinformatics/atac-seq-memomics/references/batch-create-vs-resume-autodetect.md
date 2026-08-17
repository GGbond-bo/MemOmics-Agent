# Batch Orchestration: Auto-Detect Create vs Resume

> Session: memomics-1135ed52 (2026-08-07, GSE278576 40-sample ArchR batch)
> 9/40 failed: resume_p2p3.R ran on samples without Arrow files

## The Problem

Batch orchestrators often use one execution path for all samples. But samples may be in different states — some need full Arrow creation (P1), some need doublet filtering only (P2+P3), some are complete.

**Symptom**: 9 samples (hc12/hc11/hc73/hc19/hc26/hc40/hc212191/hc35/hc9) all failed instantly with `stop("Arrow not found")` because the batch ran `resume_p2p3.R` on samples that never had Arrows created.

## The Fix: Per-Sample Status Check Before Batch Launch

```bash
for sample in $ALL_SAMPLES; do
  ARROW="ArchR_Arrow_QC/${sample}.arrow"
  CSV="ArchR_Arrow_QC_Filtered/${sample}/${sample}_filtered_cells.csv"

  if [ -f "$CSV" ]; then
    echo "SKIP $sample"
  elif [ -f "$ARROW" ]; then
    echo "RESUME $sample" && Rscript resume_p2p3.R "$sample"
  else
    echo "CREATE $sample" && Rscript create_arrow_qc.R "$sample"
  fi
done
```

## Decision Table

| Arrow? | Filtered CSV? | Action |
|:---:|:---:|---|
| ❌ | ❌ | Full P1+P2+P3 via `create_arrow_qc.R` |
| ✅ | ❌ | P2+P3 only via `resume_p2p3.R` |
| ✅ | ✅ | Skip |

## Post-Batch Validation

For each sample verify 4 artifacts:
- `ArchR_Arrow_QC/{sample}.arrow` (exists, size > 0)
- `ArchR_Arrow_QC/{sample}_result.csv` (contains n_keep)
- `ArchR_Arrow_QC_Filtered/{sample}/{sample}.arrow`
- `ArchR_Arrow_QC_Filtered/{sample}/{sample}_filtered_cells.csv`

Missing any → add to `remaining.txt` → rerun auto-detect loop (idempotent).

## Why Concurrency Must Be 1

ArchR 1.0.3 Windows: `createArrowFiles` instances share `outputDirectory/tmp/`. Multi-instance → temp file collision → 5/7 failure. RAM is irrelevant.
