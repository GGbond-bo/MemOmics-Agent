# Monkey Brain CellBender Run — 2026-07-04

## Context
- **Species**: Macaca mulatta (恒河猴)
- **Tissue**: Brain (脑)
- **Direction**: Aging (衰老)
- **Platform**: DNB (BGI/MGI)
- **Data path**: `E:\monkey\h5ad\` (15 h5ad files from prior conversion)

## Samples Tested

| Sample | Cells | Features | Epochs | Status | Notes |
|--------|-------|----------|--------|--------|-------|
| CRR278961 | 5,876 | 7,624 | 150 | ✅ | OOM at epoch 54, resumed from ckpt epoch 37 |
| CRR278962 | 5,883 | 7,246 | 150 | ✅ | Already had results from prior run |

## Parameters Used
```
--projected-ambient-count-threshold 5
--learning-rate 0.0001
--training-fraction 0.9
--low-count-threshold 20
--epochs 150
--checkpoint-mins 5
--cuda
```

## Environment
- **Conda env**: `cellbender`
- **GPU**: NVIDIA RTX 5070 Ti (16GB VRAM)
- **torch**: 2.12.0+cu132, CUDA available

## Issues Encountered

### 1. Agent didn't trigger skill (CRITICAL)
The user said "进行cellbender" — exact trigger match for this skill. The agent wrote CellBender code from scratch instead of loading the skill via `skill_view()`. This caused:
- Missing the `unset PYTHONPATH` fix (known issue #1)
- Missing the `rm ckpt.tar.gz` before fresh runs (known issue #2)
- Writing redundant conversion code when h5ad files already existed

**Fix applied in SKILL.md**: Added Common Issues entry for this pitfall.

### 2. CRR278962 already had results
The agent started a fresh CellBender run on CRR278962 at epoch 65/150 before the user pointed out the output already existed. Killed the redundant process.

**Fix applied in SKILL.md**: Added pre-flight check — verify output file existence before running.

### 3. CRR278961 OOM + resume
CRR278961 crashed at epoch 54/150 with `numpy._ArrayMemoryError` (system RAM, not GPU). Checkpoint was saved at epoch 37. Resumed successfully — checkpoint auto-detected by CellBender.

**Lesson**: Checkpoint recovery works. The 5-minute checkpoint interval is critical.

### 4. PYTHONPATH pollution
Both runs required `unset PYTHONPATH` before CellBender invocation. Already documented as known issue #1.

### 5. Skill location
This skill lives under `bioinformatics/cellbender-remove-background/` and is the authoritative copy.

## Output Files (per sample)
- `cellbender_output.h5` — raw CellRanger format output
- `cellbender_output_filtered.h5` — filtered (clean) output
- `cellbender_output_metrics.csv` — quality metrics
- `cellbender_output_report.html` — HTML report
- `cellbender_output_cell_barcodes.csv` — cell barcode list
- `cellbender_output.pdf` — PDF report
- `cellbender_output_posterior.h5` — posterior probabilities

## Results Directory
- `E:\monkey\cellbender\CRR278961\`
- `E:\monkey\cellbender\CRR278962\`

Note: User specified `E:\monkey\cellbender\` for this run. Default MemOmics convention is `MEMOMICS_HOME\results/`.