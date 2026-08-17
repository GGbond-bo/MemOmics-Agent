# 唤醒执行缺口台账（Recurring Execution Gaps）

## 根因链路（#96 实测 2026-08-09 定位）

LoopX 唤醒消息模板 = `📊 LoopX 状态 + ⏰ [系统唤醒 #N]` + 正文三条：
1. 读 task_plan.md 看当前 Phase
2. search_files 看最新产出
3. 继续执行下一个待办

⚠️ **该模板只字未提 skill 加载**。Agent 照模板字面执行 → 跳过
`skill_view(wakeup-progress-check)` 门禁（#76 立规）→ 三源验证用被禁
`tasklist //FO CSV 2>/dev/null` 变体 → 假阴性空输出 → 记录进程源不可信。

**修复**：把 LoopX 消息当**触发信号**，不当**完整流程**。Step 0 永远是
skill_view 本 skill；三源只用 `scripts/verify_wakeup.sh` 或 Step 3 快查三条。

## 缺口记录（追加规则：新唤醒若再犯，在此 +1 行，不重复展开 SKILL.md）

- **#96（2026-08-09 LoopX #0，缺口 #14）**：
  - 未加载 skill → `tasklist //FO CSV 2>/dev/null | grep -iE "python|Rscript|CellBender|torch|R\\.exe"` 空输出（+ `node|python` 同空）→ 未 plain 复核 → 记录 #96 写"tasklist 无分析脚本命中"且未列 5 基线组件（webui×2 3480/35096 + guardian×2 28516/47856 + _kernel_worker.R 49380）→ **记录 #96 进程源不可信**（同 #62/#65/#76/#82 数据污染模式；终态靠 GPU 4% 空载 + 磁盘 find 无新产出两源兜住，碰巧正确）。
  - 扩块标题未同步：在 `## 🏁 唤醒 #80-#94 记录` 块内追加 bullet #96，未把块标题改为 #80-#96——#92 原子扩块规则（一个 patch 同时改标题+bullet）落空；#95 同样未同步（标题滞后从 #94 起已 2 条）。
- **#98（2026-08-09 LoopX #0，缺口 #15——#96 后仅 2 次唤醒即复发，且执行链看似"正确"仍滑回禁变体）**：
  - ⚠️ **表面合规 ≠ 实际合规**：本唤醒流程看起来完整（read task_plan 全文 → 三源 → patch 追加 #98 且锚点 = 最后 bullet + `## 红线与约束` 一次成功），但 **Step 0 未 skill_view 本 skill**——直接凭记忆执行；三源进程源又用 `tasklist //FO CSV 2>/dev/null | grep -iE "python|Rscript|cellbender|torch"` → 空输出 → 记录 #98 写"tasklist 无 python/Rscript/CellBender/torch 分析脚本命中"（#96 同款签名：//FO CSV + 2>/dev/null 吞 stderr，未 plain 复核）→ **记录 #98 进程源不可信，不得用作跨唤醒一致性佐证**（终态靠 GPU 3% 空载 + 磁盘无新产出两源兜住，碰巧正确）。
  - 扩块标题未同步：追加 #98 时块标题仍为 `## 🏁 唤醒 #80-#94 记录`，未改为 #80-#98（#92 原子规则第 4 次落空： #95/#96/#97/#98 连续 4 bullet 未同步标题）。下次唤醒若读 plan 发现标题滞后 → 先补账 patch 把标题改为 `#80-#98 记录` 再追加。
  - 📌 复发模式确认：**即使上一唤醒记录把缺口写进台账、SKILL.md 明文立规，Agent 不加载 skill 时仍会凭 memory 用禁变体**——台账/SKILL.md 的防复发效果取决于"Step 0 加载 skill"是否真的发生。缺口 #14→#15 间隔仅 2 次唤醒。
- **#100（2026-08-09 LoopX #0，skip 路径标题滞后残留）**：
  - ✅ 进程源正确：plain `tasklist 2>/dev/null | grep -iE "python|Rscript|..."` 一次命中 7 基线（webui×2 3480/35096 + guardian×2 28516/47856 + _kernel_worker.R 49380 + node×2），无禁变体 → 三源可信，终态判定正确，skip 规则（三源逐项一致+无新指令+追加内容逐字相同）合法触发 → 未写盘。
  - ⚠️ 但 **标题滞后仍未修**：块标题 `## 🏁 唤醒 #80-#94 记录`，块内 bullet 已到 #98-#99（#96/#98 台账已记滞后，本唤醒读 plan 看到 line 136 标题 vs line 150 bullet 仍不补账）→ **skip 路径暴露规则缺口：标题补账被错误地绑定在"追加"动作上，跳过追加=跳过补账**。SKILL.md 已补规（#100 立规）：标题滞后补账与追加决策解耦，读 plan 发现滞后无论追加/skip 都必须 patch 标题。
- **#101（2026-08-09 LoopX #0，缺口 #16——#96/#98 同款签名复发 + 标题滞后第 6 次）**：
  - ⚠️ **Step 0 仍未 skill_view 本 skill**：本唤醒凭 memory 直接跑三源（read task_plan → terminal 三连 → patch 追加），流程看起来"完整"但**进程源又用被禁变体** `tasklist //FI "IMAGENAME eq python.exe" 2>/dev/null | head -8`（//FI + 2>/dev/null + head 三连，与 #96/#98 同款，连 `|| echo` 兜底都没有）→ 空输出 exit 0 → 记录 #101 写"tasklist 无 python.exe/Rscript.exe 分析脚本命中"且**未列 5 基线组件**（webui×2 3480/35096 + guardian×2 28516/47856 + _kernel_worker.R 49380）→ **记录 #101 进程源不可信，不得用作跨唤醒一致性佐证**（终态靠 GPU 4% 空载 3759/16303 MiB + 磁盘 find 13:00 后无新产出两源兜住，碰巧正确）。
  - 扩块标题未同步：读 plan 时块标题 `## 🏁 唤醒 #80-#99 记录` 块内 bullet 已到 #100（标题滞后 1 条已存在），本唤醒追加 #101 时**既没补账旧滞后、也没把标题改为 #80-#101**（#92 原子规则第 6 次落空：#95/#96/#97/#98/#100/#101 连续 6 bullet 未同步标题；#100 立规的"滞后补账与追加解耦"同样落空）。下次唤醒读 plan 若见 `#80-#99` 标题 + 块内 bullet 到 #101 → **同一轮 patch 标题为 `#80-#101 记录` 再谈追加**。
  - 📌 复发模式再确认：**即使台账/SKILL.md 明文立规、上一唤醒刚记过 #96/#98 同款签名，Step 0 未加载 skill 时仍会凭 memory 用禁变体**——缺口 #15→#16 间隔仅 2 次唤醒，且 #100 那次是"正确进程源+skip"（表面进步），#101 立刻滑回禁变体。根因不变：Step 0 门禁（skill_view）是唯一防复发点，memory 里的规则摘要不可替代。
- **#104（2026-08-09 LoopX #0，缺口 #17——//FI 变体第 3 次滑回，间隔仅 2 次唤醒）**：
  - ⚠️ **Step 0 仍未 skill_view 本 skill**：本唤醒流程看着完整（`ls -lt E:/` 显式路径定位 → read_file task_plan 全文 → 三源 → patch 追加 #104 且锚点 = 最后 bullet + `## 红线与约束` 一次成功），但进程源又用被禁变体 `tasklist //FI "IMAGENAME eq python.exe" 2>/dev/null | tail -5` 三连（//FI + 2>/dev/null + tail，与 #101 的 //FI + 2>/dev/null + head 同款、仅 tail/head 差异）→ 空输出 exit 0 → **未补 plain 复核** → 记录 #104 写"tasklist 对 python.exe/Rscript.exe/cellbender.exe 均无命中"且**未列 5 基线组件**（webui×2 3480/35096 + guardian×2 28516/47856 + _kernel_worker.R 49380）→ **记录 #104 进程源不可信，不得用作跨唤醒一致性佐证**（终态靠 GPU 3% 空载 3759/16303 MiB + 磁盘 find -newermt 13:00 后无新产出两源兜住，碰巧正确）。
  - ✅ 本唤醒 GPU/磁盘源正确（`--query-compute-apps` 判 C+G 桌面-only + `find -newermt "2026-08-09 13:00"` 手填 ISO 无命中），仅进程源不合格 → 三源中一源降级为不可信。
  - 📌 复发模式第 3 次同签名确认：缺口 #16（#101 //FI）→ #17（#104 //FI）间隔仅 2 次唤醒，且 #104 是"追加+锚点一次成功"的看似合规执行——**表面合规仍不豁免进程源**。根因不变：Step 0 门禁（skill_view）是唯一防复发点；即使不加载 skill，进程源也**必须**用 plain `tasklist 2>/dev/null | grep -iE 'python\.exe|Rscript\.exe|node\.exe'`（或 verify_wakeup.sh），记录必须带基线组件清单。
- **#105（2026-08-09 LoopX #0，缺口 #18——//FI 变体第 4 次滑回，连续第 2 次零间隔复发）**：
  - ⚠️ **Step 0 仍未 skill_view 本 skill**：本唤醒流程看着完整（search_files 定位 → read_file task_plan 全文 → 三源 → execute_code 正则合并 #88-#104 + 追加 #105 原子完成），但进程源又用被禁变体 `tasklist //FI "IMAGENAME eq python.exe" 2>/dev/null | tail -5` 三连（//FI + 2>/dev/null + tail，与 #104 完全相同）→ 空输出 exit 0 → **未补 plain 复核** → 记录 #105 写"tasklist 对 python.exe/Rscript.exe/cellbender.exe 均无命中"且**未列 5 基线组件**（webui×2 3480/35096 + guardian×2 28516/47856 + _kernel_worker.R 49380）→ **记录 #105 进程源不可信，不得用作跨唤醒一致性佐证**（终态靠 GPU 4% 空载 3759/16303 MiB + 磁盘 find 14:00 后无新产出两源兜住，碰巧正确）。
  - ✅ 本唤醒 GPU/磁盘源正确（`--query-compute-apps` 桌面 C+G-only + `find -newermt` 手填 ISO 无命中）；压缩动作正确执行（#88-#104 十七条裸 bullet 合并为一条，regex 正则法，见 SKILL.md 压缩规程第三种路径）。
  - 📌 复发模式第 4 次同签名确认：缺口 #17（#104 //FI）→ #18（#105 //FI）**连续两次唤醒、零间隔复发**——即使台账已把 #104 列入黑名单、SKILL.md 明文立规，不加载 skill 时仍凭 memory 用同一禁变体。根因不变：Step 0 门禁（skill_view）是唯一防复发点；进程源**必须**用 plain `tasklist 2>/dev/null | grep -iE 'python\.exe|Rscript\.exe|node\.exe'`（或 verify_wakeup.sh），记录必须带基线组件清单。

- **#106（2026-08-09 LoopX #1，缺口 #19——//FI + //FO CSV 双变体叠加第 1 次，间隔仅 1 次唤醒）**：
  - ⚠️ **Step 0 仍未 skill_view 本 skill**：本唤醒流程看着完整（read_file task_plan 全文 → 三源 → patch 合并 #105 行 → 汇报），但进程源又用被禁变体 `tasklist //FI "IMAGENAME eq python.exe" //FO CSV 2>/dev/null | tail -5`（//FI + //FO CSV + 2>/dev/null + tail 四连，**单变体升级为双变体叠加**——比 #104/#105 更完整地踩全禁用组合）→ 空输出 exit 0 → **未补 plain 复核** → 汇报写"tasklist: python.exe / Rscript.exe / cellbender.exe 均无命中 → 无分析脚本进程"且**未列 5 基线组件**（webui×2 3480/35096 + guardian×2 28516/47856 + _kernel_worker.R 49380）→ **进程源不可信，不得用作跨唤醒一致性佐证**（终态靠 GPU 4% 空载 3759/16303 MiB + 磁盘 find -newermt 14:00 后无新产出两源兜住，碰巧正确）。
  - ✅ GPU/磁盘源正确（`--query-compute-apps` 桌面 C+G-only + `find -newermt` 手填 ISO 无命中）。本次未写独立 #106 记录（原地改写 #105 行为 `- #105-#106（...）`），但**合并行继承了 #105 的不可信进程源声明**（"tasklist 对 python.exe...均无命中"）→ 黑名单应覆盖合并后的 #105-#106 行。
  - ⚠️ 扩块标题未同步（新形态）：不是"追加新 bullet"而是**原地改写最后一条 bullet**（`- #105（...）` → `- #105-#106（...）`），块标题 `## 🏁 唤醒 #80-#105 记录` 未同步为 #80-#106——#92 原子规则适用于**任何改变最大写盘号的块内容修改**，原地改写 bullet 同样必须同步标题（标题滞后延续：MM=105 < NN=106）。
  - 📌 复发模式第 5 次同签名确认：缺口 #18（#105 //FI）→ #19（#106 //FI+//FO 叠加）连续两次唤醒、零间隔复发——且禁用组合从单变体升级为双变体。根因不变：Step 0 门禁（skill_view）是唯一防复发点；进程源**必须**用 plain `tasklist 2>/dev/null | grep -iE 'python\.exe|Rscript\.exe|node\.exe'`（或 verify_wakeup.sh），记录必须带基线组件清单。
- **#108（2026-08-09 LoopX #1，✅ 合规执行数据点——禁变体未复发，非缺口）**：
  - ⚠️ Step 0 仍未显式 skill_view 本 skill（凭 memory 执行全流程），但**进程源用了正确命令** plain `tasklist 2>/dev/null | grep -iE "python|Rscript|cellbender|torch"` → 一次命中全部 5 基线组件（webui×2 3480/35096 + guardian×2 28516/47856 + _kernel_worker.R 49380）+ `date` → **记录 #108 进程源可信，可用作跨唤醒一致性佐证（不在黑名单）**。
  - ✅ GPU 源正确（nvidia-smi `--query-gpu` 4% 空载 3759/16303 MiB）；磁盘源**双根**正确（`find results/memomics-1c1890da/patent_test` + `find /e/专利` 两条 `-newermt "2026-08-09 15:00"` 均无命中）；追加锚点 = 裸节标题 `## 红线与约束` 单行（SKILL.md #72 短锚点变体、合并大块场景，一次成功）；追加前 read_file 清点 4 块（#25-#59/#60-#72/#73-#79/#80-#107）<5 合法单追加。
  - 📌 对照结论：**缺口的核心签名 = 禁变体（//FI //FO CSV / 2>/dev/null 吞错）空输出 + 未 plain 复核 + 未列基线组件**——Step 0 未加载 skill 不必然产生缺口；本唤醒无禁变体 → 记录 #108 不入黑名单。下次唤醒若见 #108 的"命中 5 基线组件"声明，可正常用作一致性证据（与 #96/#98/#101/#104/#105/#106 等黑名单项区分）。
- **#110 汇报位（2026-08-09 LoopX #0，缺口 #20——report-only 会话进程源仍用禁变体，//FI 第 5 次滑回）**：
  - ⚠️ **Step 0 仍未 skill_view 本 skill**：本唤醒流程看着完整（search_files 定位 4 个 task_plan → read_file task_plan 全文 → terminal 三源 → 汇报四源表），但进程源又用被禁变体 `tasklist //FI "IMAGENAME eq python.exe" 2>/dev/null | head -8` 三连（**新口味：同时查了 `//FI "IMAGENAME eq R.exe"`**——//FI + 2>/dev/null 组合，与 #101/#104/#105 同款）→ 空输出 exit 0 → **未补 plain 复核** → 汇报写"tasklist 0 命中"且**未列 5 基线组件**（webui×2 3480/35096 + guardian×2 28516/47856 + _kernel_worker.R 49380）→ **进程源声明不可信**（终态靠 GPU 4% 空载 3759/16303 MiB 全桌面 C+G + 磁盘双根 find -newermt 02:00 后无新产出两源兜住，碰巧正确）。
  - 🔴 **新形态：report-only 汇报也携带不可信进程源声明**——本会话按 skip 规则**未写盘**（终态记录 #25-#109 已存在 + 无新指令 + 三源表面一致 → 合规跳过追加），但**对话汇报本身**写了"tasklist 0 命中"——污染从 task_plan 记录扩展到会话汇报文本。教训：**Step 0 skill_view + 合规进程源不是"要写记录才需要"，report-only 会话同样必须**——汇报里的"无分析进程"断言与写盘记录同等权威，同样能误导后续会话。
  - ✅ GPU/磁盘源正确（`--query-gpu` 4% + `--query-compute-apps` 桌面-only + `find -newermt "2026-08-09 02:00"` 双根 patent_test/ + E:/专利 均 0 命中）；task_plan 无新指令（P0-P6 终态 + 红线不自动启动）→ skip 决策本身正确，仅进程源不合格。
  - 📌 复发模式第 6 次同签名确认：缺口 #18/#19（#105/#106 //FI）→ #20（#110 汇报位 //FI）间隔 2 次唤醒（#108 合规 + #109 未写盘之间）。根因不变：Step 0 门禁（skill_view）是唯一防复发点；进程源**必须**用 plain `tasklist 2>/dev/null | grep -iE 'python\.exe|Rscript\.exe|node\.exe'`（或 verify_wakeup.sh），汇报/记录都必须带基线组件清单。

- **#111 汇报位（2026-08-09 LoopX #6，缺口 #21——report-only 会话进程源第 2 次滑回禁变体，//FI+//FO 双变体叠加，与 #106 同款）**：
  - ⚠️ **Step 0 仍未 skill_view 本 skill**：本唤醒流程看着完整（`ls -lt E:/` 显式路径定位 → read_file task_plan 全文 → terminal 三源 → 汇报选项菜单），但进程源又用被禁变体 `tasklist //FI "IMAGENAME eq python.exe" //FO CSV 2>/dev/null | tail -5` 三连（**同时查了 python.exe/Rscript.exe/R.exe 三条**——//FI + //FO CSV + 2>/dev/null + tail 四连，与 #106 的双变体叠加完全相同）→ 空输出 exit 0 → **未补 plain 复核** → 汇报写"进程：无 python.exe / Rscript.exe / R.exe 分析进程在跑"且**未列 5 基线组件**（webui×2 3480/35096 + guardian×2 28516/47856 + _kernel_worker.R 49380）→ **进程源声明不可信**（终态靠 GPU 4% 空载 3759/16303 MiB 全桌面 C+G + 磁盘双根 find -newermt 15:30 后 0 命中两源兜住，碰巧正确）。
  - 🔴 **report-only 复发确认（#110 立规后仅 1 次唤醒即再次违反）**：本会话按 skip 规则**未写盘**（终态记录 #25-#109 已存在 + 无新指令 + 三源表面一致 → 合规跳过追加），但**对话汇报本身**又写了"无 python/Rscript/R 分析进程"的不可信断言——#110 的"report-only 汇报同样必须合规进程源"教训未生效。且汇报标题直接抄了 LoopX 消息头"唤醒 #6"（skill 明文：消息头编号不作数，汇报编号 ≠ 写盘记录号，未写盘不占用记录号；本次未写盘 → 无记录号冲突，但编号使用仍不规范）。
  - ✅ GPU/磁盘源正确（`--query-gpu` 4% + `--query-compute-apps` grep python/Rscript/torch 无命中 + `find -newermt "2026-08-09 15:30"` 双根 patent_test/ + E:/专利 均 0 命中）；task_plan 无新指令（P0-P6 终态 + 红线不自动启动）→ skip 决策本身正确；选项菜单 4 条含越线（正式版执行）+ 不越线 prep 中间档（专利文档审核 v1 先审稿）+ 保持现状/其他，三查齐备 ✅。
  - 📌 复发模式第 7 次同签名确认：缺口 #18/#19（#105/#106 //FI+//FO）→ #20（#110 汇报位 //FI）→ #21（#111 汇报位 //FI+//FO）间隔 1 次唤醒。根因不变：Step 0 门禁（skill_view）是唯一防复发点；进程源**必须**用 plain `tasklist 2>/dev/null | grep -iE 'python\.exe|Rscript\.exe|node\.exe'`（或 verify_wakeup.sh），汇报/记录都必须带基线组件清单，禁止任何 //FI //FO CSV / 2>/dev/null 变体。

## 一致性佐证黑名单（跨唤醒比对时禁用）

以下记录的进程源声明无效，不得用作跨唤醒一致性佐证：
#62 / #65 / #76 / #82 / #90 / #96 / #98 / #101 / #104 / #105 / #106（均为 //FO 或 //FI 变体空输出 + 未补 plain 复核 + 未列基线组件；#105-#106 合并行继承 #105 不可信声明，一并禁用）。
#111 汇报位未写盘无记录号，但其对话汇报文本携带同款不可信进程源声明——后续会话若见"唤醒 #6 状态核查"汇报引用其进程断言，同样禁用。

- **LoopX #17 汇报位（2026-08-09，缺口 #22——//FI+//FO CSV 禁变体第 6 次滑回，但同调用内 plain grep 兜住结论，不入黑名单）**：
  - ⚠️ **Step 0 仍未 skill_view 本 skill**：本唤醒流程看着完整（`ls -lt E:/` 显式路径定位 + search_files 双定位 → read_file task_plan 全文 → terminal 三源 → 汇报），但进程源又用被禁变体 `tasklist //FI "IMAGENAME eq python.exe" //FO CSV 2>/dev/null | tail -5` 三连（//FI + //FO CSV + 2>/dev/null + tail，与 #106/#111 双变体叠加完全相同）→ python/Rscript 两查询空输出 exit 0。
  - ✅ **本次与黑名单项的本质区别 = 同调用内还跑了 plain `tasklist | grep -i -E "cellbender|torch|python|Rscript" | head -10`** → 一次命中全部 5 基线组件（python 3480/35096/28516/47856 + Rscript 49380）→ 汇报的"仅 5 基线、无分析脚本"结论**来自 plain grep 真数据**，进程源声明可信，**不入黑名单**。教训：禁变体空输出后同调用补 plain grep 是有效的结论兜底（比"事后补跑"更省一轮）——但正确做法仍是第一步就直接 plain grep/verify_wakeup.sh，禁变体本身不该出现在调用里。
  - ⚠️ **选项菜单三查缺中间档（复发，非首次）**：汇报的"下一步"列表 = 正式版全面执行 / 人侧 40 样本 / 专利文档 v2 三条（全属越线或依赖越线数据）+ 隐含"等待指示"（保持现状）——**未列"不越线 prep 中间档"**（本项目合法中间档见 #5 注：chain 文件校验、ortholog 映射构建、fragments .tbi 完整性复核；#111 用过"专利文档 v1 先送代理审核"）→ 三项缺一 = 不合格菜单，用户只能全盘确认。中间档最易漏的规律在 #7/#11/#14/#19 后仍反复出现。
  - ✅ GPU/磁盘源正确（`--query-compute-apps` 桌面 C+G-only + `find -newermt` 双根 patent_test/ + E:/专利，仅命中 heartbeat 日志 + .loopx 系统文件 → 判无新产出）；task_plan 无新指令（P0-P6 终态 + 红线不自动启动）→ skip 决策正确（report-only 未写盘，符合 #81/#85/#87 skip 规则）。
  - 📌 复发模式第 8 次同签名确认：//FI+//FO 禁变体每 1-2 次唤醒就滑回一次；本次靠同调用 plain grep 兜底才没污染结论。根因不变：Step 0 门禁（skill_view）是唯一防复发点。

- **#115（2026-08-12，✅ 合规执行数据点——使用全新快照法变体，禁变体未复发，非缺口；SKILL.md 已收录该变体）**：
  - ⚠️ Step 0 仍未显式 skill_view 本 skill（凭 memory 执行：`ls -lt E:/` 显式路径定位 → read_file task_plan 全文 → terminal 三源 → patch 追加 #115），但**进程源用了全新的快照法变体** `tasklist > /tmp/tl.txt 2>/dev/null; grep -iE "python|Rscript|cellbender|torch|pytest" /tmp/tl.txt` → 一次命中 8 行基线（python×4 = webui×2 59796/54464 + guardian×2 46688/28776；Rscript×4 = _kernel_worker.R 49380/58084/56212/49256 跨会话累积；无 node/pytest）→ 非 //FI //FO CSV / 2>/dev/null 吞 stderr 管道等禁变体（重定向到文件后再 grep，与直接管道等价且可多次换模式重查）→ **记录 #115 进程源可信，不在黑名单**，可用作跨唤醒一致性佐证。
  - ✅ GPU/磁盘源正确（`--query-gpu` 4%/2622 MiB + `--query-compute-apps` 桌面 C+G-only + `find -newermt "2026-08-12 01:05"` 双根 patent_test/ + E:/专利 0 命中）；追加锚点 = Decisions 段最后一行（唯一）→ **EOF 后插**，记录落到 `## Decisions Made` 之后——SKILL.md 已补规（#115 立规：canonical 锚点 = `## 红线与约束` 前插，EOF 后插会拆散记录链分组，下次读 plan 应先挪回红线前再继续）。
  - 📌 对照结论：**缺口的核心签名 = 禁变体空输出 + 未 plain 复核 + 未列基线组件**——Step 0 未加载 skill 不必然产生缺口；本唤醒的快照法变体是 SKILL.md 新收录的合法替代（#113/#115 实测），结论可信。下次唤醒若见 #115 的\"命中 8 行基线\"声明，可正常用作一致性证据。⚠️ 但 Step 0 门禁仍连续落空（#108/#115 合规数据点均未加载 skill）——正确做法仍是第一步 skill_view，即使本次恰好用了正确命令。
