# Human 40-donor → Age/Age_group verified mapping (Zemke GSE278576, verified 2026-08-28)

Source: user-supplied `D:/我的下载/media-2/Supplemental Tables S1-S24/Table_S1.tsv`
(paper supplement for PMID 39463924, bioRxiv DOI 10.1101/2024.10.14.618338)

Selection: keep rows where `Assays` contains `10x multiome` → exactly 40 donors, matching
the 40 unique `Sample` values (`GSM85496xx_hcXX`) in `human_Hf_ATAC_40_clustered.rds`.
All 265,909 cells matched with 0 NA. 4 groups × 10 donors.

## Full donor-age mapping (DonorID → Age)

```
20-40  (10):  78=20, 77=20, 5579=25, 76=26, 29=28, 6052=28, 5614=31, 13344=33, 935=38, 937=38
40-60  (10):  1134=41, 13414=41, 5021=43, 5087=44, 1745=46, 4781=46, 81=48, 5610=50, 5551=54, 6021=55
60-80  (10):  13394=65, 73787=66, 46426=68, 1265=69, 8=69, 1271=71, 1153=75, 1203=75, 69984=75, 1216=79
80-100 (10):  98=82, 12=83, 11=86, 73=86, 19=87, 26=89, 40=89, 212191=89, 35=89, 9=89
```

R code (numerical names MUST be quoted — unquoted `78=` is a parse error):

```r
donor_age <- c(
  "78"=20, "77"=20, "5579"=25, "76"=26, "29"=28, "6052"=28, "5614"=31, "13344"=33,
  "935"=38, "937"=38, "1134"=41, "13414"=41, "5021"=43, "5087"=44, "1745"=46, "4781"=46,
  "81"=48, "5610"=50, "5551"=54, "6021"=55, "13394"=65, "73787"=66, "46426"=68, "1265"=69,
  "8"=69, "1271"=71, "1153"=75, "1203"=75, "69984"=75, "1216"=79, "98"=82, "12"=83,
  "11"=86, "73"=86, "19"=87, "26"=89, "40"=89, "212191"=89, "35"=89, "9"=89
)
donor_num <- as.integer(sub(".*hc([0-9]+).*", "\\1", proj@cellColData$Sample))
ages <- donor_age[as.character(donor_num)]                       # all 265,909 match, 0 NA
age_group <- cut(ages, breaks=c(19,40,60,80,100),
                 labels=c("20-40","40-60","60-80","80-100"), right=FALSE)
proj@cellColData$Age <- ages
proj@cellColData$Age_group <- as.character(age_group)
```

Verified result:
| Age_group | Donors | Cells |
|-----------|--------|-------|
| 20-40  | 10 | 61,798 |
| 40-60  | 10 | 70,124 |
| 60-80  | 10 | 70,335 |
| 80-100 | 10 | 63,652 |

Sandbox note: cannot write to `E:/专利/patent` (outside MEMOMICS_ALLOWED_WRITE_ROOTS);
save to `results/<sid>/` and hand user a local write-back script.

Monkey side already has in-rds `Age` (5-31) + `Age_group` (Young/Middle/Old/Exceptionally old), 21 individuals, 63 libs — no work needed.