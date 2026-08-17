---
name: multi-role-debate
description: >-
  Run and troubleshoot multi-role structured LLM debates (pro 3 + con 4 + judge)
  for analysis conclusions and parameter choices. Covers the isolation model,
  the serial pro→con→judge fallback (works when the 8-way parallel tool fails),
  provider-key injection debugging (DEEPSEEK_API_KEY), and deepseek-v4-flash
  reasoning_content quirk. Use whenever debate_analysis is required by a skill's
  iron rules or when a debate comes back 8/8 "辩论生成失败".
category: General Utility
tags: [debate, multi-agent, review, quality, llm]
when_to_use: >-
  [multi-role-debate] 需要跑多角色辩论、debate_analysis 连续失败、参数/结论需要
  多角色裁决、用户要求"先正方再反方最后LLM判决"时。
---

# Multi-Role Debate: Run, Fail, Recover

Every analysis skill mandates a multi-role debate (`debate_analysis`) after
critical steps. This skill covers the debate mechanism itself: what it is, why
it fails, and how to run it so it actually produces a verdict.

## The Debate Model (isolation is the point)

- **Pro side**: 3 independent editors (biology / statistics / bioinformatics),
  each an independent LLM call with ONLY their own prompt in `messages`.
- **Con side**: 4 independent editors (biology / statistics / bioinformatics /
  history-errors), also independent and blind to pro.
- **Judge**: the ONLY role that sees all 7 arguments; returns
  `scores`, `verdict` (support/modify/need_more_info), `confidence`,
  `recommended_params`, `reasoning`.
- Context isolation = each role gets a fresh `messages` array with only its
  prompt. Pro never sees con; editors never see each other.

## Symptom: 8/8 "辩论生成失败" — debug in this order

1. **Check the injected provider first (most common root cause).**
   MemOmics `webui/server.py::_sync_debate_env()` picks the API key for the
   debate's independent LLM calls. It used to iterate `_provider_keys` and the
   FIRST provider matching `"dcs"` in its id/url got injected — but that
   provider's key can be stale/invalid (401), so ALL 8 role calls fail
   identically while the interactive model (deepseek official) still works.
   Fixed 2026-08-01: inject `_current_model` (the in-use model config) first,
   fall back to `deepseek` provider, and only then the dcs match.
   If you see 8/8 failures, verify what got injected:
   ```python
   import os
   print(os.environ.get("DEEPSEEK_API_KEY", ""), os.environ.get("DEEPSEEK_BASE_URL", ""))
   ```
2. **Test one role call directly with httpx** (200 → then the injection is fine;
   401 → wrong provider; timeout → network/provider quota).
3. **deepseek-v4-flash puts the answer in `reasoning_content`**, `content` is
   often empty. The debate caller already has the fallback:
   ```python
   if (not content or len(content.strip()) < 10) and msg.get("reasoning_content"):
       content = msg["reasoning_content"]
   ```
   Your own ad-hoc test scripts must apply the same fallback or they'll report
   "content empty" falsely.
4. **Serial execution is now the default.** `_call_role_parallel` was changed
   from 8-way `ThreadPoolExecutor` concurrency to serial (2026-08-01): parallel
   calls hit provider quota limits and caused 7× 8/8 full failures. Roles are
   still isolated (each has its own single-message prompt); serial order
   preserves isolation. Context isolation, NOT parallelism, is what matters.
5. **P0 (2026-08-10): the engine is parameterized.** `debate_analysis()` now
   accepts `mode` (homogeneous/adversarial/multi_model/temperature), `rounds`,
   and `role_model_map`, sourced from `config.yaml` → `debate:` section.
   Cache keys include a mode fingerprint — different architectures never share
   cached verdicts. See `docs/debate-core-design.md` for the full design.

## Serial pro→con→judge fallback (validated, 8/8 success)

When `debate_analysis` itself keeps failing, run the debate yourself with a
serial script: Phase 1 pro (3 calls, isolated) → Phase 2 con (4 calls,
isolated, blind to pro) → Phase 3 judge (1 call, sees everything). Serial
calls avoid parallel-quota failures while preserving isolation.

- Template: `scripts/run_serial_debate.py` (copy, edit TOPIC/CONTEXT/PROMPTS).
- Key details in the template:
  - read key/base_url from `hermes_home/model_config.json` (`_current_model`
    equivalent — the working provider), NOT from provider_keys dcs-cloud
  - `import httpx` (NameError bites if omitted)
  - PROMPTS keys are `pro_biology/pro_statistics/pro_bioinfo` and
    `con_biology/con_statistics/con_bioinfo/con_history` — the
    `_bioinformatics` spelling is a KeyError trap
  - one `call_llm(prompt, label)` function with retries + reasoning_content
    fallback + call_id; returns error dict on final failure (don't crash)
  - archive JSON to `results/<session>/log/debate_{ts}_serial_<topic>.json`
- Archive shape (matches debate_analysis output): `{topic, context, model,
  timestamp, elapsed_sec, pro{...}, con{...}, judge{content}}` — the judge
  content contains the JSON verdict; parse it for the final report.

## Reporting a debate verdict

Lead with the verdict, then the evidence:

- **verdict=modify is a real outcome, not a failure.** The hdWGCNA red-module
  debate (2026-08-01) returned modify/high: metacell-level correlation is
  pseudo-replicated (n=6482 → individual-level n=24 recheck is mandatory),
  fiber-type composition confounds module-trait correlation, and "reversible"
  wording should be weakened to an interaction claim. Encode that as the
  next analysis step, don't bury it.
- **If the debate tool is down, say so plainly and offer the serial script.**
  The user asked "你为什么辩论失败呢？再试一试" — the answer was root cause +
  fix, not "API 挂了" as a dead end.

## Pitfalls

- Never skip the required debate because a previous attempt failed. The user
  audits debate/verdict/self-evolution compliance ("你这些参数辩证了吗？
  多agent辩论了吗？").
- `_load_debate(topic, context)` caches by md5(topic+context) with a 72h TTL —
  re-run with slightly different context to force a fresh debate.
- Don't use the interactive model's answer as the debate: isolation requires
  fresh per-role prompts, not one big prompt.
