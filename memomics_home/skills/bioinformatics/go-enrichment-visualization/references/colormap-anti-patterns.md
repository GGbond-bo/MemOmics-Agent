# Colormap Anti-Patterns for CNS Enrichment Heatmaps

## Never use these for GO enrichment heatmaps

| Anti-pattern | Why it fails | User reaction |
|---|---|---|
| `plt.cm.Reds` / `plt.get_cmap('Reds')` | Low end is grayish/brownish, not pure white | "全都是蓝色" — gray looks blue-ish |
| `RdBu` / `RdYlBu` diverging | Contains explicit blue tones | "原图哪有蓝色" |
| Any sequential colormap starting with dark color | Inverted perception — high values look low | "质量差到爆炸" |
| `viridis` / `plasma` / `inferno` | Non-monochromatic, no red at all | Completely wrong style |
| `seismic` / `coolwarm` | Diverging with blue | Same as RdBu |

## Always use custom pure-red gradient

```python
# 6-stop pure red (white → dark red, ZERO blue component)
colors = ['#FFFFFF', '#FFD4D4', '#FF8888', '#FF4444', '#CC0000', '#800000']
cmap = LinearSegmentedColormap.from_list('cns_pure_red', colors, N=256)
norm = Normalize(vmin=0, vmax=10)  # clip at 10, not raw max
```

## Color verification checklist

After generating, verify with `vision_describe`:
- ✅ Main color is `#e0e0e0` (white/gray background) + red tones
- ❌ Any `#c0c0e0` or `#c0e0c0` = blue/green present = WRONG
- ✅ No colors outside the white→red spectrum

## Why built-in colormaps fail

`matplotlib.cm.Reds` uses `#fff5f0` (pinkish) → `#67000d` (dark red).
The `#fff5f0` has an orange tint that some users perceive as "dirty".
Custom `#FFFFFF → #FFD4D4` is cleaner: pure white → pure pink, no warm tint.

## The 0-10 clip is mandatory

Raw `-log10(q)` values span 1.5 to 97+. Without clipping:
- vmax=97 makes everything below ~15 look white
- Only 1-2 cells show as red, the rest are invisible

With clip(upper=10):
- Full color gradient used for the range 0-10
- Cells >10 all show as deep red (acceptable — they're all highly significant)
- Color legend shows [0, 2, 4, 6, 8, 10] ticks
