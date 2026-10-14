# `search_files(target='content')` 在 `.gitignore` 目录里静默返回 0 命中

**实测日期**：2026-10-11 · **危害等级**：高（能把结论**反过来**）

## 现象

```
search_files(pattern="Co-Scientist|DeepRare|ChemGraph",
             target="content", path="results/memomics-75ba0499")
→ {"total_count": 0}
```

同一路径、同一时刻：

```
search_files(pattern="*", target="files", path="results/memomics-75ba0499")
→ {"total_count": 44, "files": [... 13 个 .txt/.md 全在 ...]}
```

后续用 `read_file` 直读，**证明这些词确实在文件里**（例如
`results/.../data/lit_text/Co-Scientist.txt`、`.../data/AI摘要_Co-Scientist.md`）。

## 真因（工具机制，不是工具坏了）

- `target='content'` 底层走 **ripgrep**，**默认尊重 `.gitignore`** ⇒ 被 ignore 的目录/文件
  **整体跳过**，返回 `0`，且**不报错、不给任何提示**。
- `target='files'` 走的是文件枚举路径，**不受 `.gitignore` 影响**。
- 本项目里 `results/`、`work/`、`uploads/`、`cache/` 都在 ignore 目标内 ——
  而这几个目录恰恰是**产物最常待的地方**（`results/<sid>/` 更是全部交付物的家）。

两条结论互相矛盾（files 说 44 个文件在、content 说一个词都没有），
**矛盾本身就是信号**：不要选一个信，要换工具复验。

## 危害：假 0 会反转结论

当轮差点据此判定「本批 4 篇论文的摘要未落盘 ⇒ 需要重建」，
而事实**完全相反**（摘要全在盘，只是 grep 没去看它们）。
若照此动作，等于把已完成的工作重做一遍。

同族机制见 `delegation-orchestration` §二 假 0 家族（口径 / 键名 / 分组 / 层级 / **工具静默跳过**）
—— 本条是其中**唯一不出在探针写法上、而出在「探针跑在哪个目录」**的入口。

## 对策（照抄）

1. `target='content'` 返回 0 时，**先问「这个目录被 ignore 了吗」**：
   - 用 `read_file` **直读**该文件（最省，一步到位）；
   - 或在 `terminal` 里显式 `grep -r --no-ignore <pattern> <path>`；
   - 或先 `git check-ignore -v <path>` 确认该路径的 ignore 归属。
2. **`target='files'` 与 `target='content'` 的结论不得互推**：
   files 列得出 ≠ content 找得到。
3. 判「文件在不在 / 有没有内容」的**权威**仍是 `read_file` / `stat` / `ls -l`；
   **`grep` 只作方向性交叉印证**，不作定案证据。

## 一句话

**0 命中不等于没有。在这几个目录里，`0` 先当「我没去看」，别当「它不存在」。**