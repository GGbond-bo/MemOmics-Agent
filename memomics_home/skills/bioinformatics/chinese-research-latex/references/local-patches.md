# 本机补丁（MiKTeX 便携版 + ChineseResearchLaTeX）— 2026-10-12 实测

> 适用：E:/MiKTeX（26.5 Portable）+ `third_party/CRL`（v4.1.1, commit b8b4142）。
> 症状出现在 **cv-01（学术简历）**；其余三条产品线（NSFC_Young / thesis-nju-master / paper-sci-01）不改也通过。

## 0. 症状与结论速览

| 现象 | 真正的根因 |
|---|---|
| `fontspec: font "texgyretermes-regular" cannot be found` / `font "FontAwesome" cannot be found` | `\theabsdir` 为空（不稳定）→ `\BenszFontsDir` 变成相对 `fonts/` |
| `TeX capacity exceeded, sorry [pool size=5440117]` + 满屏 `^^@`，报错停在含图标的 `\section{}` | 字体解析失败的**下游死循环**（日志同时有 `TU+lmr`、`wrong@fontshape`），**与图标、`\scshape` 无关** |
| `\end{tabu}` → `Undefined control sequence`（`\tabu@cleanup … \tabu@naturalX =\tabu@naturalX@save`） | `tabu` 与本机 LaTeX 内核（`LaTeX2e <2026-06-01>`）不兼容；**任何**文档用 `tabu` 都失败 |
| 日志里 `(…/tex/latex/tools/.tex Fileignored)` | 空文件名被当 `.tex` 去 `\input`（路径宏展开异常的伴生现象） |

已排除（都试过，不能稳定复现"好"状态）：TEXINPUTS 用正斜杠/反斜杠、`-recorder`、`-synctex`、cwd 在项目目录、输出目录是否有旧 aux、图标用 `\upshape` 包裹、`\scshape` 改掉、`progressbar`/`academicons`/`NotoSerifCJKsc_external` 逐个摘除。
**方法论教训**：先用最小复现把「字体路径」与「表格宏包」两类问题**分开**，否则 pool 爆炸会把人带偏到图标/字体定义上。

## 1. 补丁 A：字体目录空值回退（两处都要打）

`bensz-fonts.sty` 里：

```latex
\getabspath{bensz-fonts.sty}
\edef\BenszFontsPackageDir{\theabsdir}
% [MemOmics 本地修复 2026-10-12] MiKTeX 便携版下 \theabsdir 可能为空 -> 回退绝对路径
\ifx\BenszFontsPackageDir\empty
  \edef\BenszFontsPackageDir{<该副本自身所在的绝对目录>/}
\fi
```

要打两份，绝对路径各按自己所在目录写：

1. `E:/MiKTeX/texmf-local/tex/latex/bensz-fonts/bensz-fonts.sty` → 回退值 `E:/MiKTeX/texmf-local/tex/latex/bensz-fonts/`
2. `third_party/CRL/packages/bensz-fonts/bensz-fonts.sty` → 回退值 `E:/MemOmics-Agent/third_party/CRL/packages/bensz-fonts/`

（官方 wrapper 用 `TEXINPUTS=<pkg>//;…` 会**优先命中仓库副本**；texmf-local 副本给裸跑 xelatex / 其它模板用。改前备份为 `bensz-fonts.sty.bak-memomics`。）

## 2. 补丁 B：cv 模板去 tabu

`third_party/CRL/projects/cv-01/main-zh.tex` 与 `main-en.tex` 各 3 处：

```diff
- \usepackage{tabu}
+ % tabu 与本机 LaTeX 内核不兼容 -> 改用 array+tabular
+ \usepackage{array}
- \begin{tabu}{ c l r }
+ \begin{tabular}{ c l r }
- \end{tabu}
+ \end{tabular}
```

`c l r` 列式、`\multirow`、`\progressbar`、`\includegraphics` 全部零改动可用（`multirow` 包本就已加载）。改前备份为 `main-*.tex.bak-memomics`。

## 3. 构建命令（必须让 MiKTeX bin 在 PATH 上）

```bash
# MiKTeX bin 不在 PATH 时 wrapper 会抛 FileNotFoundError: 未找到可执行文件：xelatex
export PATH="E:/MiKTeX/texmfs/install/miktex/bin/x64:$PATH"
cd third_party/CRL
python packages/bensz-cv/scripts/cv_project_tool.py build --project-dir projects/cv-01 --variant all
# 产物：projects/cv-01/main-zh.pdf（≈754 KB, 3 页）+ main-en.pdf（≈678 KB）
```

## 4. 验证（本次实测结果）

```bash
# 结构：页数 + 内容
"…/x64/pdftoppm.exe" -png -r 100 -f 1 -l 1 main-zh.pdf page1   # 渲染首页人工核对
# 与上游基线做像素级比对（基线从 git 取，不要用被覆盖的产物）
git -C third_party/CRL show HEAD:projects/cv-01/main-zh.pdf > /tmp/baseline-zh.pdf
python packages/bensz-cv/scripts/cv_project_tool.py compare --project-dir projects/cv-01 --variant zh --baseline-pdf /tmp/baseline-zh.pdf
```

实测：`project_pages=3` = `baseline_pages=3`，唯一差异在第 1 页信息块（`tabular` 与 `tabu` 行距略有不同），正文/图标/进度条渲染正常。

## 5. 复查用探针（怀疑 abspath 又坏时）

```latex
\documentclass{bensz-cv}
\makeatletter\typeout{ZZDIR=[\BenszFontsDir]}\makeatother
\begin{document}\section{Test}\end{document}
```

跑完 grep 日志里的 `ZZDIR`：**应是绝对路径**；若是 `[fonts/]` → 补丁 A 失效（例如换了 CRL 目录 / 重新解压了副本）。