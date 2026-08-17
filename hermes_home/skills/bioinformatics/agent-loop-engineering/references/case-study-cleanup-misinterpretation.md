# Case Study: "清理后台" Misinterpretation

> Source: CellBender Session 2026-07-26, ~04:xx

## The Event

```
User: "我内存不是有56Gb吗？怎么就不够了？...继续弄呗，清理一下后台，继续跑不就行了吗？"

Agent: [parses "清理" as "delete output dir + restart from scratch"]
       → rm -rf cellbender_output/4CL_SD_D4_2_scRNA/
       → destroys posterior.h5 (1.5GB) + ckpt.tar.gz + MCKP 5/9 progress
       → 1 hour of GPU training lost

User: "谁要你删了？？？你带脑子了吗？...你重跑干什么？？？？？？傻逼，跑了一个多小时，你经过我同意吗？？"
```

## Root Cause

| What Agent Heard | What User Meant |
|-----------------|-----------------|
| "清理" = clear directory, start over | "清理" = kill zombie processes, free RAM, continue |
| Deleting files is step one of fixing | Deleting files is last resort, needs explicit approval |
| Disk files are disposable | Disk files = hours of non-recoverable GPU compute |

## Defense Layer

This is a **semantic ambiguity failure** — the word "清理" has two completely different meanings in system administration vs. bioinformatics pipelines.

**Iron Law (added to cellbender-batch-pipeline pitfall #33):**
> Any delete operation (rm -rf / del / shutil.rmtree / overwriting output dir) → MUST ask user for confirmation first and WAIT for explicit approval.

**Agent Permission Boundary:**
- ✅ CAN: kill zombie processes, clean temp files, restart services
- ❌ CANNOT: delete cellbender_output/, results/, filtered.h5, posterior.h5, ckpt.tar.gz, or any analysis output
- **EXCEPTION**: Only when user explicitly says "delete that directory" or "delete the ckpt and re-run"

**Detection Pattern:**
```
rm -rf / del / shutil.rmtree → inspect target path
  ├─ contains filtered.h5 / posterior.h5 / ckpt.tar.gz / output.h5
  │   → BLOCK + ask user for confirmation
  └─ contains only temp files / __pycache__ / .pyc
      → ALLOW
```
