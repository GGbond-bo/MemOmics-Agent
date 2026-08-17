# ATAC-seq Troubleshooting Guide

## Common Issues

### 1. MACS2 Not Found
**Error**: 
**Fix**: Collecting MACS2
  Downloading MACS2-2.2.9.1.tar.gz (2.0 MB)
     ---------------------------------------- 2.0/2.0 MB 2.5 MB/s  0:00:00
  Installing build dependencies: started
  Installing build dependencies: finished with status 'done'
  Getting requirements to build wheel: started
  Getting requirements to build wheel: finished with status 'error' or 3 channel Terms of Service accepted
Retrieving notices: - \ | / - done
Collecting package metadata (repodata.json): | failed

### 2. Arrow File Creation Fails
**Error**: 
**Fix**: Check fragment file format: chr, start, end, barcode, reads
**Fix**: Ensure file is gzipped (.tsv.gz)

### 3. Out of Memory (Large Datasets)
**Error**: R session crashes during LSI
**Fix**: Reduce  from 25000 to 15000
**Fix**: Use  parameter in addClusters
**Fix**: Increase  but decrease per-thread memory

### 4. TSS Enrichment Too Low
**Symptom**: Most cells filtered, <50% remain
**Fix**: Lower  from 8 to 4
**Fix**: Check TSS enrichment profile (should peak at 0)
**Fix**: Verify reference genome matches data

### 5. Too Many Clusters (>30)
**Symptom**: Clustering produces fragmented clusters
**Fix**: Lower resolution from 0.8 to 0.4-0.6
**Fix**: Increase LSI components (30 -> 20) to reduce noise
**Fix**: Check batch effects (Harmony may not have converged)

### 6. Harmony Convergence Warning
**Error**: 
**Fix**: Increase max.iter (default 10 -> 20)
**Fix**: Check if batch variable has too many levels (>10 samples)

### 7. No Peaks Called
**Symptom**: addReproduciblePeakSet returns 0 peaks
**Fix**: Check MACS2 installation
**Fix**: Lower q-value cutoff (0.05 -> 0.1)
**Fix**: Ensure genome annotation is set correctly

### 8. chromVAR Motif Deviation All Zero
**Symptom**: MotifMatrix has no variation
**Fix**: Ensure background peaks are added (addBgdPeaks)
**Fix**: Check motif annotations match genome
