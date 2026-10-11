# Microplate Experimental Design Principles

This reference covers the key concepts every researcher should understand before designing a microplate experiment. The agent should read this and explain relevant concepts to users as they make layout decisions.

---

## 1. Edge Effects

**What they are:** Wells at the outer edges of microplates often behave differently from interior wells due to uneven evaporation, temperature gradients, and surface tension effects.

**Why they matter:** Edge effects are one of the most common sources of systematic bias in plate-based experiments. Studies show outer wells can have 10-30% higher evaporation rates, leading to concentration artifacts that confound treatment effects.

**Causes:**
- **Evaporation:** Outer wells lose more liquid to evaporation, concentrating reagents and cells
- **Temperature gradients:** Plate edges reach incubator temperature faster than the center, creating uneven heating during equilibration
- **Meniscus effects:** Surface tension at plate edges differs from interior wells
- **CO2/humidity gradients:** Uneven gas exchange across the plate surface

**Mitigation strategies (in order of protection):**

| Strategy | Protection | Usable Wells (96-well) | When to Use |
|----------|-----------|----------------------|-------------|
| Empty outer wells + medium | Highest | 60 of 96 (62%) | Critical assays, long incubations |
| Controls in edge wells only | High | 60 for samples + 36 for controls | Most assays (recommended default) |
| All wells used, randomized | Moderate | All 96 | When every well is needed |

**Practical tips:**
- Fill empty edge wells with medium or PBS to reduce evaporation gradients
- Use plate sealers or humidified chambers for long incubations (>24h)
- Include edge wells in normalization (b-score method) if they must contain samples
- For 384-well plates, consider leaving 2 rows/columns empty (not just 1)

---

## 2. Experimental Units vs. Observations

**The key distinction:** An experimental unit is the smallest entity that receives a treatment independently. Wells within the same plate from the same cell batch are NOT independent experimental units — they are technical replicates (observations) of a single experimental unit.

**Example:** If you seed 6 wells from the same cell passage on the same plate and treat 3 with drug and 3 with vehicle:
- **Experimental unit:** The plate/passage (n=1, NOT n=3)
- **Observations:** 3 measurements per condition (averaged for analysis)
- **True replicates:** Repeating the experiment on different days/passages (n = number of days)

**Why this matters:** Treating technical replicates as independent samples inflates your sample size, leading to falsely significant results (pseudoreplication). This is the single most common statistical error in plate-based biology.

**Test for independence:** Ask: "If I repeated this measurement, would I get a materially different result?" If cells come from the same passage, seeded on the same day, treated with the same reagent batch — no, the measurements are intrinsically linked.

---

## 3. Independent Replicates

**What makes a replicate independent:**
- Different cell passage numbers
- Different preparation dates
- Different reagent lots (when relevant)
- Different animals or patient samples

**What does NOT make a replicate independent:**
- Duplicate wells on the same plate (technical replicates)
- Multiple plates from the same cell batch on the same day
- Re-reading the same plate at different times

**Recommended approach:**
1. Run the experiment on 3+ independent days (biological replicates)
2. Include 2-3 technical replicates per condition per day (for precision)
3. Average technical replicates within each biological replicate
4. Analyze with n = number of biological replicates

**Blocking strategy:** Use day/passage/batch as a blocking factor in your design:
- Block 1: Passage 15, Day 1
- Block 2: Passage 16, Day 2
- Block 3: Passage 17, Day 3

Each block should contain all treatments on a single plate to control for day-to-day variation.

---

## 4. Randomization

**Why randomize:** Systematic well assignment (e.g., all treatment in rows A-D, all control in rows E-H) confounds treatment with position. Any row-dependent artifact becomes indistinguishable from the treatment effect.

**What can go wrong without randomization:**
- Row effects from sequential pipetting (first rows may have slightly different volumes)
- Column effects from multichannel pipette calibration
- Temperature/evaporation gradients aligned with treatment boundaries
- Time-dependent effects (wells filled first vs. last)

**Randomization methods available in this skill:**

| Method | How It Works | Best For |
|--------|-------------|----------|
| **OSAT + Spatial** | Optimizes even distribution across plate positions | Default for most experiments |
| **Block Random** | Randomly assigns within spatial blocks | Simple experiments |
| **Latin Square** | Each treatment appears once per row and column | When row/column effects are expected |

**Critical rule:** Even with randomization, NEVER analyze wells as independent replicates if they share the same biological source. Randomization prevents positional confounding; it does not create statistical independence.

---

## 5. Covariate Balancing

**What it means:** Ensuring that variables other than treatment (covariates) are evenly distributed across plate positions to prevent confounding.

**Common covariates to balance:**
- Cell passage number (across plates in multi-plate experiments)
- Sample source (e.g., patient, mouse)
- Processing batch (reagent lots, operator)
- Time of processing (morning vs. afternoon)

**Example of confounding:** If all passage-15 samples are on Plate 1 and all passage-20 samples are on Plate 2, you cannot distinguish passage effects from plate effects.

**The OSAT approach (used by `designit`):** Optimal Sample Assignment Tool scoring minimizes the chi-square statistic between the observed and expected distribution of covariates across plates/positions. Higher priority variables are optimized first.

---

## 6. Control Placement

**Why control placement matters:** Controls serve two purposes:
1. **Quality control:** Verify the assay worked (positive/negative controls)
2. **Normalization:** Correct for plate-to-plate and position-dependent variation

**Poor control placement:** Placing all controls in columns 1 and 12 (a common default) only detects column-dependent effects. It misses row gradients, bowl-shaped effects, and diagonal patterns.

**Optimal control placement:**
- Distribute controls across all four quadrants of the plate
- Include controls in both edge and interior wells (when using the "include" edge strategy)
- Place positive and negative controls in separate well positions (not adjacent)
- Ensure enough controls per quadrant for statistical normalization (minimum 2 per quadrant for 96-well)

**Control types:**

| Control Type | Purpose | Typical Count (96-well) |
|-------------|---------|----------------------|
| Positive control | Maximum signal (assay worked) | 4-8 wells |
| Negative control | Baseline signal (vehicle/DMSO) | 4-8 wells |
| Blank | Background (no cells/medium only) | 4 wells |
| Standard curve | Quantitation reference | 6-8 concentrations × 2 replicates |
| NTC (qPCR) | No-template control | 1 per primer pair |

---

## 7. Pseudoreplication

**Definition:** Treating non-independent observations as independent replicates, artificially inflating sample size and statistical significance.

**The most common form in plate experiments:**

> "We treated 3 wells with drug and 3 wells with vehicle on a single plate and performed a t-test with n=3."

This is pseudoreplication because all 6 wells come from the same cell batch/passage. The true sample size is n=1 (one experimental unit per group).

**Single-plate limitation:** With a single plate, the biological n for each treatment is 1, regardless of having 20 technical replicate wells. Power analysis using well counts estimates *technical* power (ability to detect differences given measurement noise), not *biological* power (ability to detect true biological effects across independent experiments). Multi-plate experiments with independent cell preparations on different days provide true biological replication — each plate/day constitutes one biological replicate.

**How to avoid it:**
1. **Plan biological replicates:** Repeat the experiment on independent days/passages
2. **Average technical replicates:** Combine within-plate measurements into a single value per biological replicate
3. **Use the right n:** Analyze with n = number of independent experiments, not wells
4. **Report correctly:** State both technical and biological replicate counts

**Red flags for reviewers:**
- n > 10 with only 1-2 experimental dates
- Statistical tests on well-level data without blocking
- No mention of biological replicates in methods

---

## References

- Murphy TJ. "Sampling and experimental units." *Just a Biostatistics Textbook*. [Link](https://tjmurphy.github.io/jabstb/sampling.html)
- Wollmann et al. (2023). "Designing microplate layouts using artificial intelligence." *SLAS Discovery* 28(3):111-117. [DOI](https://doi.org/10.1016/j.slasd.2023.02.004)
- Assay Guidance Manual: "Microplate Selection and Recommended Practices." NCBI Bookshelf. [Link](https://www.ncbi.nlm.nih.gov/books/NBK558077/)
- Borbouse H et al. (2021). "Well Plate Maker: a user-friendly randomized block design application." *Bioinformatics* 37(17):2770-2772.
- Lazic SE (2010). "The problem of pseudoreplication in neuroscientific studies." *BMC Neuroscience* 11:5.
