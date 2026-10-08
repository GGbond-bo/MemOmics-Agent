# 坑 0：rail_review(post) 对「纯表格统计」也要求图片（2026-10-05 实测）

> 本文件是 SKILL.md 的补充（SKILL.md 已达 100K 字符上限，无法再追加正文）。

## 现象
脚本只做「读表 → 计数 → 写 xlsx」（完全无绘图），`rail_review(phase="post")` 返回：
```json
{"passed": false, "issues": ["未生成任何图片 — 每步至少 1 张图，必须重新执行"], "figure_count": 0}
```

## 根因
图片门禁与任务类型**无关** —— 只要走 post 审查，`figure_count=0` 就不通过。
同轮常并发出现 `"No result files found in output directory"`，这条只是 **warning，不阻断**（别把它当主因去修）。

## 解法（约 1 分钟，不要去争辩"这任务不需要图"）
1. 给汇总结果补一张**结果可视化**：
   - 计数/频次矩阵 → 热图（行=基因/条目，列=分组，**格内标数字**；
     `np.ma.masked_where(M == 0, M)` 把 0 遮成白/浅灰，避免与低值混淆）
   - 单组计数 → 条形图
2. 复跑 post 审查时把 `output_dir` 指向**已含图片的 figures 目录**
   （`figure_count` 统计的是该目录内全部图片，不要求本轮新生成）。
3. 通过后再 `skill_evolution(action="record_run")`。

## 配套坑：matplotlib 中文 = 方框
默认 DejaVu Sans 无 CJK 字形。轴标签里混中文会刷：
```
UserWarning: Glyph 32769 (\N{CJK UNIFIED IDEOGRAPH-8001}) missing from font(s) DejaVu Sans
```
图上显示为**空方框**（OCR/视觉检查能看出来）。判据：**重跑后无 glyph 警告 = 合格**。
→ 图内标签一律**纯英文**；中文解释放图注/表注/正文。这也是本用户的明确要求
（「图中说明文字 = 英文」）。

## 反面案例（本次）
第一版热图 x 轴写了 `"Ex_Old\n(老年运动)"` → 7 个 glyph 警告；
改成 `["Aging", "Ex_Old", "Ex_DM", "DM", "Ex_Young"]` 后重跑零警告，复审通过。