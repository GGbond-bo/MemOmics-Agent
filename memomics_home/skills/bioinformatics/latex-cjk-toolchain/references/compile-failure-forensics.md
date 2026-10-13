# 编译失败取证 + 对照否证：完整案例（2026-10-12 实测）

> 用途：一份「编译失败该怎么查、假说该怎么验」的实操范本。
> 案例来源：ChineseResearchLaTeX `projects/cv-01`（中英文学术简历模板）在便携 MiKTeX 26.5 / XeTeX 4.18 下编译失败。

## 一、症状链（真实报错顺序）

1. `\section{\faGraduationCap\ 教育背景}` 处开始失控
2. `wrong@fontshape` **递归**刷屏
3. 日志被 **NUL 字节洪水**（`^^@`）淹没
4. 最终 `TeX capacity exceeded [pool size=5440117]`

**诊断第一步永远是先把日志洗干净**（否则 grep 什么都匹配不到）：

```bash
tr -d '\000' < main.log | grep -v '^\^@' > clean.log
grep -n -E '! |Fatal|Error|not found|fontshape' clean.log | head -50
```

## 二、被否证的假说（⚠️ 不要再沿这条路排查）

**假说**：hyperref 对 `\section` 参数做 PDF 书签字符串展开，导致 fontawesome 命令失控。

**为什么曾被高度采信**：L2 多角色辩论 **7/8 席位独立收敛**到同一假设。
独立一致度这么高，很容易直接拿它去改模板。

**怎么被否证**：写**最小复现对照实验**——plain 版（`\section{\faGraduationCap ...}` + hyperref + fontawesome5），
一次只留这一个变量：

| 组 | 内容 | 结果 |
|---|---|---|
| 实验组 | 完整 `bensz-cv` 上下文 | ❌ 失控（pool size 溢出） |
| **对照组** | plain 最小文档 | ✅ **exit=0，正常出 PDF（6,646 B）** |

⇒ **对照组未复现故障 = 假说否证**。故障**必须依赖 bensz-cv 特定上下文**，不是通用 hyperref 行为。

**教训**：辩论收敛 ≠ 实证。若直接采信，会浪费整轮并给模板引入错误改动。
（配套规程见 `debate-core` §3.3 与 SKILL.md 第五节。）

## 三、真线索（当前最佳解释，仍未修复）

- `\faGraduationCap` **不是 fontawesome 官方宏**，而是 bensz-cv 自带文件定义的：
  `packages/bensz-cv/fontawesomesymbols-generic.tex:375`
  ```tex
  \def\faGraduationCap{\faicon{graduation-cap}}
  ```
- 而本机装的 fontawesome 是 **v4.6.3.1**（`ProvidesPackage{fontawesome}[2016/05/15 v4.6.3.1]`），
  **`\faicon` 属 fontawesome v5 语法** → 典型的 **v4 / v5 定义层混用**。
- 且 `bensz-cv.cls` 内**没有** fontawesome 加载行。

**已试且无效（勿重复）**：装 `fontawesome` / `fontawesome5`、`initexmf --mkmaps`、
`initexmf --update-fndb`、`*_project_tool.py clean`、手工 `TEXINPUTS='.../bensz-fonts//;'` + `-recorder`、
多趟编译、去掉 `--enable-installer`。

**未执行的候选修法（按优先级）**：
1. 确认 bensz-cv 期望的 fontawesome 版本 → 调整加载顺序，让 v5 定义生效；
2. 改用 v5 官方写法 `\faIcon{graduation-cap}`（注意大小写：v5 是 `\faIcon`，v4 是 `\faicon`）；
3. 在 `main-zh.tex` 侧用 `\texorpdfstring` 包裹图标命令，绕开书签展开路径（**注意**：由第二节可知
   书签展开并非充分原因，此法只能算缓解，需实测确认）。

**验证方式（必须）**：改完跑官方 `cv_project_tool.py build` → 记 `exit code` + PDF 字节数 + 时间戳。
时间戳尤其重要——仓库**自带基线 PDF**，不核对时间戳会把旧文件当新产物。

## 四、同一轮里其它可复用结论

| 模板 | 结果 | 产物 |
|---|---|---|
| `paper-sci-01` | ✅ exit=0 | main.pdf 107,570 B |
| `NSFC_Young` | ✅ exit=0 | main.pdf 1,258,127 B |
| `thesis-nju-master` | ✅ 出 PDF（仅 tikz overlay 首过警告） | main.pdf 460,907 B |
| `cv-01` | ❌ 未解 | 无新 PDF |

> 前三条 = 「工具链本身是好的」的对照证据：cv-01 的失败**不是** TeX 装错了，
> 而是该模板自身的宏/字体定义问题。**排查时先建立这个基线**，能省掉大量环境怀疑。