# 样例：boxplot_16_O_ex 面板 → A4 上半区 + 字号规范（6/5/7）

2026-10-05 实测通过的「PDF 面板 → A4 交付版」样例，供对照与复现。

- **输入**：`D:\肌肉锻炼\Figure S2\boxplot_16_O_ex (2).pdf`（576×288pt，28 个文字帧；源文件 sha256 `3f1ecc15…` 与母版 `FigureS2_new.ai` 全程未被修改）
- **处理**：面板导入配方（`open` → `artboard-set` A4 → `move --target all` 进上半区 → `text-set` 分组字号 → 标题 7pt 居中 → 复验 → `export` → `close-doc --force`）
- **产物**：`boxplot_16_O_ex_A4top.pdf`（A4 595.28×841.89，28 spans、文字可编辑）
- **验收数字**（PyMuPDF 直读文本层，与 AI 侧 `text-list` 一致）：
  - 字号直方图：`{5.0: 10, 6.0: 17, 7.0: 1}`（原图：`{6×10, 7×2, 8×14, 9×1, 10×1}`）
  - 标题 `Aged Exercise` 7.00pt，中心 x=297.64（A4 中线）
  - 内容 y 71.1–350.5 ≤ 420.9（只占上半页）
  - 字体：原图 Helvetica → 成品 ArialMT（Windows 版 AI 自动替换，口径见 SKILL.md 坑表）
- **对照图**：`font_compare_original_vs_final.png`（上=原图、下=成品，另附标题/列头/注释三组放大对）
- **复现核对**：`python ../../scripts/font_compare.py --orig <原图.pdf> --final boxplot_16_O_ex_A4top.pdf --out .`