---
name: latex-cjk-toolchain
description: >-
  LaTeX / CJK 文档工具链的**供给与排障**（不限于某个模板集）：装 TeX 发行版（Windows 便携 MiKTeX / TeX Live）、
  本地宏包树（TEXMFHOME / texmf-local）、XeLaTeX 中文底座、编译报错的根因定位，以及**编译类交付的验证纪律**
  （exit code + 产物字节数 / 最小对照实验否证假说）。触发词：装 TeX、装 LaTeX、xelatex 找不到、latexmk not found、
  编译不出 PDF、宏包缺失、ctex 报错、中文字体 not found、MiKTeX、TeX Live、TEXMFHOME、kpsewhich、字体映射、编译失败排查。
when_to_use: >-
  [latex-cjk-toolchain] 当任务卡在 LaTeX **工具链本身**而不是内容/模板时触发：① 本机没有 TeX 发行版或
  xelatex/latexmk/pdflatex 找不到 ② 装了但报宏包缺失（xxx.sty/.cls not found）、ctex/xeCJK 报错、
  字体 not found/wrong@fontshape ③ 需要把某个仓库自带的公共包/.sty 装进 TeX 树
  ④ 要判断「这份 .tex 到底能不能编译出 PDF」以及怎么**证明**编译成功 ⑤ 中文文档乱码/方框/字体缺失。
  模板选型与产品线编排（国自然/毕业论文/SCI 模板）不归本 skill，走 chinese-research-latex。
trigger_keywords: ["装TeX", "装 TeX", "装LaTeX", "装 LaTeX", "xelatex 找不到", "latexmk not found", "编译不出PDF", "编译不出 PDF", "宏包缺失", "sty not found", "cls not found", "ctex 报错", "中文字体 not found", "MiKTeX", "TeX Live", "TEXMFHOME", "kpsewhich", "字体映射", "编译失败排查", "wrong@fontshape", "pool size"]
trigger_level: RED 必触发
---

# LaTeX / CJK 工具链：供给 · 排障 · 编译验证

**本 skill 的职责**：让「这份 .tex 能不能真编译出 PDF」变成**可执行、可验证**的事。
管三件事：① 把 TeX 发行版和宏包装到位；② 编译报错的根因定位；③ 编译类交付的**证据纪律**。

**与相邻 skill 的边界（别抢）**：

| 需求 | 走哪 |
|---|---|
| 模板选型、产品线（国自然 / 毕业论文 / SCI / 简历）、上传 Overleaf、DOCX 导出 | `chinese-research-latex` |
| 中文学位论文**规范合规 + DOCX 出稿**（读学校规范附件） | `academic-thesis-docx` / `cn-degree-thesis-writing` |
| 纯英文稿件论证、章节起草 | `nature-writing` / `nature-polishing` |
| 结论/参数裁决（含编译失败的**假设**该不该采信） | `debate-core`（§3.3 与本 skill 第五节配套） |

---

## 一、Windows：便携 MiKTeX（免管理员、可脚本化、落指定盘）

> 实测环境：Windows 11 + 无 TeX + 无管理员权限 + C 盘紧张 + GitHub git 协议不通。以下命令均实测通过。

```bash
# 1) 先「列目录」取真实文件名——不要猜（实测猜 miktexsetup-x64.zip 会 404）
#    https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/win32/miktex/setup/windows-x64/
#    → 实为 miktexsetup-<ver>-x64.zip，解压得到 miktexsetup_standalone.exe（注意 _standalone 后缀）
# 2) 官方语法（--help 实证）：子命令是 download | install
EXE download --portable='E:\MiKTeX' --package-set=basic \
  --remote-package-repository='https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/win32/miktex/tm/packages/' \
  --use-registry=no --modify-path=no
EXE install      # 同参数
```

- `--use-registry=no --modify-path=no` = **不写注册表、不改 PATH**（真便携）
- `basic` 包集**已含** ctex / xeCJK / ctexart / fontspec / zhnumber —— 中文底座够用，不必上 full
- 实测 **88 秒 / 479 MB**，产物 `E:/MiKTeX/texmfs/install/miktex/bin/x64/{xelatex,kpsewhich,mpm,initexmf}.exe`
- **>10 分钟的命令用 `background=True` + `notify_on_complete=True`**（前台硬上限 600 s）

## 二、把仓库自带的宏包装进 TeX 树（`TEXMFHOME` 为空是最大陷阱）

**症状**：宏包装完了，编译仍报 `xxx.sty / yyy.cls not found`。
**根因**：便携 MiKTeX 的 `TEXMFHOME` **为空**，安装器无法自动定位 → 必须显式指定。

```bash
# 仓库根级 install.py 往往仍要联网下载快照 → 网络不通时用各包自带的「委托安装器 --source local」
PY='<项目>/.venv/Scripts/python.exe'; RWIN='<仓库根>'; TM='E:/MiKTeX/texmf-local'
"$PY" "$RWIN/packages/<pkg-fonts>/scripts/package/install.py" --texmfhome "$TM"     # 无子命令的包
for p in <其余包>; do
  "$PY" "$RWIN/packages/$p/scripts/package/install.py" --texmfhome "$TM" \
     install --source local --path "$RWIN/packages/$p" --force   # 有的包需 --ref <分支>
done
initexmf --register-root "$TM" && initexmf --update-fndb
kpsewhich <pkg>.sty        # ✅ 必须逐个命中 texmf-local 才算装好
```

- ⚠️ **`--texmfhome` 是顶层选项，必须放在子命令「之前」**；各包 CLI 形态可能不同（无子命令 / 需 `--ref`）——先跑 `--help` 取真实语法，别照抄。
- ⚠️ 安装器可能偷偷 `pip install --user`（污染用户目录，违反「装到项目内」规范）→ 查有无 `--skip-python-deps` 类开关并用上。
- ⚠️ 有的安装器会把版本缓存写到 `C:\Users\<user>\.<项目名>\`（实测 666 MB）——C 盘紧张时迁走。

## 三、编译：优先官方 wrapper，裸跑 xelatex 是最后手段

- **官方构建脚本通常不依赖当前目录找字体，而是显式把字体目录注入 `TEXINPUTS`** → 正确入口是仓库自带的 `*_project_tool.py build`，不是 `xelatex main.tex`。
- 中文文档**必须 XeLaTeX**（Overleaf: Menu → Compiler → XeLaTeX）。
- 缺宏包（如 `tabu.sty`）：MiKTeX 的「按需自动装包」在 `-interaction=nonstopmode` 下**不触发** →
  编译加 `--enable-installer`，或 `mpm --install=<pkg>`；先确认
  `initexmf --show-config-value='[MPM]AutoInstall'`=1 且 `[MPM]RemoteRepository` 指向可用镜像。
- 交叉引用/目录需多趟（`xelatex → bibtex → xelatex → xelatex`）；**首过 warning 不等于失败**。

## 四、坑表（全部亲测）

| 现象 | 根因 | 修法 |
|---|---|---|
| 传给原生 exe 的路径被改写 → `No such file` | Git Bash/MSYS 把 `/e/x` 转成 `E:\e\x`；`MSYS2_ARG_CONV_EXCL='*'` **实测无效** | 给原生程序（python.exe / xelatex / mpm / miktexsetup）**一律传 `E:/...` 风格** |
| `git clone` 报 `schannel: failed to receive handshake` | 该机 GitHub git 协议 TLS 不通（curl 正常），换 `GIT_SSL_BACKEND=openssl` 也无效 | 换镜像源（如 Gitee）克隆 |
| `mpm --install` 行为异常 | 官方已标 deprecated | 先查 `[MPM]AutoInstall` / `RemoteRepository` 配置值，再用 |
| 内联 shell 报 `unexpected EOF` | 命令里含反引号（grep 模式常见） | 诊断逻辑写成 `.sh` 再跑，别内联 |
| 日志读不了 / 满屏乱码 | 编译失败会往日志灌 NUL | `tr -d '\000' \| grep -v '^\^@'` 再读 |
| 卡住并输出 `TeX capacity exceeded [pool size]` | 未定义命令 + 字体映射失控（罕见字符展开） | 见 `references/compile-failure-forensics.md` |
| 宏包**装上了**仍报错（不是 `not found`，而是 `Undefined control sequence` 停在宏包内部宏上） | 宏包与本机内核**不兼容**（停更宏包常见，如 `tabu` vs `LaTeX2e <2026-06-01>`）—— 再装/重装/换镜像都无用 | **换等价且维护中的宏包**（`tabu`→`array`+`tabular`，或 `tabularray`，注意 `\multirow` 要换 `\SetCell`）；判定用最小复现：`latex-toolchain-troubleshooting/templates/probe_package_kernel_compat.tex` |
| 官方 wrapper 抛 `未找到可执行文件：xelatex` | 便携 MiKTeX 用 `--modify-path=no` 装的，bin **不在 PATH**；shell 里 export 的 PATH 不会进 Python 子进程 | 显式设 PATH（shell: `export PATH="E:/MiKTeX/texmfs/install/miktex/bin/x64:$PATH"`；Python: `env["PATH"]=MIKTEX_BIN+os.pathsep+env["PATH"]`） |

## 五、🔴 编译类交付的验证纪律（本 skill 的核心价值）

「我改了 .tex」≠「能编译」；「编译没报错」≠「出了 PDF」。交付前必须拿到：

1. **`exit code`**（0 才算成功）+ **产物真实字节数**（真的 stat 出来的 PDF 大小）；
2. **产物时间戳** —— ⚠️ 仓库里常带**基线 PDF**，别把旧文件当本次产物（实测踩过：模板自带的 `main-zh.pdf` 时间戳是克隆时刻，差点被当成本次构建结果）；
3. 路径写全，**不许用「应该能跑 / 看起来正常」代替实测**。

**假说必须过最小对照实验才采信**（与 `debate-core` §3.3 配套）：
多角色辩论或自己的推理**收敛到同一假设 ≠ 假设成立**。把假设拆成可证伪的最小命题 →
跑**对照**（一次只留一个变量）→ 看 `exit code`。**对照组未复现故障 = 假设被否证**；
否证结论要连同「已排除的错路」一起落盘，否则下次重走。
完整案例（7/8 席位收敛的错误假设被 plain 版对照实验推翻）见
`references/compile-failure-forensics.md`。

**产物级验证（本机实测配方，2026-10-12）**—— 只报 "exit 0" 不够，还要证明**内容没被改坏**：

```bash
# ① 与上游基线做像素级比对（多数模板库自带 compare 子命令）
git -C <仓库> show HEAD:projects/<模板>/main-zh.pdf > /tmp/baseline-zh.pdf    # 基线必须从 git 取
python packages/<pkg>/scripts/<tool>_project_tool.py compare \
  --project-dir projects/<模板> --variant zh --baseline-pdf /tmp/baseline-zh.pdf
#   → 看 project_pages == baseline_pages；identical=false 时看 mismatches[].bbox 是否只在局部
# ② 首页渲染成 PNG，再交给 vision_describe 核对版式（纯文本模型必须走这条，不许凭空描述）
"…/miktex/bin/x64/pdftoppm.exe" -png -r 100 -f 1 -l 1 main-zh.pdf page1
```

- ⚠️ **基线 PDF 千万别用被覆盖过的产物**：模板自带 PDF 在构建时会被原地覆盖 ⇒ 必须先 `git show HEAD:<path>` 取回原始基线，否则比对毫无意义（实测踩过）。
- 像素比对 `identical:false` 是**常态**（换表格实现、行距微差都会触发），**不等于失败**：页数一致 + 差异 bbox 局部 ⇒ 通过，并在交付说明里写清差异位置与原因。
- 上面这套（基线比对 + 渲染读图）是**版式类改动**（换表格宏包、调间距、改字体）唯一可信的验收证据。

## 六、收尾

- 把最终配方（真实命令 + 真实报错 + 镜像里真实文件名）写进 `references/`，**别只留在对话里**。
- 非生信交付（PDF/DOCX）若被 `rail_review(post)` 按「分析级」口径判 failed（要求 figure_count>0、或 location 被误推断成 cluster）→ **如实说明口径不匹配**，用第五节证据交付，**不补假图凑数**。
- 环境缺失类卡点：**如实报一次 + 给选项**（装发行版 / 走 Overleaf / 只做内容）即止，不要每轮重复重申同一个卡点。

相关参考：`references/compile-failure-forensics.md`（编译失败取证 + 对照否证的完整案例）。