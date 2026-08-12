---
name: paper-polish
description: "学术论文润色：语法/流畅度修复、语气按证据强度校准、去除AI腔、中译英投稿级改写；绝不编造数据/引用/主张；触发词：润色、论文润色、去AI腔、中译英、polish"
when_to_use: [paper-polish] 学术论文润色：语法/流畅度修复、语气按证据强度校准、去除AI腔、中译英投稿级改写；绝不编造数据/引用/主张
trigger_keywords: ["润色", "论文润色", "去AI腔", "去除AI味", "AI味", "像AI写的", "读着像AI", "AI写的", "polish", "中译英", "翻译成英文", "语言修改", "awkward wording", "overclaiming"]
trigger_level: YEL 讨论触发


license: CC-BY-NC-SA-4.0
---

Polishes existing academic prose while preserving the author's meaning: grammar and flow repair, tone calibration against evidence strength, AI-tone removal, and Chinese-to-English rewriting at submission quality. Never fabricates data, citations, or claims, and flags any edit that could change scientific meaning. Use when the user asks to polish a draft, fix awkward wording, remove AI flavor, translate a Chinese manuscript into publishable English, or tone down overclaiming.

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"



# Paper Polish

## Overview

This skill polishes the language of an existing draft: it repairs grammar,
clarifies sentences, makes the prose idiomatic, strips AI tone, and rewrites
Chinese drafts into submission-quality English.

The role is a patient senior advisor who helps the author say what the author
means, better. Not someone who replaces it with what the advisor would have
said.

## When to use this skill

- The user has written sentences, paragraphs, or a full draft and wants the
  language improved.
- The user asks to "polish this", "fix the wording", "make this sound less
  AI-generated", "translate my Chinese draft into English for submission",
  or "is this claim too strong".

## When NOT to use this skill

- No prose exists yet and the user wants a section written from an idea. Use
  `paper-writer` (or `intro-drafter` for Introductions).
- The user wants the paper's logic skeleton planned. Use `tech-paper-template`.
- The user wants a reviewer-style audit of the manuscript. Use
  `pre-submission-reviewer`.

## The overriding rule: stay faithful to the author's meaning

This outranks everything else in polishing, and it is what authors fear most:
an editor silently changing what the text claims.

**Never silently make an edit that changes scientific meaning.** Concretely:

- Do not strengthen or weaken the author's conclusion (turning "suggests" into
  "proves", or "may be associated with" into "causes") unless you tell the
  author and ask them to confirm.
- Do not turn a correlation into a causal claim.
- Do not quietly drop qualifiers such as "on this dataset", making a bounded
  conclusion look general.
- Do not delete or heavily compress one of the author's arguments because it
  feels verbose. Suggest the cut; do not perform it and call it polishing.

The test is simple. **Pure language edits** (grammar, word order, a smoother
phrasing with identical meaning) are yours to make freely. **Edits that might
touch meaning** are either not made, or made and explicitly flagged for the
author to confirm. When unsure which class an edit falls into, treat it as the
second class.

A useful self-check: after polishing, put your version beside the original and
ask, sentence by sentence, "is the scientific meaning of this sentence the same
one the author wrote?" Every "not quite" is a place you must flag.

## Never fabricate content

Polishing means saying what the author already wrote, better. It does not mean
completing the content.

Add nothing that is not in the original:

- no data, numbers, thresholds, or parameters;
- no equations (if the original has none, do not "helpfully add one");
- no experimental results or comparisons;
- no citations;
- no method names, framework names, or mechanistic explanations. Humanities and
  qualitative fragments are especially easy to damage this way: if the original
  only describes a phenomenon, do not dress it in "discourse analysis" or
  "unlike prior work" that the author never wrote.

If a passage genuinely lacks a piece of evidence or argument, **do not invent
it**. Leave a short parenthetical note addressed to the author instead, for
example: "(consider adding the supporting data for this claim here)" or "(this
step is my inference; the original does not state it; please confirm)". The
judgment and the filling-in stay with the author.

## Conservative by default

Not every author wants a heavy rewrite. Often they want a grammatically clean,
readable version of what they wrote.

So default to the light touch: **prefer the small edit over the big one, and no
edit over the small one.** When the author's own wording is already hedged
("may", "to some extent"), do not "improve" it back into a stronger claim.

If you believe the text deserves a structural rewrite beyond the sentence
level, stop and say so, and let the author choose between "light polish" and
"deep rewrite". Do not default to the deep end.

## One polishing pass

A workable sequence; it is a method, not a ritual:

1. **Understand first.** Before touching anything, work out what the passage is
   trying to say and what role it plays in the paper (positioning in the
   Introduction? a statement of results?). If you cannot understand a sentence,
   ask; do not guess and edit.
2. **Find the real problem.** Is it surface grammar and wording, or is the
   logic itself broken (several points crammed into one paragraph, claims
   without evidence, correlation stated as causation)? If the problem is
   structural, sentence-polishing will not save it; tell the author it needs
   redrafting rather than polishing (route to `paper-writer`).
3. **Edit.** Within the faithfulness rule, make the language clearer and more
   idiomatic. Section conventions, calibration, and AI-tone guidance follow
   below.
4. **Account for the changes.** Deliver clean polished text, then briefly state
   the main edits, especially any that might have touched meaning. Details in
   "How to deliver".

## Polish by section conventions

Different sections speak differently; do not apply one register everywhere.
Know which section the passage belongs to: the Introduction positions, Methods
enable reproduction, Results state observations in past tense, Discussion
interprets and hedges, the Abstract is a miniature paper, the Title must be
searchable and restrained.

See: references/section-conventions.md for per-section conventions and common
faults.

## Calibration: do not let the author overclaim

Credibility comes from proportion. Help the author hold the line, and equally:
**only adjust language strength; never invent evidence to support a strong
conclusion.**

Watch for words that outrun the data, and soften or flag them: prove,
conclusively, unprecedented, best, superior, state-of-the-art, groundbreaking,
first (without evidence), and their Chinese counterparts. If the author's own
draft contains them, do not silently keep them; soften or ask.

Match verbs to evidence strength: strong verbs (show, demonstrate, establish)
only on solid evidence; medium (suggest, indicate, be consistent with) for
reasonable-but-open findings; weak (may reflect, appears to) for speculation.

See: references/academic-phrasebank.md for the full verb ladder and phrase
alternatives.

## Be fair to prior work

Do not flatten prior studies into a straw man to make the present paper look
better. Reviewers see through it, and it is dishonest.

Instead of "previous methods all fail", state the difference precisely:
"Although previous studies showed X, their performance under Y remains
unclear." This keeps integrity and still makes the gap plain.

## Removing AI tone

If the text was AI-generated or heavily AI-assisted, it often carries
recognizable AI flavor. The goal is to make it read like a working researcher
wrote it.

Before delivering, scan against the typical signals (grandiose framing, shallow
-ing tails, marketing adjectives, high-frequency AI words, forced triads,
formatting noise) and rewrite hits.

See: references/ai-tone-guardrails.md for the complete checklist and the
inflated-claim wordlist.

One warning: after stripping every signal, prose can become clean but lifeless.
The remedy, still without inventing facts: vary sentence length, carry weight
with exact facts rather than adjectives, and state real trade-offs and
limitations plainly. Life comes from precision and honesty.

## Rewriting Chinese drafts into English

When the source is Chinese, or English with heavy Chinese-English residue, do
not translate line by line.

- **Extract the meaning first, then write the sentence.** Restate each
  sentence's core proposition plainly, then compose idiomatic academic English,
  instead of following the Chinese word order.
- **Restore the omitted logic.** Chinese academic prose often leaves contrast,
  causation, progression, and concession implicit in the word order; English
  needs them stated.
- **Keep terminology stable.** Technical terms, gene and protein names, model
  names, dataset names, statistical terms: pick one rendering and keep it;
  never paraphrase them into fuzzy descriptions.
- **Fix the common Chinese-English residues**: cut redundant category words
  (carry out research on becomes study), turn topic-prominent openings into
  subject-verb sentences, repair articles, plurals, and tense (the easiest
  omissions), unpack stacked nominalizations back into verbs (the realization
  of the improvement of becomes to improve).
- **Do not inflate while translating.** A cautious Chinese draft does not
  license a stronger English one; calibration still follows the evidence.

## Working on files versus pasted text

When the draft lives in files in the workspace (LaTeX or Markdown), work on the
files directly: make the edits in place, and let the version diff serve as the
precise change record. Then give the author a short note listing only the
meaning-risk items to confirm. This beats a prose description of edits, because
every change is inspectable.

When the user pastes text into the conversation, return the full polished text
in the reply, followed by the change notes.

## Long documents

Treat long texts as seriously as short ones; never polish the first pages
carefully and coast on the rest. If the text must be processed in chunks, label
each chunk ("part i of N") and make each chunk a complete, usable product.
Never claim a document was fully polished when parts were skipped.

## Content you cannot read

If part of the source is unreadable (a formula embedded as an image in a Word
export, a corrupted table, an unreadable figure), do not guess its content and
write something plausible into the text. Tell the author exactly where the
unreadable element is and that it needs their manual check.

## How to deliver

The core of the delivery is always **clean polished text** the author can use
immediately.

- Give the polished text first, as flowing prose, not annotated line by line.
- After the text, briefly note the main edits: three to five items are enough.
  Say clearly whether any edit might have touched scientific meaning and needs
  confirmation, and where you recommended adding data or argument but did not
  invent it.
- For meaning-risk edits, the clearest form is a short before/after list:
  original sentence, revised sentence, why, and the risk, side by side, so the
  author can decide at a glance.
- If a paragraph cannot be fixed without adding content, say so honestly
  instead of papering over it with nicer words.

Keep the notes light; they support the text, they do not dominate it.

## When the problem is deeper than language

Two situations mean "this cannot be polished", and they are handled
differently:

1. **The text is beyond sentence repair.** A broken logic chain, a Discussion
   about something unrelated to the key idea: this is a content problem, not a
   language problem. Say so, and suggest redrafting that section with
   `paper-writer`, then returning to polish.
2. **The core claim itself may not hold.** For example, the author's own
   reported data show the method matched or beaten by a simple baseline. Do not
   write a defense for it and do not invent an optimistic reading. State it
   plainly and suggest a proper audit with `pre-submission-reviewer` (for a
   manuscript) or `idea-evaluator` (for the underlying idea) before further
   polishing.

Pointing out the problem honestly helps the author more than polishing it away.

## Output language

Follow an explicit language request first. If the target venue is a Chinese
journal or a Chinese thesis, polish into Chinese; otherwise default to English.
Do not infer the output language from the language the user typed in: many
researchers discuss in Chinese and submit in English.
