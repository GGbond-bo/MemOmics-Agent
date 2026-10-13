# 便携 MiKTeX（Windows）+ 自建包/字体装配：逐条可复制配方

> 全部数字来自 **2026-10-12 实测**（Windows 11 / 无管理员权限 / C 盘仅剩 24.9 GB / E 盘 241 GB / GitHub git 协议不通）。
> 目标：**免管理员、不写注册表、不落 C 盘、可整目录搬走**。

---

## 一、装 MiKTeX（便携）

```bash
# 0) 先列镜像真实文件名（⛔ 不要猜 miktexsetup-x64.zip —— 实测 404）
curl -s 'https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/win32/miktex/setup/windows-x64/' | grep -o 'miktexsetup[^"]*'
# 实测：miktexsetup-5.5.0+<build>-x64.zip

# 1) 下载 + 解压 → 得 miktexsetup_standalone.exe（注意 _standalone 后缀）
#    实测 2.6 MB

# 2) 查官方语法（两子命令 download / install）
./miktexsetup_standalone.exe --help

# 3) download 然后 install（同参数）
EXE=E:/path/to/miktexsetup_standalone.exe
SRC='https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/win32/miktex/tm/packages/'
"$EXE" download --portable='E:\MiKTeX' --package-set=basic \
        --remote-package-repository="$SRC" --use-registry=no --modify-path=no
"$EXE" install  --portable='E:\MiKTeX' --package-set=basic \
        --remote-package-repository="$SRC" --use-registry=no --modify-path=no
```

**实测结果**：**88 秒**完成，**479 MB**，产物
`E:/MiKTeX/texmfs/install/miktex/bin/x64/{xelatex,kpsewhich,mpm,initexmf}.exe`
`xelatex --version` → `MiKTeX-XeTeX 4.18 (MiKTeX 26.5 Portable)`

**要点**：
- `basic` 包集**已含** `ctex` / `xeCJK` / `ctexart` / `fontspec` / `zhnumber` ⇒ **中文底座够用**，不必上 `complete`
- `--use-registry=no --modify-path=no` = 便携、不污染系统
- ⚠️ 前台 terminal 上限 600 s：网络慢时**必须** `background=True` + `notify_on_complete=True`
- ⚠️ **路径一律传 `E:/...` 风格**：Git Bash 会把 `/e/...` 转成 `E:\e\...` → `No such file`（`MSYS2_ARG_CONV_EXCL='*'` 本机实测无效）

---

## 二、便携模式的两个必知事实

```bash
kpsewhich --var-value=TEXMFHOME    # 便携下为「空」 → 自建包必须 --texmfhome 显式指定
kpsewhich --var-value=TEXMFLOCAL   # 自建用户 texmf 根，需 --register-root 才生效
```

```bash
# 自建并注册用户 texmf 根
mkdir -p 'E:/MiKTeX/texmf-local'
initexmf --register-root 'E:/MiKTeX/texmf-local'
```

---

## 三、把自建包 / 字体装进 texmf 树

**核心手法：用各包自带的委托安装器 + `--source local`**，吃本地克隆，**彻底绕开下载**
（仓库根级安装器（如 `scripts/install.py`）常仍要联网拉快照包，在不联网/GitHub 不通时直接失败：
实测报 `gitee:File is not a zip file`）。

```bash
PY='<项目>/.venv/Scripts/python.exe'
TM='E:/MiKTeX/texmf-local'

# A) 没有子命令的包（实测：bensz-fonts 这类）—— 直接给 --texmfhome
"$PY" '<repo>/packages/bensz-fonts/scripts/package/install.py' --texmfhome "$TM"

# B) 有 install 子命令的包 —— --texmfhome 必须在子命令「之前」!!
for p in bensz-nsfc bensz-paper bensz-thesis bensz-cv; do
  EXTRA=""; [ "$p" = bensz-nsfc ] && EXTRA="--ref main"   # ⚠️ 各包必填项不同
  "$PY" "<repo>/packages/$p/scripts/package/install.py" --texmfhome "$TM" \
       install --source local --path "<repo>/packages/$p" $EXTRA --force
done

# C) 刷新文件名库（不刷 kpsewhich 找不到）
initexmf --update-fndb
```

**踩过的四个坑**：
1. **`--texmfhome` 是顶层选项，必须放子命令之前**；放后面会被当子命令参数 → 解析失败
2. **各包 CLI 形态不统一**：有的无子命令、有的额外必填（`--ref`）⇒ **先逐个取真实 `--help`**，别套同一模板
3. **`--skip-python-deps`**：有的安装器会 `pip install --user -r requirements.txt`（**污染用户目录**、违反"项目内安装"规范、本机常失败）⇒ 跳过
4. **`--source local --path` 必须给绝对路径**，且和其它参数一样用 `E:/...` 风格

**验证**：
```bash
kpsewhich bensz-thesis.sty bensz-cv.cls bensz-nsfc.sty bensz-paper.sty
# 应全部命中 E:/MiKTeX/texmf-local/tex/latex/<pkg>/
```

**副作用**：这类安装器会往 `C:\Users\<user>\.<项目名>\` 写版本缓存（实测 **666 MB**）。
C 盘紧张时必须 `mv` 到 E 盘；⚠️ **重跑安装器会再生成一次**。

---

## 四、编译器行为：官方 wrapper vs 裸跑

```bash
# ✅ 官方入口（会用 TEXINPUTS 注入自建字体/包目录）
python packages/<pkg>/scripts/<name>_project_tool.py build --project-dir projects/<模板> [--variant all]

# ❌ 裸跑（自建字体/公共包的库通常必失败）
xelatex -interaction=nonstopmode main.tex
```

官方原文（`docs/bensz-fonts-support-model.md`）：
> 构建脚本**并不依赖当前工作目录刚好能找到字体文件**，而是**显式把字体目录加入 `TEXINPUTS`**。

⇒ **排障第一问永远是「官方 wrapper 也失败吗？」**：
- wrapper 成功 / 裸跑失败 → 是 `TEXINPUTS` 注入差异，**不是环境坏**
- wrapper 也失败 → 才进入环境排障（`references/cv01-fontawesome-case.md`）

---

## 五、缺包补装

```bash
initexmf --show-config-value='[MPM]AutoInstall'          # 应为 1
initexmf --show-config-value='[MPM]RemoteRepository'     # 应指向可用镜像
mpm --install=<pkg>                                      # 补单包（官方已标 deprecated）
# 编译时让缺包自动补齐：
xelatex -interaction=nonstopmode --enable-installer main.tex
```
⚠️ `-interaction=nonstopmode` 下**无法交互取包**，缺包（实测 `tabu.sty`）会直接算失败。

---

## 六、本机实测的模板级结果（作为"环境已就绪"的基线）

| 模板 | 结果 | 产物 |
|---|---|---|
| `paper-sci-01`（SCI 论文） | ✅ exit=0 | `main.pdf` 107,570 B |
| `NSFC_Young`（国自然标书） | ✅ exit=0 | `main.pdf` 1,258,127 B |
| `thesis-nju-master`（学位论文） | ✅ 出 PDF（仅 tikz overlay 首过告警） | `main.pdf` 460,907 B |
| `cv-01`（学术简历） | ❌ 未解 → 见 `cv01-fontawesome-case.md` | 无新产物 |

⚠️ **基线 PDF 的时间戳 = 克隆时刻**，别把仓库自带的旧 PDF 误判成本次构建产物；对时间戳、看 `.latex-cache/`。