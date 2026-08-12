<!-- Canonical copy. If this file is duplicated into another skill, edit THIS copy
     (paper-polish/references/) and re-sync; scripts/check_shared_sync.py enforces parity. -->

# AI-tone guardrails and inflated-claim wordlist

Scan against these two lists when removing AI flavor or calibrating claim strength.
A hit does not automatically mean "delete"; it means stop and ask whether the word
carries information or merely performs depth.

## Typical AI-tone signals

Scan item by item; rewrite on hit:

- **Grandiose framing**: stands as a testament, is a testament to, pivotal moment,
  evolving landscape, reflects a broader, setting the stage, marking a shift.
  Delete; replace with concrete facts.
- **Shallow -ing tails**: highlighting / underscoring / emphasizing / ensuring /
  reflecting / showcasing hung at the end of a sentence to fake depth. Expand into
  a real clause or delete.
- **Marketing adjectives**: boasts, vibrant, rich (figurative), profound, nestled,
  in the heart of, groundbreaking, breathtaking. Delete.
- **Vague attribution**: industry reports suggest, observers have cited, experts
  argue, with no source. Name the real source or delete.
- **High-frequency AI words**: delve, intricate, tapestry, underscore, testament,
  garner, pivotal, vibrant, leverage, empower (as marketing verbs), encompass,
  stems from, pave the way for, notably, yielding, at its essence, impede.
  Replace with plain words.
- **Copula avoidance**: serves as / stands as / represents / boasts. Use is / are / has.
- **Negative parallelism, forced triads, fake ranges**: not only... but also...,
  it is not just... it is..., forcing three items, from X to Y when the two ends are
  not on one scale. State directly.
- **Synonym cycling**: the same object called three different names in one passage.
  Pick one name and keep it.
- **Hyphenated-pair pileup**: third-party, data-driven, end-to-end, real-time,
  cutting-edge stacked as decoration. Keep necessary terms, cut ornaments.
- **Fragmented headings**: a heading followed by one line that restates the heading.
  Delete or merge into prose.
- **Formatting noise**: excessive dashes, mechanical bolding, Title Case headings,
  emoji, curly quotes.
- **Chat politeness**: Great question, I hope this helps, as of my last update,
  You are absolutely right. Delete.
- **Filler and over-hedging**: in order to (use to), due to the fact that (use
  because), could potentially possibly (use may), empty upbeat closers.

Closing self-check: ask "where does this passage still read machine-written?", list
the remaining signals, then rewrite so it does not.

Reminder: after stripping every signal, prose can turn clean but lifeless, with
uniform sentence length and no acknowledged complexity. The fix, still without
inventing facts or inflating claims: vary sentence length, carry weight with exact
facts instead of stacked adjectives, and state real trade-offs and limitations
plainly. Voice comes from precision and honesty, not from noise.

## Inflated-claim wordlist (soften or flag unless the data genuinely supports it)

Do not auto-generate high-risk claims such as "first", "only", "best". When the
author's own draft contains them, do not silently keep them either: soften, or flag
for the author to confirm the evidence.

**English**: extraordinary, exceptional, remarkable, unprecedented, revolutionary,
groundbreaking, new paradigm, best, superior, state-of-the-art, proves,
conclusively, perfectly, first (without evidence), innovative, pioneering,
transformative, surpass, excel, breakthrough.

**Chinese**: 卓越、首次、唯一、最高、完美、碾压、遥遥领先、颠覆性、最优。

Safer replacement directions:

- prove: show / suggest, depending on evidence
- conclusively: delete, or "to our knowledge"
- best / superior: among the strongest / performs competitively
- unprecedented: delete, or bound to a specific scope
- first: "to our knowledge, the first" (only when actually checked), or bound to
  the studied cohort or setting

The point is not to weaken every strong word. It is to make claim strength match
evidence strength. When the evidence is strong and the scope is stated, strong
verbs are correct.

## One-line summary

De-AI-toning and de-inflation are two faces of the same job: make the text honest.
No tone that carries zero information; no claim the evidence cannot carry. Edit the
expression, never the facts: do not invent data, experiments, or citations to prop
up a strong conclusion.
