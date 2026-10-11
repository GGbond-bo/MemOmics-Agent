# Advanced Plate Design Strategies

## Latin Square Designs

**What:** Each treatment appears exactly once in each row and each column. This design controls for both row and column effects.

**When to use:**
- When you suspect both row and column positional effects
- When the number of treatments equals or divides evenly into the number of rows/columns
- When systematic plate effects are a concern

**How it maps to plates:**
- A 4×4 Latin square tiles naturally onto a 96-well plate (8 rows ÷ 4 = 2 tiles vertically, 12 cols ÷ 4 = 3 tiles horizontally)
- For a 384-well plate: 16 rows and 24 columns allow many tiling options

**Limitations:**
- Works best when number of treatments divides plate dimensions evenly
- Does not protect against interaction effects between row and column
- For complex experiments, OSAT + spatial scoring is usually more flexible

**Use in this skill:**
```r
layout <- generate_plate_layout(experiment, method = "latin_square")
```

---

## Blocked Randomization

**What:** Divide the plate into blocks (regions), then randomize within each block. Ensures every treatment appears in every block.

**When to use:**
- When you want balance across plate regions
- When treatments are processed block-by-block (e.g., column-wise pipetting)
- Simpler alternative to full OSAT optimization

**Block definitions for 96-well:**
- 4 quadrants (24 wells each)
- 2 halves (top/bottom or left/right, 48 wells each)
- 8 column-wise blocks (12 wells each)
- 12 row-wise blocks (8 wells each)

**Use in this skill:**
```r
layout <- generate_plate_layout(experiment, method = "block_random")
```

---

## Multi-Plate Experiments

**When experiments span multiple plates:**

### Across-Plate Balancing
Use OSAT scoring to ensure covariates are balanced across plates:
- Each treatment should appear on every plate
- Sample covariates (sex, age group, batch) should be evenly distributed
- Controls should be consistent across plates for normalization

### Within-Plate Optimization
After across-plate assignment, optimize within each plate:
- Spatial scoring prevents clustering of the same treatment
- Controls distributed across quadrants on every plate
- Edge strategy applied consistently

### Multi-plate design:
```r
experiment <- define_experiment(
    plate_format = 96,
    treatments = c("Drug_A", "Drug_B", "Vehicle"),
    n_replicates = 4,
    n_plates = 3,
    controls = list(positive = "MaxSignal", negative = "DMSO"),
    n_controls = list(positive = 4, negative = 4),
    edge_strategy = "controls_only"
)
layout <- generate_plate_layout(experiment, method = "osat_spatial")
```

---

## OSAT + Spatial Scoring (designit)

This is the default and most powerful method. It uses two complementary scoring functions:

1. **OSAT score (across plates):** Minimizes chi-square statistic between observed and expected distribution of treatment groups across plates. Ensures balanced plate assignment.

2. **Spatial score (within plates):** Penalizes same-treatment wells that are close together. Maximizes physical distance between replicates of the same condition.

**Optimization process:**
1. Random initial assignment
2. Iterative swaps (n_shuffle samples swapped per iteration)
3. Accept swaps that improve the combined score
4. Repeat for max_iter iterations

**Tuning parameters:**
- `max_iter`: More iterations = better optimization (default 1000, use 2000+ for 384-well)
- `seed`: Different seeds produce different valid layouts — try a few if quality score is low

---

## Handling Pipetting Constraints

**Column-wise pipetting (multichannel):**
- Multichannel pipettes fill 8 wells at a time (one column)
- All wells in a column receive the same treatment at the same time
- This constrains layouts: an entire column must contain the same reagent

**Row-wise pipetting:**
- Less common but used with some robotic handlers
- Similar constraint: entire row receives the same treatment

**When to accommodate pipetting constraints:**
- Use `manual_template` method for strict column-wise constraints
- Use `block_random` with column-sized blocks for partial column constraints
- For OSAT/spatial methods, pipetting constraints are not enforced — the optimized layout may require single-channel pipetting or a robotic handler

**Practical compromise:** Generate an optimized layout, then adjust manually for pipetting convenience. The quality dashboard will show if adjustments degrade the layout quality.
