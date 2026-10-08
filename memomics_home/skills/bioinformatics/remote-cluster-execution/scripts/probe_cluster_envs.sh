#!/usr/bin/env bash
# 远端集群环境探查（只读，登录节点可跑）
# 用法:  bash probe_cluster_envs.sh <conda_root> [PKG1 PKG2 ...]
# 例:    bash probe_cluster_envs.sh /hwfssz3/PS_JLU/zhangxiao6/software/miniconda3
#
# 一次跑完四件事：① env 列表+类型+版本 ② 逐 R env 关键包 ③ 逐 Python env 关键包 ④ activate 可用性
# 设计要点（见 SKILL.md 铁规 0）：环境名不可信 —— 只以 find.package / find_spec 的实测结果为准。

set -u
M="${1:?usage: probe_cluster_envs.sh <conda_root> [pkgs...]}"
shift || true

RPKGS=("$@")
[ ${#RPKGS[@]} -eq 0 ] && RPKGS=(Seurat ArchR CellChat monocle3 Signac ComplexHeatmap hdWGCNA harmony DESeq2 clusterProfiler BSgenome.Hsapiens.UCSC.hg38 sctransform)
PPKGS=(scanpy anndata squidpy harmonypy scvi celltypist pyscenic scvelo torch decoupler cellrank)

echo "########## 0. conda_root 可访问性 ##########"
ls -ld "$M" 2>&1

echo
echo "########## 1. env 列表 + 类型 + 版本 ##########"
for d in "$M"/envs/*/; do
  [ -d "$d" ] || continue
  e=$(basename "$d")
  if   [ -x "$d/bin/Rscript" ]; then printf "R  %-18s " "$e"; "$d/bin/Rscript" --version 2>&1 | head -1
  elif [ -x "$d/bin/python"  ]; then printf "PY %-18s " "$e"; "$d/bin/python"  --version 2>&1
  else  printf "?? %-18s (无 Rscript/python —— 可能是纯工具目录)\n" "$e"
  fi
done

echo
echo "########## 2. 逐 R env：libPaths + 关键包 ##########"
for d in "$M"/envs/*/; do
  [ -x "$d/bin/Rscript" ] || continue
  e=$(basename "$d")
  echo "--- $e ---"
  "$d/bin/Rscript" -e '
    args <- commandArgs(TRUE)
    cat("R:", R.version.string, "| n_pkgs:", length(rownames(installed.packages())), "\n")
    cat("libPaths:\n"); print(.libPaths())
    for (p in args) cat(sprintf("%-30s %s\n", p,
        ifelse(requireNamespace(p, quietly=TRUE), as.character(packageVersion(p)), "NOT_INSTALLED")))
  ' "${RPKGS[@]}" 2>&1
done

echo
echo "########## 3. 逐 Python env：关键包 ##########"
for d in "$M"/envs/*/; do
  [ -x "$d/bin/python" ] || continue
  e=$(basename "$d")
  echo "--- $e ---"
  "$d/bin/python" -c "
import importlib.util as u, sys
print('python', sys.version.split()[0])
for m in '''${PPKGS[*]}'''.split():
    s = u.find_spec(m)
    if not s:
        print('%-14s NO' % m); continue
    try:
        print('%-14s %s' % (m, getattr(__import__(m), '__version__', '?')))
    except Exception as ex:
        print('%-14s import-error (%s)' % (m, type(ex).__name__))
" 2>&1
done

echo
echo "########## 4. conda activate 可用性（只读测试，不写目录）##########"
if [ -f "$M/bin/activate" ]; then
  ( source "$M/bin/activate" 2>&1 && echo "activate OK -> $(command -v python)" ) 2>&1
else
  echo "无 bin/activate（非 conda 目录？）"
fi

echo
echo "########## 5. 提示 ##########"
cat <<'TIP'
判断口径：
  * NOT_INSTALLED / NO  = 该环境真的没有这个包 —— 别按 env 目录名假设它有
  * 同时看 libPaths / sys.path：包可能装在 env 之外的共享库
  * 别人的目录（属主非本人）= 只读可用，装不了包
  * 作业脚本必须 source activate 或 export PATH，系统级 Rscript/python3 常不在 PATH
TIP