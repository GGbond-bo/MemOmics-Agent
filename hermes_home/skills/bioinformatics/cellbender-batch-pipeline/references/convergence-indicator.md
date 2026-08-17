# Convergence Indicator — Official Source Code Interpretation

## Source
`cellbender/remove_background/run.py` lines 501-504 (CellBender v0.3.2)

## Formula

```python
convergence_indicator = (
    np.mean(|ELBO_last_2_step_changes|)  # numerator: avg step-to-step change over last 3 epochs
    /
    np.std(ELBO_last_20_steps)            # denominator: std of last 20 epochs
)
```

In plain English: **recent wobble ÷ overall wobble**.

## Interpretation

| Value | Meaning |
|-------|---------|
| **< 1** | Recent changes smaller than overall noise → model stabilized → ✅ EXCELLENT |
| **1-5** | Recent changes within normal fluctuation range → model basically stable → 🟡 ACCEPTABLE |
| **> 5** | Recent changes far exceed overall noise → model still in significant adjustment → 🔴 NOT CONVERGED, more epochs needed |

## Why 5?

This follows from statistical Z-score logic: if |ELBO change| > 5× std, it's an extreme outlier. The threshold 5 is from statistical convention, not an explicit CellBender team specification.

## Verification (2026-07-29, 6 brain samples)

| Sample | Value | Verdict |
|--------|:-----:|---------|
| 2309H_3 | 0.27 | ✅ Excellent |
| 3506H_2 | 0.67 | ✅ Good |
| 3506H_1 | 0.74 | ✅ Good |
| 3506H_4 | 1.11 | 🟡 Acceptable |
| 3506H_3 | 1.18 | 🟡 Acceptable |
| 2309H_4 | 1.86 | 🟡 Acceptable |

All < 5 — all converged properly.

## Important

The official CellBender tutorial (`cellbender_tutorial.ipynb`) only demonstrates running through, does not discuss convergence_indicator interpretation. This metric exists only in source code `run.py`, with no standalone documentation page.
