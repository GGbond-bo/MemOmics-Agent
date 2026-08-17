---
name: chai1
description: "Structure prediction for protein, nucleic-acid, and small-molecule complexes with the Chai-1 foundation model (Chai Discovery 2024, github.com/chaidiscovery/chai-lab). Reach for this skill to predict "
when_to_use: "[chai1] OpenAI4S 移植：Structure prediction for protein, nucleic-acid, and small-mo..."
version: 1.0.0
author: OpenAI4S Contributors (PKU-YuanGroup)
license: Apache-2.0
platforms: [windows, linux, macos]
origin: openai4s
metadata:
  hermes:
    tags: [openai4s, chai1]
    difficulty: advanced
    language: Python
    category: Structural Biology
prerequisites:
  r_packages: []
  python_packages: []
---

> 📦 本 skill 由 OpenAI4S (PKU-YuanGroup, MIT/Apache-2.0) 移植。
> 原仓库: https://github.com/PKU-YuanGroup/OpenAI4S


# Chai-1

Chai-1 is an all-atom diffusion co-folder in the same family as Boltz-2 and
AlphaFold3: a multi-entity FASTA in, mmCIF plus pTM/ipTM/pLDDT out, with
protein, RNA, DNA, and SMILES-ligand chains all first-class. It and `boltz`
cover the same surface; running both and keeping designs that pass either is a
common consensus filter, and Chai's Python entry point makes it the easier of
the two to embed in a loop. Code and weights are Apache-2.0 — commercial use
including drug discovery is explicitly permitted
(github.com/chaidiscovery/chai-lab).

## Running it

```python
from pathlib import Path
from chai_lab.chai1 import run_inference

Path("complex.fasta").write_text("""
>protein|name=target
MVTPEGNVSLVDESLLVGVTDEDRAVRS...
>protein|name=binder
AIQRTPKIQVYSRHPAENG...
>ligand|name=cofactor
CCCCCCCCCCCCCC(=O)O
""".strip())

candidates = run_inference(
    fasta_file=Path("complex.fasta"),
    output_dir=Path("out/"),
    num_trunk_recycles=3,
    num_diffn_timesteps=200,
    seed=42,
    device="cuda:0",
    use_esm_embeddings=True,
)
print([rd.aggregate_score.item() for rd in candidates.ranking_data])
```

The FASTA header is `>{entity_type}|name={id}` with `entity_type` ∈
{`protein`, `rna`, `dna`, `ligand`}; ligand records carry a SMILES string as
the sequence body, and modified residues are written inline as
`...AAK(SEP)AAG...`. From the shell the same job is `chai-lab fold
complex.fasta out/ --use-msa-server`. Without `--use-msa-server` (or
`use_msa_server=True` in Python) the model runs on ESM embeddings alone, which
is faster but typically a few ipTM points behind the MSA-backed run.

`output_dir` receives `pred.model_idx_{0..4}.cif` plus a matching
`scores.model_idx_{N}.npz` per sample with `aggregate_score`, `ptm`, `iptm`,
`per_chain_ptm`, and clash flags. Rank by `aggregate_score`; treat `iptm` >
0.5 as a soft pass for an interface. The function refuses a non-empty `output_dir`, so
clear or rotate it between calls.

## Unset `CHAI_DOWNLOADS_DIR` fails mid-run with PermissionError on a read-only image

Chai downloads ~5 GB on the first inference call (not at install time),
including its own traced ESM2-3B for the embedding path. If
`CHAI_DOWNLOADS_DIR` is unset, the default is inside `site-packages`: on a
read-only image that fails with a confusing `PermissionError` mid-run, and on
a writable one it silently re-downloads ~5 GB into the container on every cold
start. Export the variable to a persisted volume so the download happens once.

## No-MSA mode still loads a 3 B-parameter ESM — same VRAM, not less

`use_esm_embeddings=True` without an MSA still loads a 3-billion-parameter
language model into GPU memory alongside the trunk; it removes the MSA-server
round-trip, not the VRAM cost. If you OOM, drop `num_diffn_timesteps` or fold
fewer chains per call rather than expecting the no-MSA mode to fit a smaller
card.

## Errors worth recognizing

| You see | It means / do this |
|---|---|
| `PermissionError` under `site-packages/chai_lab/...` | `CHAI_DOWNLOADS_DIR` not set on a read-only image — export it to a writable path or the pre-populated mount. |
| `RuntimeError: CUDA out of memory` during ESM embedding | The traced ESM2-3B is loading alongside the trunk — use an 80 GB tier or split chains across calls. |

---

**Next:** filter survivors on confidence/clash metrics or feed them back to
`proteinmpnn` for the next design round.
