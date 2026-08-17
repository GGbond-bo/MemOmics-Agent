# CRE Conservation Beginner Quickstart

> For users who say "我是小白" or "I'm new to CRE." Start here.

## The 5-Minute Mental Model

Think of your genome as a 46-volume encyclopedia set (chromosomes). Each volume has thousands of articles (genes). But you don't read every article in every cell — that would be chaos.

**CREs are the sticky notes** that say things like:
- "Open to page 742 — this neuron needs SOX2 right now!" → **Enhancer**
- "Start reading here for the BDNF gene" → **Promoter**
- "Skip this section — not needed in this cell" → **Silencer**
- "Don't let the sticky note from page 200 affect page 500" → **Insulator**

## The 3 Technologies You Need to Know

| Technology | What It Detects | The Intuition |
|------------|----------------|---------------|
| **ATAC-seq** | Open vs closed chromatin | Like scanning a book to see which pages have bookmarks |
| **ChIP-seq** | Specific protein binding (H3K27ac = "active enhancer") | Like highlighting all sticky notes written in red ink |
| **Hi-C** | Which DNA regions touch in 3D | Like a map of which pages are dog-eared together |

## The 3 Pre-Computed Scores (Just Look Them Up)

| Score | Database | What It Tells You |
|-------|----------|-------------------|
| **phastCons** | UCSC Table Browser | "How conserved is this base across 46+ species?" 0=not conserved, 1=ultra-conserved |
| **GERP** | UCSC / Ensembl | "Is this base evolving slower than neutral?" >2 = constrained |
| **LiftOver chain** | UCSC Downloads | "Where does this position in human map to in monkey?" |

**You never calculate these from scratch.** They exist in databases.

## Your First Analysis (Copy-Paste Recipe)

### Step 1: Get human brain ATAC-seq peaks
```bash
# Download from ENCODE (example — actual accession varies by brain region)
wget https://www.encodeproject.org/files/ENCFFXXXXXX/@@download/ENCFFXXXXXX.bed.gz
gunzip ENCFFXXXXXX.bed.gz
```

### Step 2: Get monkey brain ATAC-seq peaks
```bash
# From GEO — search for "macaque brain ATAC-seq"
# Or use Meng 2026 Nat Commun supplementary data
```

### Step 3: Liftover monkey peaks to human
```bash
# Download chain file from UCSC
wget http://hgdownload.soe.ucsc.edu/goldenPath/rheMac10/liftOver/rheMac10ToHg38.over.chain.gz
gunzip rheMac10ToHg38.over.chain.gz

# Run liftOver
liftOver monkey_peaks.bed rheMac10ToHg38.over.chain monkey_on_human.bed unmapped.bed
```

### Step 4: Find orthologous CRE pairs
```bash
# Intersect lifted monkey peaks with human peaks
bedtools intersect -a monkey_on_human.bed -b human_peaks.bed -wa -wb -f 0.5 -r > orthologous_pairs.bed
```

### Step 5: Query phastCons for each pair
```python
# Python snippet using UCSC REST API
import requests
for chrom, start, end in orthologous_pairs:
    url = f"https://api.genome.ucsc.edu/getData/track?genome=hg38;track=phastCons100way;chrom={chrom};start={start};end={end}"
    r = requests.get(url)
    score = r.json()['phastCons100way']['mean']
```

That's it — you now have L1 sequence conservation for every CRE pair. L2-L4 build on this foundation.

## Common Beginner Mistakes

1. **Mixing genome builds**: hg38 ≠ GRCh38 (subtly different). Pick ONE and stick to it.
2. **Wrong LiftOver direction**: monkey→human uses rheMac10ToHg38.chain; human→monkey uses hg38ToRheMac10.chain.
3. **Thinking you need to calculate phastCons**: You don't. UCSC has done the multispecies alignment for you.
4. **Expecting perfect matches**: A CRE with 70% sequence identity is actually very good for human-monkey comparison (~25 Mya divergence).
