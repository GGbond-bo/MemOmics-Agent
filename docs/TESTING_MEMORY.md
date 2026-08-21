# 单会话上下文 + 记忆 测试说明（TESTING_MEMORY）

MemOmics 的「单会话上下文逻辑」与「记忆」经过多轮审计/压测沉淀为可重复的离线测试门禁。

## 快速跑（gate）

```powershell
pwsh scripts/gate_memory.ps1        # 只跑上下文/记忆相关用例（离线，~1s）
python -m pytest -m memory -q       # 等价：按 memory marker 全跑
```

全量回归：`python -m pytest webui/tests -q`（唯一一间既有失败是 `test_frontend_ux::test_single_script_block`
的 index.html 结构断言，与上下文/记忆无关，未触碰前端）。

## 覆盖什么

| 套件文件 | 覆盖 |
|---|---|
| `test_context_arch.py` (17) | P1 usable() 预算、P2 writer(§1-§11/单写者/路径守卫)、P5 增量边界、P4 分段重建、编排 fail-open、FTS 召回 |
| `test_requirements_memory.py` (10) | REQUIREMENTS 提取/去重/上限/digest 携带/rollup 同带/scripts 清单/助手指令过滤 |
| `test_long_context.py` (9) | 脚手架剥离、预算/尾窗/结构化 checkpoint 折叠 |
| `test_single_session_stress.py` (24) | 多场景/极端/对抗：预算非法值、脏内容、并发 writer 单写者、300 条反复滚动 upto 单调、空输出不劣化 checkpoint、seeded fuzz 不抛异常、digest 有界 |

## 关键不变量（防回归重点）

1. **P5 边界单调**：无"新片段"时绝不重写 checkpoint（`upto` 不回退）。
2. **好摘要不被占位顶掉**：`read_checkpoint` 优先选"最新且 ≥400B 有实质内容"档。
3. **writer 单写者**：同一会话并发触发只落盘一次；文件名毫秒+随机后缀防同秒覆盖。
4. **记忆不丢**：REQUIREMENTS 每轮无条件进 digest；折叠重建时仍出现（`必须带 P 值` 类要求随 rollup 存活）。
5. **fail-open**：无 LLM / writer 异常 / 脏历史 → 确定性回退或原样返回，绝不崩、绝不丢消息。
6. **REQUIREMENTS 卫生**：发给助手的指令（"只用一句话回复/不要调用任何工具"）不再入库。

## 真实数据验证（一次性，记录在案）

- `memomics-2274ab75`：767 条 user/assistant → (b) 卫生 760；默认 usable 下 measure=98,528 不压缩（正确）；
  小预算下回放正确选用 3.6KB §-checkpoint（upto 748）重建 4 块 + 尾窗。
- live 记忆召回：问"脚本放哪个目录" → 直接答 `scripts/`（该约定只存于 REQUIREMENTS，不在尾窗）。
- live 卫生：自检消息后 REQUIREMENTS 不再新增噪音行。
