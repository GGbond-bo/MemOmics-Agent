# -*- coding: utf-8 -*-
"""极端评测 A/G：脚手架污染 + facts 质量审计 + 干净消息样本导出。"""
import sqlite3, re, json, hashlib
DB = r'E:\MemOmics-Agent\hermes_home\state.db'
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
rows = c.execute(
    "SELECT id, content FROM messages WHERE session_id='memomics-cd677556' "
    "AND role IN ('user','human') AND (active=1 OR compacted=1) ORDER BY id"
).fetchall()
c.close()

PREFIXES = ("[会话要求", "[相关历史记忆", "[会话锚点", "[系统唤醒", "📊 LoopX", "[System:", "[数据读取配方")
scaffold = 0
clean = []
for mid, content in rows:
    t = re.sub(r'\s+', ' ', str(content or '')).strip()
    if t.startswith(PREFIXES):
        scaffold += 1
    else:
        clean.append({'id': mid, 'text': t[:200]})
total = len(rows)
print(f"user rows: {total} | scaffold-injected: {scaffold} ({scaffold*100//total}%) | clean: {len(clean)}")

# 脚手架去重后的唯一条数
uniq_scaff = len(set(
    re.sub(r'\s+', ' ', str(r[1] or '')).strip()
    for r in rows if re.sub(r'\s+', ' ', str(r[1] or '')).strip().startswith(PREFIXES)
))
print(f"unique scaffold texts: {uniq_scaff} (injected {scaffold} times)")

# facts 质量审计
DB2 = r'E:\MemOmics-Agent\hermes_home\memory_store.db'
c2 = sqlite3.connect(f'file:{DB2}?mode=ro', uri=True)
facts = c2.execute("SELECT fact_id, content, category, tags, trust_score FROM facts").fetchall()
c2.close()
print(f"\nfacts total: {len(facts)}")
cats = {}
for f in facts:
    cats[f[2]] = cats.get(f[2], 0) + 1
print("category:", cats)
lens = [len(str(f[1])) for f in facts]
print(f"len: min={min(lens)} median={sorted(lens)[len(lens)//2]} max={max(lens)}")
hashes = {}
for f in facts:
    h = hashlib.md5(str(f[1]).encode('utf-8', 'ignore')).hexdigest()
    hashes[h] = hashes.get(h, 0) + 1
dups = sum(v - 1 for v in hashes.values())
print(f"exact-duplicate facts: {dups} ({dups*100//max(1,len(facts))}%)")
# 代码行占比（user_request 类里含 R 代码的）
codey = sum(1 for f in facts if re.search(r"<-\s*[A-Za-z]|\b(getPeakSet|addPeakMatrix|saveArchRProject|filterDoublets|readRDS|library\()\b", str(f[1])))
print(f"facts containing R-code snippets: {codey}")
tr = [f for f in facts if f[2] == 'user_request']
tr_codey = sum(1 for f in tr if re.search(r"<-\s*[A-Za-z]|\b(getPeakSet|addPeakMatrix|saveArchRProject|filterDoublets|readRDS)\b", str(f[1])))
print(f"user_request facts: {len(tr)}, of which code-like: {tr_codey} ({tr_codey*100//max(1,len(tr))}%)")

with open(r'E:\MemOmics-Agent\scripts\bench_clean_msgs.json', 'w', encoding='utf-8') as f:
    json.dump(clean, f, ensure_ascii=False, indent=1)
print(f"\nclean msgs saved: scripts/bench_clean_msgs.json ({len(clean)} msgs)")
