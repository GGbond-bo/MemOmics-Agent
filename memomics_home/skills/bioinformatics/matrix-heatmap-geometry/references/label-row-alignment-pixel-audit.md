# 标签 ↔ 色块行对齐：像素级审计 + 自校准（矩阵热图通用）

> 触发场景：用户说「字体跟自己的色块不对齐」/「名字没对准那一行」/「图不合格」，
> 而对象级自检（`get_window_extent` / `transData`）报 PASS。
> 首次实证：2026-10-01，`47_MEF2C_log2FC_heatmap_5contrasts_10subclusters`（10 亚群 × 5 对比，matplotlib + pcolormesh）。

---

## 一、症状与真根因

**症状**：脚本自带对齐自检打印 `ALIGN 亚群名↔行色块 max=0.0 px`，用户看图说错位。

**真根因（实测）**：10 行热图，脚本写 `ax.set_ylim(NR - 0.5, -0.5)` 并据此假定「行中心在 data y = 0..9」。
对导出 PNG 反算后，**色带真实行中心在 data y = 0.517, 1.517, …, 9.517** ——
每个标签恒偏 **半个行高**：60.5 px @300 dpi（行高 120 px）= **5.08 mm**，10 行无一例外（匀偏，不是随机抖动）。

**视觉后果**：每个亚群名落在**两行之间的白格线上**；第一行的名字飘在热图上沿之外。
匀偏 0.5 行是「标签整体错半格」的典型指纹 —— 见到就不要再去查字形基线。

---

## 二、为什么对象级自检会骗人（两个独立缺陷）

1. **包围盒退化**：在 `plt.close(fig)` 之后（或图未以目标 dpi 重绘）取 `t.get_window_extent(rend)`，
   刻度标签返回 **1×1 px**。一次审计因此同时吐出两个假数字：
   - `OVERLAPPING text pairs = 190`（= 20 个文字两两组合 C(20,2)，全是 1×1 px 相接）
   - `ALIGN 亚群名↔行色块 max = 1227.5 px`（≈ 整个 axes 高度，坐标系混了）
2. **dpi 不一致**：`transData.transform()` 基于 canvas（本例 100 dpi 构造），
   `get_window_extent()` 若基于 300 dpi 导出 → 二者数值不可比。

> **铁律**：任何「标签与色块是否对齐」的判定，必须**对最终导出的 PNG 做像素测量**。
> 对象级数字只能当线索。汇报必须给**逐项 Δ 数值 + 容差**；只说「已对齐」= 无效汇报
> （本次因拿假数字回「我量过，偏差 0.5 px」，被用户连怼两轮）。

---

## 三、检测配方（对渲染 PNG，逐条都是踩坑换来的）

```python
import numpy as np
from PIL import Image
A = np.asarray(Image.open(PNG).convert('RGB')).astype(int)
H, W, _ = A.shape

# 1) 热图横向主块 —— 用「非白像素」而非饱和度
nw = A.min(2) < 250                      # ⚠️ 不要用 sat>25：pale 格（|logFC| 小）饱和度≈0 会漏
cc = nw.sum(0) > 200
# 连续段 → 合并间隔 <80 px → 取最宽块 = 热图 x 范围 [xL, xR]

# 2) 行色带：热图 x 范围内非白行占比 > 50%，高度 >40 px，取前 NR 段 gs
pf = nw[:, xL:xR+1].sum(1)
gs = [b for b in runs(pf > 0.5*(xR-xL+1)) if b[1]-b[0] > 40][:NR]

# 3) 行高 —— 用 band 的 top 之差，不要用 center 之差
rh = gs[1][0] - gs[0][0]                 # ⚠️ 末行常因 pale 被截断；用 center 会把末行推偏 30 px
rows = [gs[0][0] + (k+0.5)*rh for k in range(NR)]

# 4) 标签墨迹：逐行开窗取质心（不要按 y 连通分组）
dk = A.max(2) < 140
win = dk[int(c-0.4*rh):int(c+0.4*rh)+1, 0:xL-8]
cent = lo + (win.sum(1) * np.arange(len(win))).sum() / win.sum(1).sum()
# ⚠️ 按 y 连通分组会把 10 个名数成 12/13 组：括号/下延字符留 1 px 空隙被拆开

# 5) 判据
assert max(abs(cent_k - rows[k]) for k) < 0.05 * rh      # 本例 6 px
```

**两条反直觉的检测选择（都实测踩过）**
- ❌ **不要用"白格线"定位行**。格内**白色数值文字**（`color='white' if abs(v)>0.30`）的笔画只有 ~3 px 厚，
  会被 `b-a<=6` 的细线过滤当成白格线收进来 → 把**行中心**误判成格线 → 白绕两轮。
  探针位置换到列间隙也没用（文字位置随列变）。
- ✅ 改用「非白像素色带」：浅色格也能识别，且与文字无关。

---

## 四、自校准修法（与 ylim 假设彻底解耦）

不要试图去「推」ylim 或换 `set_yticklabels` / `ax.text(y=i)` —— 两者都会同样偏半行
（因为偏差在**行色块的数据坐标**里，不在标签 API 里）。正确做法是**量出来再钉上去**：

```python
# 先正常出图并存 PNG，再：
fig.set_dpi(300); fig.canvas.draw()              # 必须与导出一致
inv = ax.transData.inverted()
for k, c_img in enumerate(band_centers_img):     # 第 k 行色带的像素中心（图像 y，原点左上）
    LABTXT[k].set_y(inv.transform((0, H_img - c_img))[1])
# 再重出 png/svg/pdf（并同步 task5/figures/ 之类副本目录）
```

标签与色块从此**同源**：两者的像素位置都由同一次渲染决定，与 ylim 取值无关。

实测校准输出直接把真值暴露出来：
`CALIB 色带数=10 行高=120 px | 标签 y(data) = [0.517, 1.517, 2.517, …, 9.517]`

**修后复测**：10 行 Δ = −1.6 … −3.3 px（行高 120 px，容差 6 px）→ **PASS**。
残余 ≤3.3 px 来自墨迹质心与几何中心的字形不对称（下延字符），不是错位。

---

## 五、交付卫生（用户会检查）

1. **重出前先备份**旧的 `png/svg/pdf` 到 `figures/_backup_<stem>_before_<fix>/`。
2. **图内文字全英文**（用户偏好）；脚本注释与终端打印可以中文 —— 「图里的文字」才要求英文。
3. 汇报格式：**逐行 Δ 表** + 容差 + 备份路径 + 三格式文件大小。禁止只说「已修好」。
4. 顺带把**旧的自检换掉**：化对象级为像素级，并在脚本里打印 `PASS/FAIL` 与逐行 Δ，
   否则同一个假 PASS 会在下一轮原样复现。