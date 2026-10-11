# 产品线细节与构建命令（来源：上游 `docs/manual-setup-guide.md` + `AGENTS.md`）

## 1. 公共包（`packages/`，装入 TEXMFHOME）

| 包 | 说明 |
|---|---|
| `bensz-fonts` | 共享字体基础包（字体资产 + 统一字体 API）；被其它包作为强制依赖 |
| `bensz-nsfc` | NSFC 公共包（三套国自然模板的共享样式基础，`type=general\|local\|young` 切换） |
| `bensz-paper` | SCI 论文公共包（PDF / DOCX 双输出） |
| `bensz-thesis` | 毕业论文公共包（硕士/博士 + 像素级验收脚本 + DOCX 初稿导出） |
| `bensz-cv` | 学术简历公共包（中英文模板 + 像素级验收脚本） |

安装（仓库根目录执行；`--mirror gitee` 在中国大陆更稳）：

```bash
python scripts/install.py install                       # 默认全部
python scripts/install.py install --packages bensz-nsfc,bensz-paper,bensz-thesis,bensz-cv
python scripts/install.py install --packages bensz-cv --mirror gitee
python scripts/install.py install --force               # 版本一致时会自动跳过，需覆盖才加
python scripts/install.py list                          # 查看支持的包
```

- 安装器会自动探测 `kpsewhich` / `mktexlsr` / `texhash` / `initexmf`，兼容 TeX Live / MiKTeX；TeX 不在 PATH 或要自定义 texmf 树时加 `--texmfhome <路径>`。
- 包级版本管理（可选）：`python packages/bensz-paper/scripts/package/install.py install|rollback|check|use --ref v4.0.0`；状态目录统一在 `~/.ChineseResearchLaTeX/<package>/`。
- NSFC 包可用 `.nsfc-version` 锁文件（`ref + commit + package_version + template_version`）+ `rollback` 回退；仓库开发时可 `--source local --path packages/bensz-nsfc --ref local-dev` 装本地工作树。

## 2. 项目层结构约定（改内容时）

- 正文维护在 `extraTex/**/*.tex`；`main.tex` 是入口。
- `extraTex/@config.tex` 只保留一行公共包入口，例如 `\usepackage[type=general]{bensz-nsfc-common}`。
- **不要复制公共实现到项目层**；共享样式问题应上收到 `packages/bensz-*`。
- DOCX 导出**不保存第二份正文源**（运行期临时生成 Markdown）。

## 3. 构建命令（官方 wrapper 优先，别裸跑 xelatex）

```bash
# NSFC（含省基金）
python packages/bensz-nsfc/scripts/nsfc_project_tool.py build --project-dir projects/NSFC_Young

# SCI / 投稿信：PDF + DOCX 双输出、字数统计
python packages/bensz-paper/scripts/paper_project_tool.py build --project-dir projects/paper-sci-01
python packages/bensz-paper/scripts/paper_project_tool.py build --project-dir projects/paper-coverletter-01
python packages/bensz-paper/scripts/paper_project_tool.py count-words projects/paper-sci-01/extraTex/body/introduction.tex

# 学位论文 / 博士后
python packages/bensz-thesis/scripts/thesis_project_tool.py build --project-dir projects/thesis-nju-master
python packages/bensz-thesis/scripts/thesis_project_tool.py build --project-dir projects/thesis-nju-master --tex-file baseline.tex
python packages/bensz-thesis/scripts/thesis_project_tool.py docx  --project-dir projects/thesis-smu-master

# 简历（中英文）
python packages/bensz-cv/scripts/cv_project_tool.py build --project-dir projects/cv-01 --variant all
```

## 4. DOCX 导出已处理的行为

- Pandoc 默认表格补稳定可见横向边框；Word 侧标题/作者/参考文献关键样式按当前 LaTeX profile 统一。
- 数学公式经 HTML5 + MathML 中间态落成 **Word 原生公式对象**（避免 `$\gamma$` 源码泄漏）。
- 项目未声明参考文献命令时，自动跳过 `biber` 与 citeproc（适配 `paper-coverletter-01` 这类投稿信）。
- `count-words` 传 `main.tex` 会递归跟随 `\input`/`\include`，忽略命令名、引用 keys 与公式源码。
- 复杂表格/算法/代码块/TikZ/PDF 专属构造 → 在 `.latex-cache/docx/main_docx_quality_report.md` 提示人工复核；学校 Word 样式配 `--reference-doc`。

## 5. 仓库级约定（上游 `AGENTS.md`）

- AI 任务工作区：`./.bensz-api/task-{yyyymmdd-hhmm}-{简短描述}/`，其下每个实际使用的 skill 单独 `input/ output/ log/`。
- 缓存与中间文件走 `.bensz-api/` 或 `.latex-cache/`，**不得污染仓库根目录/源码目录**。
- 未经明确要求不删/不迁/不覆盖用户文件；不擅自 commit/branch。
- 提交与发布分离：只有上传成功才可称「已发布」。

## 6. Windows / 本机注意

- 本机 **无 TeX 发行版**（`xelatex`/`latexmk`/`kpsewhich` 均未找到）→ 编译与公共包安装需先装 TeX Live（推荐，官方测试平台之一）或 MiKTeX。
- shell 是 git-bash（MSYS）：路径用 `/e/MemOmics-Agent/...` 或 `E:/MemOmics-Agent/...`，**不要**用 `/c/...` 风格拼 E 盘。
- 平台对 `rm -rf` 有删除门禁：清理临时目录时改成「克隆到新目录 + `mv`」。