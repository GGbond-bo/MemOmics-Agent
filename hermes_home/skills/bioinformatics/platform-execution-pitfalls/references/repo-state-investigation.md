# 仓库状态事实调查（git status 解析 + 技能库构成）

用户会周期性问「仓库这些改动文件都是什么」「为什么这么多文件」。

**这类问题是事实问题，必须查 `git status` 实况回答**（不许凭印象），但**查法有讲究** ——
本轮（2026-10-01，memomics-afd2d418）在解析与轮次铺开上各踩一次。

---

## 1. 取路径：一律 `git -c core.quotepath=false status --porcelain`

**症状**：`git status --porcelain -uall | awk '{print $2}'` 拿到的文件名是**转义残片**，
据此报出的「异常文件名」是错的 —— 本轮把它报成 `2xnull第四MWUp`，真名是 `2xnull且MWUp`。

**根因**：git 默认 `core.quotepath=true`，对含非 ASCII / 特殊字符（`[`、空格、引号）的路径
**加引号并做 C 风格八进制转义**（形如 `"2x\346\260\224..."`）。`awk '{print $2}'` 把它当名字取走，
再传给 `ls`/`read_file` 必然找不到 → 极易得出「疑似误建文件 / 文件不存在」的错误结论。

**正解**：

```bash
git -c core.quotepath=false status --porcelain -uall      # 真名，可直接喂给 ls/stat/read_file
```

**同族注意**：`-uall` 下未跟踪项是 `?? path`、已跟踪是 ` M path`（前导空格），
所以 `awk '{print $2}'` 只在**无重命名（`R  old -> new`）**时可靠；要严谨就用
`awk '{print $NF}'` 或 `git status --porcelain -z` 配合 `tr '\0' '\n'`。

**判据**：**上报「异常/怪文件名」之前，必须先用 `core.quotepath=false` 复核一次**，
再决定是否说「疑似误建」。把转义残片当真名 = 把自己的解析 bug 报成数据问题。

---

## 2. 一次查够，不要递进式铺轮次

**本轮实际轨迹（7 轮只读，中途被循环检测 OOB 强制干预）**：
按顶层目录分组 → 按文件类型 → 看跟踪状态 → 抽 skill.json diff → 看 mtime 分布 → 查怪名 → 再查 md diff。

检测器按**调用形态**（同工具 × 相似参数结构）判相似，不看每轮命令是否真的不同 ——
「追一个事实」的递进式只读调查天然命中（同族见 SKILL.md 坑表「批量同构调用」「逐项核对」诸行）。

**正解：一条命令一次给全**，然后直接作答（要更细就跑第二条，但别一次只回答一个子问题）：

```bash
cd <repo> && echo "=== 分组 ===" && git -c core.quotepath=false status --porcelain -uall \
  | awk '{print $2}' | awk -F/ '{print $1"/"$2}' | sort | uniq -c | sort -rn | head -15 \
&& echo "=== 类型 ===" && git -c core.quotepath=false status --porcelain -uall \
  | awk '{print $2}' | sed 's/.*\.//' | sort | uniq -c | sort -rn | head -12 \
&& echo "=== 跟踪状态 ===" && git status --porcelain -uno | awk '{print $1}' | sort | uniq -c \
&& echo "=== 非技能库改动（真名） ===" && git -c core.quotepath=false status --porcelain -uall | grep -v 'hermes_home/skills'
```

要 mtime 分布时**别一条条 `stat`**（`xargs -I{} stat -c '%y' {}` 打几百个文件很慢且形态像批量同构）：
用 `git diff --stat` 抽样就够，分布问题只在「是否集中在某一天」时才需要。

---

## 3. `hermes_home/skills` 为什么有几百个改动文件（可直接复用的答案）

技能库在仓库里的组织方式是 **一个技能 = 一个目录**：

| 文件 | 作用 | 为什么会在改动列表里 |
|---|---|---|
| `skill.json` | 元数据：`trigger_keywords` / `trigger_level` / `proven_params` | **管「这个技能什么时候被自动触发」** → 全库批量升级时一改就是几百个 |
| `SKILL.md` | 技能正文（步骤、参数、踩坑） | **管「用的时候怎么做」** → 每次踩坑/裁决都会累积回写 |
| `scripts/` | 技能自带脚本 | 沉淀新脚本时新增 |
| `SKILLS_INDEX.md` | 全库总索引 | 每加/删一个技能就多/少一行 |

**实测构成（2026-10-01）**：777 个改动全在 `hermes_home/skills/` 下
= 368 md（`SKILL.md` 346 + 索引 1 + 其余）+ 336 json（`skill.json`）+ 58 py + 16 yaml + 15 R。
其中 **skill.json 的 mtime 高度集中：302 个在 2026-09-23 一天完成** —— 那天给**每个**技能补了
`trigger_keywords` + `trigger_level`。单文件形态是「42 行 → 250 行」（涨的是触发词数组，一个词一行），
不是逻辑改动。

**意义**：这一层**不是产品代码，是 agent 的经验层**。所以：

- 仓库那 4 个 skill 测试（`test_skills_registry` / `test_skills_sync` / `test_skill_routing_matrix` /
  `test_skill_trigger_contract`）**只校验注册表一致性**，不校验 SKILL.md 内容质量 ——
  「测试全绿」不等于「技能写得好」。
- 改这一层的正确验证 = JSON/YAML 可解析 + 脚本 sha256 对齐 + 上述 4 个测试（见
  `user-script-sedimentation-completion.md`）。

**顺带的运行时垃圾**（属「跑起来会变」的文件，应进 `.gitignore` 而不是提交）：
`tmp/dask-scratch-space/*.lock`、`hermes_home/processes.json`、`hermes_home/env_inventory.json`、
`hermes_home/remote/jobs.jsonl`、`hermes_home/.config__*.tmp`。

**提交建议口径**（用户问「要不要提交」时给分组、不要自己 commit）：
① 技能库元数据升级（那批同日 `skill.json`）② 技能内容累积（各 `SKILL.md`）
③ 垃圾文件先加 `.gitignore` 再提交。用户明说「未 commit」不算问题 —— 仓库本就长期数百个改动文件，
但**新沉淀的 skill 文件必须 `git add`**（见 SKILL.md 坑表「沉淀的最后一道门是 git add」行）。