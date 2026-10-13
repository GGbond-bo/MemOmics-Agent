# 回执核销探针的命令卫生（2026-10-11 实测，`deleg_8e3e2dac` 核销轮）

场景：判「这条 `delegate_task` 回执是不是迟到重放」时，要在交付物里做**覆盖计数**、在磁盘上做 **mtime / 字节数**取数。
这两个动作的命令写法有**静默坑**（不报错、只是少给数或给错数），逐条实测如下。

## 1. 覆盖计数：一次命令取全实体（✅ 照抄配方）

交付物 = `results/<sid>/results/AI_agent_前沿工作解读.md`（251 行 `(wc -l)` / 23,801 B）。

```bash
grep -o -i -E "cassia|chemcrow|paper2agent|sciencebuddy|biomni|chemgraph|deeprare|biomaster|co-scientist" \
  "<交付物路径>" | tr 'A-Z' 'a-z' | sort | uniq -c | sort -rn
```

实测输出（9 实体一次取全）：

```
19 paper2agent
18 biomni
16 sciencebuddy
16 cassia
14 deeprare
14 co-scientist
14 chemcrow
12 chemgraph
11 biomaster
```

判读：本批 4 篇（CASSIA / ChemCrow / paper2Agent / ScienceBuddy）全部命中 ⇒ 已消费；
配合落盘件 mtime 早于交付物 mtime（⓪-j ①）即可定案，无需 5 项 diff。

## 2. ⛔ 不要用 `&&` 串 `grep -c`

```bash
grep -c CASSIA f && grep -c ChemCrow f && grep -c paper2Agent f && grep -c ScienceBuddy f
```

实际只打印 3 行（`16 / 13 / 0`）：`paper2Agent` 精确大小写 **0 命中** ⇒ `grep -c` 退出码 1 ⇒ **`&&` 链当场断掉**，
第 4 个实体根本没跑。两个后果：
① 少取一个实体的数；② 已打印的那个 `0` 极易被误读成「该篇在交付物里不存在 ⇒ 本批未被消费」
（真值 **19** 次，只是大小写不同 —— 与 §二 第 3 项 `geNomad`/`GeNomad` 陷阱同源）。
⇒ 只用上面 §1 的单条 `grep -o | tr | sort | uniq -c`：无退出码分支，且顺带完成大小写归一。

## 3. ⛔ 复杂 shell payload 会被解析器硬拦（不是权限问题，重试同一串无效）

```bash
for k in CASSIA ChemCrow paper2Agent ScienceBuddy; do printf "  %-14s %s\n" "$k" "$(grep -c "$k" "$D")"; done
```

返回：

```
BLOCKED (hardline): command parser limit or malformed executable payload.
```

⇒ 探针一律写成**单用途一行命令**；需要多件事就**拆成多次 terminal 调用**（每次一个简单管道）。
`for … do … done` + 嵌套引号 + 多段 `$( )` 拼成一条 = 高风险 payload。

## 4. find 先行（复述 ⓪-k 纪律①，本轮再次踩到）

判「交付物在不在」**只认** `find . -name "<交付物名>"`（跨全会话目录）。
本轮单层 `ls results/AI_agent_前沿工作解读.md` 报 MISSING，真实位置是
`results/<sid>/results/AI_agent_前沿工作解读.md`（**嵌套了两层 `results/`**）。
⇒ 一次 `ls` 的 MISSING 不是证据，只说明「不在你猜的那一层」。

## 5. 反向封闭（复述 ⓪-k 纪律②，本轮照跑）

```bash
find results/<sid> -newermt "<交付物 mtime>" -type f | grep -v "/log/"
```

本轮非空项只有 `.loopx/goals/…/runs/*.json|.md` —— 框架自身的运行快照，**不是交付物**。
照实说明「仅 loopx 快照」即算反向封闭成立。