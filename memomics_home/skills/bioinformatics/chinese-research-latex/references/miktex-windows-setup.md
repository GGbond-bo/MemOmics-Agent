# MiKTeX on Windows（免管理员便携）+ CRL 公共包本地安装（2026-10-12 实测）

> 场景：Windows 11 + 无 TeX 发行版 + 无管理员权限 + C 盘紧张 + GitHub 不通。
> 全部实测通过并记录真实报错，勿凭记忆改动。

## 一、装 MiKTeX（便携、免管理员、落 E 盘）

1. 从清华镜像**列目录**取真实文件名（**不要猜** `miktexsetup-x64.zip`，实测 404）：
   `https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/win32/miktex/setup/windows-x64/`
   → 实为 `miktexsetup-5.5.0+1763023-x64.zip`
2. 下载解压 → 得到 **`miktexsetup_standalone.exe`**（注意 `_standalone` 后缀，不是 `miktexsetup.exe`）
3. 官方语法（`--help` 实证）：`install.py download|install` 两子命令
   ```bash
   EXE download --portable='E:\MiKTeX' --package-set=basic \
     --remote-package-repository='https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/win32/miktex/tm/packages/' \
     --use-registry=no --modify-path=no
   EXE install  （同参数）
   ```
   - `basic` 包集已含 ctex / xeCJK / ctexart / fontspec / zhnumber —— 中文底座够用
   - `--use-registry=no --modify-path=no` = 不写注册表、不改 PATH
   - 实测 **88 秒**完成，479 MB，产物 `E:/MiKTeX/texmfs/install/miktex/bin/x64/{xelatex,kpsewhich,mpm,initexmf}.exe`

## 二、装 CRL 公共包（关键：本机 GitHub 不通 → 走本地克隆）

根级 `scripts/install.py` **仍要联网下载快照** → 本机失败（`gitee:File is not a zip file`）。
**改用各包自带委托安装器 + `--source local`**（官方支持，绕开全部下载）：

```bash
PY='E:/MemOmics-Agent/.venv/Scripts/python.exe'
RWIN='E:/MemOmics-Agent/third_party/CRL'
TM='E:/MiKTeX/texmf-local'

# 1) fonts（无子命令）
"$PY" "$RWIN/packages/bensz-fonts/scripts/package/install.py" --texmfhome "$TM"
# 2) 其余四包（--texmfhome 必须在子命令「之前」）
for p in bensz-nsfc bensz-paper bensz-thesis bensz-cv; do
  EXTRA=""; [ "$p" = bensz-nsfc ] && EXTRA="--ref main"      # nsfc 的 --ref 必填
  "$PY" "$RWIN/packages/$p/scripts/package/install.py" --texmfhome "$TM" \
     install --source local --path "$RWIN/packages/$p" $EXTRA --force
done
# 3) 刷新文件名库
initexmf --update-fndb
```
- **`bensz-paper` 必须加 `--skip-python-deps`**：否则它跑 `pip install --user -r requirements.txt`（污染用户目录，违反"项目内安装"规范）且本机失败
- 验证：`kpsewhich bensz-thesis.sty bensz-cv.cls ...` 应全部命中 `E:/MiKTeX/texmf-local/tex/latex/<pkg>/`
- ⚠️ **副作用**：安装器把版本缓存写到 `C:\Users\<user>\.ChineseResearchLaTeX\`（实测 **666 MB**）。C 盘紧张时必须迁走（`mv` 到 E 盘）；重跑安装器会再生成

## 三、编译（官方路径 = 注入 TEXINPUTS，不是裸跑 xelatex）

官方原文（`docs/bensz-fonts-support-model.md`）：
> 官方构建脚本**并不依赖当前工作目录刚好能找到字体文件**，而是显式把 `packages/bensz-fonts/` 加入 `TEXINPUTS`。

```bash
cd <repo 根>
"$PY" packages/bensz-cv/scripts/cv_project_tool.py       build --project-dir projects/cv-01          --variant all
"$PY" packages/bensz-thesis/scripts/thesis_project_tool.py build --project-dir projects/thesis-nju-master
"$PY" packages/bensz-paper/scripts/paper_project_tool.py  build --project-dir projects/paper-sci-01
"$PY" packages/bensz-nsfc/scripts/nsfc_project_tool.py    build --project-dir projects/NSFC_Young
```
工具子命令：`build / clean / compare`（compare 做像素级基线比对）。

## 四、本机实测结果（2026-10-12）

| 模板 | 结果 | 产物 |
|---|---|---|
| `paper-sci-01` | ✅ exit=0 | main.pdf 107,570 B |
| `NSFC_Young` | ✅ exit=0 | main.pdf 1,258,127 B |
| `thesis-nju-master` | ✅ 出 PDF（仅 tikz overlay 首过警告） | main.pdf 460,907 B |
| `cv-01` | ❌ 残留未解 | 无新 PDF（仓库基线 PDF 时间戳为克隆时刻，勿误判） |

## 五、坑表（全部亲测）

1. **MSYS 路径转换**：Git Bash 下 `MSYS2_ARG_CONV_EXCL='*'` **对本机不生效**。给原生 Windows 程序（python.exe / xelatex / miktexsetup）**一律传 `E:/...` 风格**，否则 `/e/...` 被转成 `E:\e\...` → `No such file`
2. **前台超时上限 600 s**：>10 min 的任务（download+install）必须 `background=True` + `notify_on_complete=True`
3. **不要猜镜像文件名**：先 `curl` 列目录
4. **`mpm --install`**：可补包（如 `tabu`），但官方已标 deprecated；用前先 `initexmf --show-config-value='[MPM]AutoInstall'` 确认=1、`[MPM]RemoteRepository` 指向镜像
5. **内联 shell 含反引号会炸**：grep 模式里带 `` ` `` 触发 `unexpected EOF` → 诊断逻辑写进 `.sh` 再跑
6. **日志会被 NUL 污染**：`tr -d '\000' | grep -v '^\^@'` 再读
7. **cv-01 残留问题**（MiKTeX 26.5）——**未解，但机理已逼近**：
   - 稳定卡 `main-zh.tex` 的 `\section{\faGraduationCap\ 教育背景}` → `wrong@fontshape` 递归 → NUL(`^^@`) 洪水 → `TeX capacity exceeded [pool size=5440117]`
   - **已试且无效**：装 fontawesome/fontawesome5、`initexmf --mkmaps/--update-fndb`、`cv_project_tool.py clean`、手工 `TEXINPUTS='…/bensz-fonts//;'` + `-recorder`、多趟、不带 `--enable-installer`
   - ⚠️ **假说已被否证，勿再沿此路排查**：一度怀疑 hyperref 对 `\section` 参数做 PDF 书签字符串展开；**最小复现对照实验推翻**——`\section{\faGraduationCap ...}` + hyperref + fontawesome5 的 plain 版 **exit=0 正常出 PDF**（6,646 B）。⇒ 故障必须依赖 bensz-cv 类上下文，不是通用 hyperref 行为
   - ✅ **真正的线索**：`\faGraduationCap` **不是 fontawesome 官方宏**，而是 bensz-cv 自带的 `packages/bensz-cv/fontawesomesymbols-generic.tex:375` 定义：`\def\faGraduationCap{\faicon{graduation-cap}}`；而本机装的 fontawesome 是 **v4.6.3.1**（`ProvidesPackage{fontawesome}[2016/05/15 v4.6.3.1]`），`\faicon` 属 **v5 语法** → 典型 **fontawesome v4/v5 定义层混用**；`bensz-cv.cls` 内无 fontawesome 加载行
   - **下一步待验证方向**（未执行）：确认 bensz-cv 期望的 fontawesome 版本，调整加载顺序或让 v5 定义生效；或改用 `\faIcon{graduation-cap}`（v5 官方写法）

## 六、环境记录

- MiKTeX：`E:/MiKTeX`（portable 26.5 / XeTeX 4.18），bin `E:/MiKTeX/texmfs/install/miktex/bin/x64`
- 用户 texmf 根：`E:/MiKTeX/texmf-local`（已 `initexmf --register-root`）
- 便携模式下 `TEXMFHOME` 为空 → 必须显式 `--texmfhome`