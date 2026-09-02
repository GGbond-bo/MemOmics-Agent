#!/bin/bash
# ASCII-only credential check on fresh package extract
OUT=/tmp/cred_check.txt
> "$OUT"
echo "== model_config.json (first 300 bytes) ==" >> "$OUT"
head -c 300 ~/mm-heal/MemOmics/hermes_home/model_config.json 2>/dev/null >> "$OUT"
echo "" >> "$OUT"
echo "== real sk- key scan in fresh extract hermes_home ==" >> "$OUT"
grep -rl "sk-[A-Za-z0-9]\{20,\}" ~/mm-heal/MemOmics/hermes_home/ 2>/dev/null | head -3 >> "$OUT"
grep -rl "sk-[A-Za-z0-9]\{20,\}" ~/mm-heal/MemOmics/hermes_home/ 2>/dev/null | wc -l >> "$OUT"
echo "== provider_keys.json in fresh extract? ==" >> "$OUT"
ls ~/mm-heal/MemOmics/hermes_home/provider_keys.json 2>/dev/null || echo "not shipped" >> "$OUT"
echo "== config.yaml api_key line ==" >> "$OUT"
grep -E "^api_key" ~/mm-heal/MemOmics/hermes_home/config.yaml 2>/dev/null | head -1 >> "$OUT"
echo CRED_CHECK_DONE