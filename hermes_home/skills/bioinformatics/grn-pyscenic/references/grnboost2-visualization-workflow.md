# GRNBoost2-Only 综合可视化工作流

> **创建日期**: 2026-07-09  
> **来源**: 人类骨骼肌衰老 SMF 亚群 SCENIC 分析，双路线（去神经路线A + 应激路线B）  
> **问题**: cisTarget 因基因名不匹配失败（regulons.csv 每个基因被拆成单个字符，AUCell 全 0），但 GRNBoost2 输出正常  
> **解决方案**: 用 GRNBoost2 adjacencies 直接计算 TF 活性，生成 7 种以上可视化图

## 触发场景

- cisTarget 失败（`AssertionError: Signatures dataframe is empty!` 或 regulons 被拆成单个字符）
- AUCell 矩阵全为 0.0（regulons 无效）
- 但 GRNBoost2 的 adjacencies 文件正常（有 TF、target、importance 列）
- 需要 Zone 级别和细胞级别的 TF 活性对比

## 数据准备

```python
# 从 GRNBoost2 adjacencies 计算 TF 活性
# 方法：对每个 TF，取 importance 最高的 N 个靶基因，计算其在每个细胞中的均值表达
def compute_tf_activity_from_adjacencies(adjacencies_path, cell_tf_activity_path, n_top=50, min_targets=5):
    """
    从 GRNBoost2 adjacencies 计算细胞级 TF 活性评分
    
    Parameters:
    -----------
    adjacencies_path : str
        GRNBoost2 输出的 adjacencies.csv（列: TF, target, importance）
    ex_matrix_path : str
        表达矩阵 CSV（cells × genes），需与 adjacencies 的基因名一致
    n_top : int
        每个 TF 取 top N 个靶基因计算均值（默认 50）
    min_targets : int
        TF 至少需要 min_targets 个有效靶基因才计算活性（默认 5）
    
    Returns:
    --------
    tf_activity : pd.DataFrame
        cells × TFs 的活性矩阵
    zone_tf_activity : pd.DataFrame
        zones × TFs 的均值活性矩阵
    """
    ...
```

## 7 种必出图

### 图1: Zone × TF 活性热图 (`tf_zone_heatmap.png`)
- 行 = TF，列 = Zone
- 颜色 = 活性值
- 关键 TF（RUNX1、MAF、MYOD1、FOS 等）标注 ★
- 使用 `sns.heatmap`

### 图2: 关键 TF 箱线图 (`key_tf_boxplot.png`)
- 取方差最大的 6-8 个 TF
- 按 Zone 分组做箱线图
- 每个 Zone 用不同颜色
- 使用 `ax.boxplot` + `ax.set_xticklabels`

### 图3: TF 调控网络图 (`regulon_network.png`)
- 从 adjacencies 取 TF-靶基因关系
- 筛选关键 TF 相关的边（top 200）
- 布局：`nx.spring_layout(k=1.5, iterations=100)`
- TF 节点红色（大），靶基因蓝色（小）
- 关键 TF 标 ★ 并加黄色高亮框
- 使用 `networkx` + `matplotlib`

### 图4: Z-score 归一化热图 (`zscore_heatmap.png`)
- 按 TF 做 Z-score 归一化
- 使用 `sns.diverging_palette(250, 15)` 配色
- 看相对活性高低（不是绝对值）

### 图5: 核心 TF 对比图 (`core_tf_comparison.png`)
- 小提琴图：每个 Zone 的 RUNX1/MAF/MYOD1 活性分布
- 标注均值
- 使用 `sns.violinplot(inner='quartile', cut=0)`

### 图6: Zone Top10 TF 排序图 (`zone_top_tfs.png`)
- 每个 Zone 独立展示 Top10 TF
- 水平条形图，按活性值排序
- 关键 TF 用红色，其他蓝色

### 图7: 双路线对比图（可选）
- 找两条路线共享的 TF
- 并排展示活性对比
- 中间用红色虚线分割

## 关键坑（已踩过的）

### 1. Zone 名大小写匹配
- 元数据中的 zone 名通常是**小写**：`zone1`, `zone2`, `NMJ`, `zone5`, `zone6`
- 代码中必须用 `print(meta['subcluster'].unique())` 先检查
- 颜色字典也必须用小写 key：`ZONE_COLORS = {'zone1': '#E74C3C', ...}`

### 2. cell_tf_activity.csv 的 zone 列
- 这个 CSV 的最后一列是 `zone`（字符串列）
- 读取时必须 `df = df.drop(columns=['zone'])` 否则 `var()` 会报错

### 3. matplotlib 版本兼容
- 新版 matplotlib 的 `boxplot()` 不支持 `labels=` 参数
- 改用 `ax.set_xticklabels(labels)` 在 boxplot 之后设置

### 4. 网络图节点数
- 如果筛选条件太严，网络图可能只有几个节点
- 至少保留 top 200 条边，确保节点 ≥ 30

### 5. 必须先用 skill 自带脚本
- **必须先调用 `generate_all_visualizations()`** 生成 `regulon_heatmap.png` + `regulon_network.png`
- 如果它失败了，才用本参考文件的自定义方法
- 绝不能不调用 skill 脚本直接写自定义代码

## 验证清单

| 检查项 | 标准 | 工具 |
|:------|:----|:-----|
| 每张图大小 | > 5KB | `os.path.getsize()` |
| 热图颜色 | 非单一色 | 肉眼检查 |
| 网络图节点 | ≥ 30 | `G.number_of_nodes()` |
| 网络图边数 | ≥ 30 | `G.number_of_edges()` |
| 总图数 | ≥ 6 张 | 文件计数 |
| 无空图 | 不报 matplotlib 错误 | 执行日志 |