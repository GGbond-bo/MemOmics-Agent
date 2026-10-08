# MemOmics Verify Pattern — Ad-hoc Framework Verification

> Pattern established 2026-07-26 during loop-engineering session.

## Purpose

After any framework-level code change (new tool, new iron law, new module), write a **standalone verification script** to `%TEMP%/memomics-verify-<module>.py` and execute it. The script must be independent — no shared state with the session, no dependency on the current LLM context.

## Template

```python
"""Ad-hoc verification: MemOmics <module>."""
import sys, os
sys.path.insert(0, r"E:\MemOmics-Agent\memomics")

from bio_tools.<module> import <imports>

passed = 0
total = <N>

# 1. First check
assert ...
passed += 1; print(f"[{passed}/{total}] <description>")

# ... more checks ...

print(f"\nALL {passed}/{total} PASSED")
```

## Requirements

1. File location: `%TEMP%/memomics-verify-<module>.py`
2. Exit code: must be 0 only if ALL checks pass
3. Output format: `[N/M] description` per check, final `ALL N/N PASSED`
4. Clean up: delete the temp file after execution
5. Must test: import, edge cases, state persistence, error paths

## Usage Example

```bash
# Write to temp
cat > %TEMP%/memomics-verify-guardian.py << 'PYEOF'
... (verification script)
PYEOF

# Execute
python %TEMP%/memomics-verify-guardian.py

# Expected: ALL 8/8 PASSED

# Clean up
del %TEMP%/memomics-verify-guardian.py
```

## Verified Modules

| Module | Script | Checks | Date | Result |
|--------|--------|--------|------|--------|
| guardian | `memomics-verify-guardian.py` | 8/8 | 2026-07-26 | PASS |
