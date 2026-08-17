# LIANA L-R Methods Comparison

## Why LIANA-py

LIANA (LIgand-receptor ANAlysis) is a Python framework that wraps multiple L-R inference methods and provides consensus ranking. Using LIANA instead of a single method (e.g., CellPhoneDB alone) reduces method-specific biases.

## Methods Included

| Method | What It Tests | Strengths | Weaknesses |
|--------|--------------|-----------|------------|
| **CellPhoneDB** | Permutation test on mean L-R expression between cell types | Well-validated, accounts for complex subunit interactions | Computationally expensive with many cell types |
| **NATMI** | Edge specificity + expression of L-R pairs | Captures cell-type-specific interactions | May miss ubiquitous signaling |
| **Connectome** | Scaled expression product | Simple, interpretable | No statistical test |
| **log2FC** | Fold-change of L-R expression between cell types | Directly measures cell-type preference | No significance assessment |

## Consensus Ranking

LIANA aggregates across methods using robust rank aggregation (RRA), producing a consensus ranking that is more reliable than any single method. Interactions ranked highly by multiple methods are prioritized.

## Disease vs Control Comparison

For disease drug discovery, we run LIANA separately on:
1. Disease subset (SSc samples only)
2. Control subset (healthy samples only)

Interactions present in disease but absent/weak in control represent disease-specific communication that may be therapeutically targetable.

## Output Interpretation

- **High consensus rank + disease-relevant cell types:** Strong candidate for therapeutic intervention
- **Disease-specific interaction:** Present only in disease, may represent aberrant signaling
- **Multi-method significant:** Robust finding, not method artifact
