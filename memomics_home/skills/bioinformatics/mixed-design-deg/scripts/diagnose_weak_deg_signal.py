# -*- coding: utf-8 -*-
"""
弱信号 DEG 诊断一键复跑  (skill: mixed-design-deg · SKILL.md §陷阱 3.5-3.8)

回答用户「这基因也太少了，方法是不是有问题？」—— 一次跑完四项诊断：
  ① 阳性对照自证      ② π1（Storey，量化"多少基因真变了"）
  ③ 检测下限反推      ④ 效应量分布
外加：⑤ 面板富集（同时打印【错误口径】与【匹配零假设】结果，让选择偏倚自证）
      ⑥ 细胞组成变化（需 cell-level meta）⑦ 各亚群 pseudobulk 输入细胞数

输入
  TABLES : {对比名: 表格路径}，列须含
           contrast, celltype, gene, logFC, CI.L, CI.R, AveExpr, t, P.Value, adj.P.Val
  META   : 可选，cell-level meta CSV，须含 samplename + 亚群列（默认 annotation_L3）

用法
  python diagnose_weak_deg_signal.py                # 改下面 CONFIG 后直接跑
  exec(open(r"...\\diagnose_weak_deg_signal.py", encoding="utf-8").read())   # 平台内

输出
  控制台报告 + WEAK_SIGNAL_REPORT.md（与脚本同目录的 results 目录）
"""
import os
import numpy as np
import pandas as pd
from scipy import stats

# ============================ CONFIG ============================
TABLES = {
    'Aging':    r'D:/肌肉锻炼/file/Aging.csv',
    'DM':       r'D:/肌肉锻炼/file/DM.csv',
    'Ex_Young': r'D:/肌肉锻炼/file/Ex_Young.csv',
    'Ex_Old':   r'D:/肌肉锻炼/file/Ex_Old.csv',
    'Ex_DM':    r'D:/肌肉锻炼/file/Ex_DM (1).csv',
}
META      = r'E:/骨骼肌锻炼/MF_L3_meta_new.csv'   # 无则设 None
META_SUB  = 'annotation_L3'                       # meta 里的亚群列名
OUT_MD    = r'E:/MemOmics-Agent/results/memomics-afd2d418/task2/results/WEAK_SIGNAL_REPORT.md'

# 阳性对照基因面板。⚠️ 只放「与你的活检时相匹配」的基因：
#    训练后静息活检 -> 别放急性 IEG（FOS/JUN/EGR1/NR4A），它们本就不该升高
PANEL = ['FOS', 'FOSB', 'JUN', 'JUNB', 'EGR1', 'ATF3', 'NR4A1', 'NR4A2', 'NR4A3', 'MYC',
         'PPARGC1A', 'PPARGC1B', 'ESRRB', 'ESRRG', 'TFAM', 'NRF1', 'CS', 'SDHA', 'CYCS', 'COX4I1',
         'SLC2A4', 'PDK4', 'HK2', 'PFKFB3', 'IRS1', 'IRS2', 'TBC1D4', 'PRKAA1', 'PRKAA2',
         'FBXO32', 'TRIM63', 'MSTN', 'ULK1', 'BECN1', 'MAP1LC3B', 'BNIP3', 'TFEB',
         'MYH7', 'MYH2', 'MYH1', 'MYBPH', 'TNNT1', 'TNNI1', 'ACTN3', 'TNNC1',
         'VEGFA', 'VEGFB', 'HIF1A', 'EPAS1', 'ANGPT1', 'NOS3',
         'HSPA1A', 'HSPA1B', 'HSPB1', 'DNAJB1', 'HSPA8',
         'MYOD1', 'MYOG', 'PAX7', 'MEF2C', 'MYF5',
         'IL6', 'IL15', 'SPARC', 'FNDC5']
# ================================================================

Z = 1.959964
CONTRASTS = list(TABLES)
report = []


def say(s=''):
    print(s)
    report.append(str(s))


def se_from_ci(d):
    return (d['CI.R'] - d['CI.L']) / (2 * Z)


# ---------------- 载入 ----------------
data = {}
say('## 0. 载入')
for k, v in TABLES.items():
    d = pd.read_csv(v)
    d['SE'] = se_from_ci(d)
    d['abs_t'] = d['logFC'].abs() / d['SE']
    data[k] = d
    say(f'- {k:10s} rows={len(d):8d}  subclusters={d["celltype"].nunique()}')

# ---------------- ① ② ③ ④ 总览 ----------------
say('\n## 1. 阳性对照 / π1 / 检测下限 / 效应量')
rows = []
for k in CONTRASTS:
    d = data[k]
    m = int(d['P.Value'].notna().sum())
    pi1 = 1 - (d['P.Value'].between(0.5, 1.0).sum() / (0.5 * m))       # Storey
    sig = d['adj.P.Val'] < 0.05
    tcut = d.loc[sig, 'abs_t'].min() if sig.any() else np.nan
    med_se = d['SE'].median()
    rows.append(dict(contrast=k, m=m,
                     pct_nom=round(100 * (d['P.Value'] < 0.05).mean(), 2),
                     n_fdr=int(sig.sum()),
                     pi1_pct=round(100 * pi1, 1),
                     med_abs_lfc=round(d['logFC'].abs().median(), 3),
                     pct_lfc_gt05=round(100 * (d['logFC'].abs() > 0.5).mean(), 1),
                     pct_lfc_gt1=round(100 * (d['logFC'].abs() > 1).mean(), 1),
                     med_SE=round(med_se, 3),
                     BH_t_cut=round(tcut, 2) if sig.any() else None,
                     min_detect_lfc=round(tcut * med_se, 2) if sig.any() else None))
ov = pd.DataFrame(rows)
say('\n```')
say(ov.to_string(index=False))
say('```')
say('\n> 判读：π1 = 「真变了的基因占比」；min_detect_lfc = 该设计能稳定检出的最小 |logFC|（FDR<0.05）。')
say('> 「基因少」若伴随 π1 高 + min_detect_lfc 大于中位 |logFC| ⇒ 效应量 vs 检测下限错配，**不是方法坏**。')

# 各亚群 π1
say('\n### 各亚群 π1 (%)')
r2 = []
for k in CONTRASTS:
    for ct, g in data[k].groupby('celltype'):
        m = int(g['P.Value'].notna().sum())
        r2.append(dict(celltype=ct, contrast=k,
                       pi1_pct=round(100 * (1 - g['P.Value'].between(0.5, 1.0).sum() / (0.5 * m)), 1)))
piv = (pd.DataFrame(r2).pivot(index='celltype', columns='contrast', values='pi1_pct')
       .reindex(columns=CONTRASTS))
say('\n```')
say(piv.to_string())
say('```')

# ---------------- ⑤ 面板富集：错误口径 vs 匹配零假设 ----------------
say('\n## 2. 面板富集 —— 两种口径对照（看清选择偏倚）')
r3 = []
for k in CONTRASTS:
    d = data[k]
    # 【错误】面板取亚群最小 P，全基因组用池化率
    panel_p = d[d['gene'].isin(PANEL)].groupby('gene')['P.Value'].min()
    pooled = (d['P.Value'] < 0.05).mean()
    hit = int((panel_p < 0.05).sum()); tot = len(panel_p)
    bad_fold = (hit / tot) / pooled if pooled > 0 else np.nan
    # 【正确】全基因组每基因也取亚群最小 P
    gmin = d.groupby('gene')['P.Value'].min()
    matched = (gmin < 0.05).mean()
    good_fold = (hit / tot) / matched if matched > 0 else np.nan
    odds, pval = stats.fisher_exact(
        [[hit, tot - hit],
         [int(round(matched * 10000)), 10000 - int(round(matched * 10000))]])
    _, pu = stats.mannwhitneyu(panel_p, gmin, alternative='less')
    r3.append(dict(contrast=k, panel=f'{hit}/{tot}',
                   panel_rate=round(100 * hit / tot, 1),
                   pooled_null=round(100 * pooled, 2),
                   matched_null=round(100 * matched, 2),
                   WRONG_fold=round(bad_fold, 2),
                   RIGHT_fold=round(good_fold, 2),
                   fisher_p_right=f'{pval:.2e}',
                   mannwhitney_p=f'{pu:.2e}'))
pan = pd.DataFrame(r3)
say('\n```')
say(pan.to_string(index=False))
say('```')
say('\n> ⚠️ 只有 `RIGHT_fold` + `fisher_p_right` 可引用。`WRONG_fold` 列是**展示选择偏倚**用的反例。')
say(f'> 机理：{len(piv)} 个亚群取最小 P，纯随机下 P(min)<0.05 的概率 = '
    f'{100 * (1 - 0.95 ** len(piv)):.0f}%，所以匹配零假设率本就该在这个量级。')
say('> ⛔ 不要拿面板富集当方法有效性的证据 —— 用 ① 阳性对照量级 + 具名基因/方向/效应量。')

# ---------------- ⑥ ⑦ meta 相关 ----------------
if META and os.path.exists(META):
    meta = pd.read_csv(META, usecols=['samplename', META_SUB])
    cnt = meta.groupby([META_SUB, 'samplename']).size().rename('n_cells').reset_index()

    say('\n## 3. 🔴 细胞组成变化（pseudobulk DEG 的结构性盲区）')
    cnt2 = cnt.assign(phase=np.where(cnt['samplename'].str.endswith('Post'), 'Post', 'Pre'))
    pv = cnt2.pivot_table(index=META_SUB, columns='phase', values='n_cells', aggfunc='mean')
    if {'Pre', 'Post'}.issubset(pv.columns):
        pv['Post/Pre'] = (pv['Post'] / pv['Pre']).round(3)
        say('\n```')
        say(pv.round(1).sort_values('Post/Pre').to_string())
        say('```')
        say('\n> 按亚群 pseudobulk DEG **看不见亚群之间的比例变化**。Post/Pre 明显偏离 1 的亚群，')
        say('> 其变化只能靠**细胞比例检验**（skill `celltype-proportion-comparison`）或 AUCell 打分捕捉。')
        say('> ⚠️ 须独立配对检验确认再定性（n 小、方差大时均值比可能是抽样噪声）。')

    say('\n## 4. 各亚群 pseudobulk 输入细胞数（≠ 功效代理量）')
    tab = cnt.groupby(META_SUB)['n_cells'].agg(['median', 'min', 'max'])
    tab['n_ge10'] = cnt.assign(x=cnt['n_cells'] >= 10).groupby(META_SUB)['x'].sum()
    tab['pct_cells'] = (cnt.groupby(META_SUB)['n_cells'].sum() / len(meta) * 100).round(2)
    say('\n```')
    say(tab.sort_values('median').to_string())
    say('```')
    say('\n> ⛔ 别把细胞数当功效代理量 —— 实测细胞最多的亚群往往不是命中最多的（效应量定位才是主导）。')

say('\n## 5. 附：面板基因逐条明细（方法是否在检正确生物学）')
det = []
for k in CONTRASTS:
    d = data[k]
    for g in PANEL:
        sub = d[d['gene'] == g]
        if not len(sub):
            continue
        r = sub.loc[sub['P.Value'].idxmin()]
        det.append(dict(gene=g, contrast=k, celltype=r['celltype'],
                        logFC=round(r['logFC'], 2), P=r['P.Value'],
                        FDR=round(r['adj.P.Val'], 4),
                        sig_fdr=bool(r['adj.P.Val'] < 0.05)))
det = pd.DataFrame(det)
say('\n命中 FDR<0.05 的面板基因（方法在检正确生物学的硬证据）：')
hitdf = det[det['sig_fdr']].sort_values('P')
say('\n```')
say(hitdf[['gene', 'contrast', 'celltype', 'logFC', 'P']].to_string(index=False)
    if len(hitdf) else '  （无）—— 检查活检时相与面板是否匹配')
say('```')

# ---------------- 落盘 ----------------
if OUT_MD:
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, 'w', encoding='utf-8') as f:
        f.write('# 弱信号 DEG 诊断报告\n\n')
        f.write('\n'.join(report))
    print(f'\n[OK] -> {OUT_MD}')