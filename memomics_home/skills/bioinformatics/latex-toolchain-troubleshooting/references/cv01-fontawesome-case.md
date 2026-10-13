# 实例档案：cv-01 编译失败（`FontAwesome cannot be found` → `pool size` 爆炸）——✅ 已结案

> 场景：ChineseResearchLaTeX v4.1.1 的 `projects/cv-01`（中英文学术简历）在**便携 MiKTeX 26.5** 下编译失败。
> 同期 `paper-sci-01` / `NSFC_Young` / `thesis-nju-master` **三个模板全部 exit=0 正常出 PDF**。
> 本文件的价值：**两条听上去很合理的假设已被实验否证**（别再走）＋**两个真因与最终修法**（别再重新猜）。

---

## 〇、✅ 最终结论（2026-10-12 结案，先读这段）

**两个独立故障叠加**，任一单独存在都不足以解释全部症状：

| # | 层 | 真因 | 修法（已落地） |
|---|---|---|---|
| A | 资源路径 | `\getabspath{bensz-fonts.sty}` 的 `\theabsdir` 在本机便携 MiKTeX 下**返回空**（且同一命令两次运行结果不一致）→ `\BenszFontsDir` 退化成相对 `fonts/` → fontspec 的 `Path=` 解析失败 | 给两处 `bensz-fonts.sty` 加**空值回退绝对路径**（见 `chinese-research-latex/references/local-patches.md` §1） |
| B | 宏包兼容 | `tabu`（2019 停更）与本机内核 `LaTeX2e <2026-06-01>` **不兼容**：`\end{tabu}` 抛 `Undefined control sequence`（宏体停在 `\tabu@cleanup … \tabu@naturalX =\tabu@naturalX@save`） | cv 模板 `\usepackage{tabu}`→`\usepackage{array}` + `\begin{tabular}`/`\end{tabular}`（`c l r` 列式零改动） |

**结果**：`main-zh.pdf` 754 KB / `main-en.pdf` 678 KB，3 页；与上游基线像素比对页数一致、仅首页信息块行距有微差（`tabular` vs `tabu`）⇒ 通过。
**幂等体检脚本**：`chinese-research-latex/scripts/crl_fix_local_patches.py --check`（待打 0 项即健康）。

**顺带纠正本文件旧版的两处错**（旧版写于只定位到半个真因时）：
- ❌ 旧结论\"改用官方 wrapper（注入 `TEXINPUTS`）可绕开 `Path=` 解析\" —— **实测不稳定**：官方 wrapper 同样撞上 A（时对时空），只靠 TEXINPUTS 治不了。
- ❌ 旧结论把症状整体归给\"资源路径\" —— 实际还叠加了 B（宏包层）；只修 A 仍会因 `tabu` 失败。

---

## 一、A 层真因（日志原文，已定位）

清洗日志后 **第 4322 行**：

```
! Package fontspec Error:
(fontspec)                The font "FontAwesome" cannot be found; this may
(fontspec)                be but usually is not a fontspec bug. Either there
(fontspec)                is a typo in the font name/file, the font is not
(fontspec)                installed (correctly), or there is a bug in the
(fontspec)                underlying font loading engine (XeTeX/luaotfload).
```

**完整失败链**：
```
fontspec 找不到 FontAwesome（\BenszFontsDir 为空 → Path=fonts/ 不存在）
  → \FA 字体家族未建立
  → \symbol{"F19D}（毕业帽）无字体可用 → 该字符回退到 TU+lmr
  → wrong@fontshape 递归告警
  → 日志被 NUL(^^@) 洪水灌满
  → TeX capacity exceeded [pool size=5440117]，报错行落在 \section{\faGraduationCap …}
```

⇒ 表面症状（`TeX capacity exceeded` / NUL 洪水 / 报错行上的图标）是**结果**，不是原因。**别从症状下手**。

---

## 二、⛔ 两条已被实验否证的死路（勿再排查）

### ❌ 死路 A：hyperref 对 `\section` 参数做 PDF 书签字符串展开
- 为什么当时觉得对：L2 多角色辩论 **7/8 席位独立收敛**到这个假设；`\section{\faGraduationCap\ 教育背景}` 里带脆弱命令，书签展开确实是经典坑。
- **怎么被否证的**：最小复现对照实验 —— `\section{\faGraduationCap ...}` + hyperref + fontawesome5 的 **plain 版编译 exit=0、正常出 PDF（6,646 B）**。
- 追加否证事实：`cv-01/main-zh.tex` 里**根本没有** `\faGraduationCap` 字面量。
- **教训**：7 个角色一致同意 ≠ 对。**多数收敛也可能是同向误判**，必须用对照实验落地。

### ❌ 死路 B：fontawesome v4/v5 定义层混用
- 为什么当时觉得对：`\faGraduationCap` 看着不像 fontawesome 官方宏，且 `\faicon{...}` 是 v5 风格写法，本机又装了 v4.6.3.1。
- **怎么被否证的**：bensz-cv **自带整套 v4.6.3**——
  `packages/bensz-cv/` 下齐备 `fontawesome.sty`（`\ProvidesPackage{fontawesome}[2016/05/15 v4.6.3 ...]`）
  + `fontawesomesymbols-generic.tex` + `-pdftex.tex` + `-xeluatex.tex`。
  而 `\faicon` 就定义在**自带** `fontawesome.sty` 里：
  `\newcommand*{\faicon}[1]{{\csname faicon@#1\endcsname}}`
  `fontawesomesymbols-xeluatex.tex:375` 亦有对应 `faicon@graduation-cap` 定义。
  ⇒ **两支版本一致，不存在混用**。
- **教训**：怀疑"版本混用"前，先 `ls` + `head` 把**实际加载的那个文件**看清楚，别凭宏名风格推断。

### ❌ 死路 C（本次新增）：改图标/字体形状写法
按报错行归因，试过 `\upshape` 包裹图标、`\titleformat{\section}` 去掉 `\scshape`、
逐个摘除 `progressbar` / `academicons` / `NotoSerifCJKsc_external`——**全部无效**（约 20 次无效调用）。
- **教训**：**报错行 ≠ 根因行**。池溢出报错会落在"后面第一个需要换字形的宏"上 ⇒ 先修上游坏状态，别改报错行。

---

## 三、文件系统事实（已实查，勿重复查）

| 事实 | 实测值 |
|---|---|
| bensz-cv 自带 fontawesome 版本 | `v4.6.3`（2016/05/15） |
| `\faGraduationCap` 定义处 | `packages/bensz-cv/fontawesomesymbols-generic.tex:375` → `\def\faGraduationCap{\faicon{graduation-cap}}` |
| `\FA` 家族定义处 | `packages/bensz-cv/fontawesome.sty`（`\iffontawesome@otf` 分支内） |
| `\FA` 定义原文 | `\newfontfamily{\FA}[Path=\BenszFontsDir, Scale=0.85, SmallCapsFont=*]{FontAwesome}` — **无 `Extension=`** |
| 该分支还做了什么 | `\usepackage{fontspec}` + **`\RequirePackage{bensz-fonts}`**（字体目录宏来自它） |
| `FontAwesome.otf` 在 texmf-local | ✅ `E:/MiKTeX/texmf-local/tex/latex/bensz-fonts/fonts/FontAwesome.otf`（132,564 B） |
| `FontAwesome.otf` 在 MiKTeX 自带树 | ✅ `E:/MiKTeX/texmfs/install/fonts/opentype/public/fontawesome/FontAwesome.otf` |
| `texgyretermes-regular.otf` | ✅ 在 `bensz-fonts/fonts/`（154,232 B），**文件从来没缺过** |
| `kpsewhich bensz-fonts.sty` | ✅ `E:/MiKTeX/texmf-local/tex/latex/bensz-fonts/bensz-fonts.sty` |
| `TEXMFLOCAL` | `E:/MiKTeX/texmf-local`（已 `--register-root`） |
| `TEXMFHOME` | 便携模式下**为空** → 自建包必须 `--texmfhome` 显式指定 |

⇒ **结论：不是"文件缺失"**。文件两处都在、kpsewhich 也命中。
⇒ **缺口在 fontspec 的 `Path=` 解析**：`Path=` 不走 kpathsea 补全，`<Path>FontAwesome`（连扩展名都没有）要靠 `\BenszFontsDir` 展开出一个**真实可用的绝对路径**。

---

## 四、`\BenszFontsDir` 的机理链（源码实证）

`packages/bensz-fonts/bensz-fonts.sty`：
```latex
\RequirePackage[abspath]{currfile}
\getabspath{bensz-fonts.sty}
\edef\BenszFontsPackageDir{\theabsdir}
\newcommand{\BenszFontsDir}{\BenszFontsPackageDir fonts/}
\newcommand{\BenszFontsFile}[1]{\BenszFontsPackageDir fonts/#1}
```
⇒ `\BenszFontsDir` = **bensz-fonts.sty 所在目录 + `fonts/`**，整条依赖 `currfile` 的 `abspath` 记录是否成立。
⇒ **实测该链在本机不稳定**：同一命令两次运行，`\typeout{DIR=[\BenszFontsDir]}` 有时打出绝对路径、有时打出 `fonts/`（`\theabsdir` 为空）。已排除的解释：TEXINPUTS 正/反斜杠、`-recorder`、`-synctex`、`cwd`、输出目录旧 aux。
⇒ 所以**不要去"稳定 abspath 链"**，直接在宏里加空值回退。

---

## 五、✅ 收口动作（已执行完，勿重做）

1. 打印 `\BenszFontsDir` 真实值（`\typeout` 探针）→ 确认空值/不稳定 ⇒ 判定为 A 层真因。
2. 给**两处** `bensz-fonts.sty` 加空值回退（改前留 `.bak-memomics`）：texmf-local 副本 + 仓库副本。
3. 最小复现判定 B 层：`article` + `tabu` 两行表格即报 `Undefined control sequence` ⇒ 宏包级不兼容，改 `array` + `tabular`。
4. 真编译：`cv_project_tool.py build --project-dir projects/cv-01 --variant all` → exit 0，报出 PDF 绝对路径 + 字节数。
5. 版式验收：`compare`（基线用 `git show HEAD:…` 取）页数一致 + `pdftoppm` 渲染首页核对版式。
6. ⚠️ 仓库里 `cv-01/main-zh.pdf` 等**会被构建原地覆盖** ⇒ 别拿它当基线，也别把旧时间戳的 PDF 当本次产物。

---

## 六、已试且无效的清单（别再重复）

装 `fontawesome`/`fontawesome5` 宏包、`initexmf --mkmaps`、`initexmf --update-fndb`、
`cv_project_tool.py clean`、手工 `TEXINPUTS='…/bensz-fonts//;'` + `-recorder`、多趟编译、
不带 `--enable-installer` 重跑、`\texorpdfstring` 包裹（最小复现里能编过，但**不是** cv-01 的病灶）、
图标 `\upshape` 包裹、去掉 `\scshape`、逐个摘除 `progressbar`/`academicons`/`NotoSerifCJKsc_external`、
调 `-recorder/-synctex/cwd/output-directory`。

**有效的是三件事**：① 空值回退补丁（A）② `tabu`→`array`+`tabular`（B）③ 官方 wrapper 必须能拿到 MiKTeX bin 的 PATH（否则 `FileNotFoundError: 未找到可执行文件：xelatex`）。

---

## 七、可复用的排查手法（本案例的沉淀）

1. **清洗巨型日志**：`tr -d '\000' | grep -v '^\^@'`（12.9 MB / 15.9 万行 → 可读）
2. **⛔ 不要信第一个 `!`**：第 76 行 `! Transform components aren't all known.` 是 MiKTeX 用 METAFONT
   现场生成 `othello` 的 `OT.mf` 造成的**无害噪声**（伴随 `Running miktex-mf.exe`、`Font metrics written on OT.tfm`），
   真因在第 **4322** 行。**按语义 grep**（`fontspec Error` / `cannot be found` / `Undefined control sequence`），用 `scripts/tex_log_root_cause.sh`。
3. **症状 ≠ 原因**：`TeX capacity exceeded [pool size]` / NUL 洪水是**递归的结果**，往上游找第一个"语义错误"。
4. **多角色一致同意 ≠ 正确**：7/8 收敛的假设被一个 10 行对照实验推翻。任何假设都要有对照。
5. **"文件在不在"先于"版本对不对"**：先 `ls`/`kpsewhich` 拿文件系统事实，再谈版本与加载顺序。
6. **分层最小复现**（本案例最终奏效的手法）：宏包层用 `templates/probe_package_kernel_compat.tex` 判定；
   路径层用 `templates/probe_font_dir_resolution.tex` 判定；**两类分开验证通过后再合跑**。