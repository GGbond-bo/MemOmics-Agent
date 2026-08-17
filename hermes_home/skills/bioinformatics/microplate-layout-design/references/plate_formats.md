# Microplate Format Specifications

## Supported Formats

| Format | Rows | Columns | Total Wells | Well Volume (typical) | Common Uses |
|--------|------|---------|-------------|----------------------|-------------|
| **96-well** | 8 (A-H) | 12 (1-12) | 96 | 100-300 µL | Most lab assays, qPCR, ELISA |
| **384-well** | 16 (A-P) | 24 (1-24) | 384 | 20-100 µL | HTS, compound screening, qPCR |

## 96-Well Plate

```
     1   2   3   4   5   6   7   8   9  10  11  12
A  [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ]
B  [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ]
C  [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ]
D  [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ]
E  [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ]
F  [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ]
G  [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ]
H  [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ] [  ]
```

**Edge wells (36):** Row A, Row H, Column 1, Column 12
**Interior wells (60):** B2 through G11

### Edge Effect Zones
- **High risk (36 wells):** Outer ring (row 1, row 8, col 1, col 12)
- **Medium risk (20 wells):** Second ring (row 2, row 7, col 2, col 11)
- **Low risk (40 wells):** Interior (rows 3-6, cols 3-10)

## 384-Well Plate

**Edge wells (76):** Row A, Row P, Column 1, Column 24
**Interior wells (308):** B2 through O23

### Edge Effect Zones
- **High risk (76 wells):** Outer ring
- **Medium risk (72 wells):** Second ring
- **Low risk (236 wells):** Interior (rows 3-14, cols 3-22)

### 384-Well Considerations
- Consider leaving 2 rows/columns empty (not just 1) for better edge protection
- Multichannel pipettes fill by column — consider column-wise treatment assignment
- Smaller volumes = higher evaporation sensitivity = more edge effect impact

## Well Naming Convention

Wells are named by row letter + column number:
- `A1` = top-left corner
- `H12` = bottom-right corner (96-well)
- `P24` = bottom-right corner (384-well)

Multi-plate: `P1_A1` = Plate 1, well A1

## Quadrant Definitions (for Control Distribution)

### 96-Well Quadrants
| Quadrant | Rows | Columns | Wells |
|----------|------|---------|-------|
| Q1 (top-left) | A-D | 1-6 | 24 |
| Q2 (top-right) | A-D | 7-12 | 24 |
| Q3 (bottom-left) | E-H | 1-6 | 24 |
| Q4 (bottom-right) | E-H | 7-12 | 24 |

### 384-Well Quadrants
| Quadrant | Rows | Columns | Wells |
|----------|------|---------|-------|
| Q1 (top-left) | A-H | 1-12 | 96 |
| Q2 (top-right) | A-H | 13-24 | 96 |
| Q3 (bottom-left) | I-P | 1-12 | 96 |
| Q4 (bottom-right) | I-P | 13-24 | 96 |
