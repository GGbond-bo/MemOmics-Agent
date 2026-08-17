# Common Assay Layout Templates

Pre-configured layout patterns for frequently used assay types. Use `load_example_experiment()` with the corresponding template name, or adapt these patterns for custom experiments.

---

## 1. Dose-Response Assay (96-well)

**Template:** `dose_response_96`

**Typical setup:**
- 2-3 compounds × 6-8 concentrations
- 3 replicates per concentration
- Positive control (e.g., staurosporine for viability)
- Negative control (vehicle, e.g., DMSO)
- Blank wells (medium only)

**Key considerations:**
- **Randomize dose positions:** Don't place doses in sequential columns (confounds dose with column)
- **Edge strategy:** "controls_only" recommended — place controls in outer ring
- **DMSO normalization:** Vehicle (0.1% DMSO) wells should be distributed, not clustered
- **Serial dilution direction:** If pipetting serial dilutions column-wise, balance by randomizing which column each concentration appears in

**Recommended method:** `osat_spatial` — ensures even spatial distribution of each concentration

---

## 2. qPCR Plate (96-well)

**Template:** `qpcr_96`

**Typical setup:**
- 4-8 gene targets (including 2 housekeeping genes)
- 2 conditions (treated vs. control)
- 3 technical replicates per gene/condition
- NTC (No Template Control) for each primer pair

**Key considerations:**
- **Technical replicates:** 3 wells per gene/condition (averaged before analysis)
- **NTCs:** One per primer pair, placed in different positions across the plate
- **Edge strategy:** "include" usually acceptable for qPCR (sealed plates, short reads)
- **Inter-run calibrator:** Include if comparing across plates
- **Standard curve:** If quantitative, dedicate one column or use separate plate

**Recommended method:** `block_random` — simpler layout, technical replicates grouped for pipetting efficiency

**Important:** qPCR technical replicates on the same plate are NOT biological replicates. The biological replicate is the RNA extraction/cDNA synthesis. Average Ct values across technical replicates before calculating ΔΔCt.

---

## 3. ELISA / Immunoassay (96-well)

**Typical setup:**
- Standard curve: 6-8 concentrations × 2 replicates
- Samples: variable number × 2 replicates
- Positive and negative controls
- Blank (substrate only)

**Key considerations:**
- **Standard curve placement:** Distribute across the plate (not just column 1-2) to capture positional variation
- **Edge strategy:** "controls_only" — edge wells ideal for blanks and extreme standard concentrations
- **Sample replicates:** Place duplicates in different plate regions, not adjacent wells
- **Wash artifacts:** Consider plate washer flow direction (row vs. column)

**Recommended method:** `osat_spatial` — ensures standard curve points cover plate geography for better normalization

---

## 4. Cell Viability / Cytotoxicity Screen (384-well)

**Template:** `cell_viability_384`

**Typical setup:**
- 8-16 compounds × 3 concentrations (high, mid, low)
- 4 replicates per compound/concentration
- Positive control (cytotoxic agent)
- Negative control (vehicle)
- Blanks (medium, no cells)

**Key considerations:**
- **Edge strategy:** "empty" strongly recommended — 384-well plates have severe edge effects
- **Interleaved controls:** Place controls throughout the plate, not just corners
- **Z'-factor validation:** Need positive and negative controls on every plate for QC
- **Incubation time sensitivity:** Longer incubations amplify edge effects

**Recommended method:** `osat_spatial` with `max_iter = 2000` — more iterations needed for 384-well optimization

---

## 5. Simple Two-Group Comparison (96-well)

**Template:** `simple_96`

**Typical setup:**
- 2 conditions (treatment vs. control)
- 6+ replicates per condition (biological, across plates)
- 3 technical replicates per biological replicate per plate
- Positive, negative, and blank controls

**Key considerations:**
- **Biological replicates:** Each plate represents one biological replicate
- **Technical replicates:** 3 wells per condition per plate (averaged)
- **Edge strategy:** "controls_only" is a safe default
- **Blocking:** If running multiple plates, balance conditions across plate positions

**Recommended method:** `block_random` — simple and effective for 2-group designs

---

## Choosing the Right Template

| Assay Type | Template | Plate | Edge Strategy | Method |
|-----------|----------|-------|---------------|--------|
| Drug dose-response | `dose_response_96` | 96 | controls_only | osat_spatial |
| qPCR ΔΔCt (ratiometric) | `qpcr_96` | 96 | include | block_random or osat_spatial |
| Cell viability screen | `cell_viability_384` | 384 | empty | osat_spatial |
| Simple comparison | `simple_96` | 96 | controls_only | block_random |
| Custom | `define_experiment()` | Any | User choice | User choice |
