# Custom Genome for Non-UCSC Organisms (NCBI Chromosome Naming)

## When This Applies

Your Arrow files contain NCBI-style chromosome names (e.g. `NC_088375.1` instead of `chr1`).
This happens with:
- Non-human, non-mouse species (macaque, rat, zebrafish, etc.)
- T2T / complete assemblies that use RefSeq accession numbers
- Any assembly where the fragment file used NCBI naming during `createArrowFiles`

## Symptom

- `addTileMatrix()` → clear error: `Chromosome chr1 not in ArrowFile! Available Chromosomes are : NC_088375.1,NC_088376.1,...`
- `addGroupCoverages()` → **silent crash** with exit_code=1 after partial completion (e.g. 21/57 groups done, no error message in log)
- `addArchRGenome("hg38")` / `addArchRGenome("mm10")` → no error when called, but all downstream functions fail

## Root Cause

`addArchRGenome("hg38")` builds a genome annotation with UCSC names (chr1-chr22, chrX, chrY).
ArchR functions look for these names in the Arrow files. If the Arrow files use NCBI names, lookup fails.

## Fix: Build Custom Genome Annotation Manually

**Do NOT use `createGenomeAnnotation(genome="MyAssembly")`** — it searches for a matching BSgenome package.

### Step 1: Extract Chromosome Sizes from Arrow Files (Python)

```python
import h5py, json
af = r"path/to/sample.arrow"
chrom_sizes = {}
with h5py.File(af, 'r') as f:
    if 'TileMatrix' in f:
        for p in f['TileMatrix']['Info']['Params']:
            chrom_sizes[p[0].decode('utf-8')] = int(p[1])
with open("chrom_sizes.json", 'w') as fp:
    json.dump(chrom_sizes, fp, indent=2)
```

### Step 2: Build Custom Annotation in R

```r
library(ArchR); library(GenomicRanges)
chrom_sizes <- c("NC_088375.1"=234122563, "NC_088376.1"=203129947, ...)
chrom_gr <- GRanges(seqnames=names(chrom_sizes), ranges=IRanges(start=1, end=chrom_sizes))
names(chrom_gr) <- names(chrom_sizes)

# Build as SimpleList directly (NOT createGenomeAnnotation — needs BSgenome)
genomeAnnotation <- SimpleList(genome="CustomAssembly", chromSizes=chrom_gr, blacklist=GRanges())
geneAnnotation <- SimpleList(genome="CustomAssembly", genes=GRanges(), exons=GRanges(), TSS=GRanges())

# Replace in project
proj <- readRDS("project.rds")
proj@genomeAnnotation <- genomeAnnotation
proj@geneAnnotation <- geneAnnotation
proj <- addTileMatrix(proj, tileSize=500, force=TRUE)
```

## Important: Already-Existing Matrices in Arrow Files

Arrow HDF5 may already contain TileMatrix/PeakMatrix/GeneScoreMatrix from previous sessions.
Check with `list(f['TileMatrix'].keys())`. After fixing genome, `addTileMatrix(force=TRUE)` will regenerate.

## Macaque T2T Reference (NC_088375.1–NC_088395.1)

Maps to Macaca mulatta chr1-20+X. Full table in reference file.

## Pitfalls

1. **createGenomeAnnotation looks for BSgenome** — don't use for custom assemblies. Build SimpleList directly.
2. **Empty geneAnnotation is fine for TileMatrix/diff** — only needed for peak annotation (ChIPseeker).
3. **addGroupCoverages silent crash vs addTileMatrix clear error** — always test with addTileMatrix first.
4. **chromSizes must match Arrow file exactly** — one extra/missing chromosome breaks all functions.
