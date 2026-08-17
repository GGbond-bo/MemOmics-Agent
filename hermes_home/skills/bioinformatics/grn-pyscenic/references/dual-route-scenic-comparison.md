# 双路线 SCENIC 比较工作流（Dual-Route SCENIC Comparison）

> 2026-07-09 实战记录：人类骨骼肌 SMF 亚聚类，11,630 cells，GRNBoost2-Only 模式

## 背景

SMF 数据包含两条独立生物学过程：
- **路线A**（去神经化→再神经支配）：Zone1 → Zone2 → NMJ → Zone5/6
- **路线B**（应激→成熟发育）：Zone3 → Zone4 → Zone5

不能一次跑所有细胞的 SCENIC（两条路线会互相混淆），必须分开跑再比较。

## 数据准备

```python
# 路线A：去神经化路线
route_a = adata[adata.obs['subcluster'].isin(['Zone1','Zone2','NMJ','Zone5','Zone6'])].copy()
# route_a shape: ~8,900 cells × 51,227 genes

# 路线B：应激→成熟路线  
route_b = adata[adata.obs['subcluster'].isin(['Zone3','Zone4','Zone5'])].copy()
# route_b shape: ~6,974 cells × 51,227 genes

# 注意 Zone5 在两条路线中都出现——作为健康对照端点
```

## 关键参数

| 参数 | 路线A | 路线B |
|:----|:----:|:----:|
| 细胞数 | ~8,900 | ~6,974 |
| HVG 数 | 3,000 | 3,000 |
| GRNBoost2 方法 | arboreto | arboreto |
| 随机森林树数 | 1,000 | 1,000 |
| 种子 | 123 | 456 |
| TF 列表 | allTFs_hg38.txt (1,678 TF) | 同左 |
| 运行时间 | ~30 min | ~25 min |

## 结果对比

### 路线A 排名前 10 TF（按 Zone 间活性方差排序）

| 排名 | TF | 最高活性 Zone | 活性值 | 生物学意义 |
|:---:|:--|:-----------|:-----:|:----------|
| 1 | ATF3 | zone6 | 3.28 | 通用应激响应 |
| 2 | ARID5A | zone6 | 2.18 | 炎症/应激 |
| 3 | NR4A3 | zone6 | 2.53 | 核受体应激 |
| 4 | CREB5 | NMJ | 2.38 | cAMP 信号 |
| 5 | RUNX1 | zone5 | 3.66 | 去神经核心 TF |
| 6 | MYOD1 | zone1 | 2.15 | 去神经后再生尝试 |
| 7 | MAF | zone5 | 2.57 | 快肌身份维持；zone1 最低 |
| 8 | EGR1 | zone6 | 1.72 | 即刻早期基因 |
| 9 | FOSL1 | zone1 | 1.89 | AP-1 家族 |
| 10 | SIX4 | NMJ | 1.93 | NMJ 维持 |

### 路线B 排名前 10 TF

| 排名 | TF | 最高活性 Zone | 活性值 | 生物学意义 |
|:---:|:--|:-----------|:-----:|:----------|
| 1 | ATF3 | zone4 | 10.44 | 应激核心——路线B 更高 |
| 2 | ARID5A | zone4 | 6.15 | 炎症应激 |
| 3 | NR4A3 | zone4 | 5.89 | 核受体应激 |
| 4 | CREB5 | zone4 | 4.21 | cAMP 信号 |
| 5 | RUNX1 | zone3 | 3.86 | 去神经信号（轻度） |
| 6 | EGR1 | zone4 | 3.12 | 即刻早期基因 |
| 7 | JUNB | zone4 | 2.45 | AP-1 应激 |
| 8 | FOS | zone3 | 1.66 | AP-1 机械应力——路线B 特有 |
| 9 | ATF7 | zone4 | 1.89 | 应激响应 |
| 10 | FOSL2 | zone4 | 2.01 | AP-1 家族 |

### 核心发现

| TF | 路线A | 路线B | 结论 |
|:--|:----:|:----:|:----|
| **ATF3** | #1, 3.28 | #1, 10.44 | **通用应激 TF**，路线B 活性高 3×（应激更剧烈） |
| **RUNX1** | #5, 3.66 | #5, 3.86 | **两条路线都活跃**——但靶基因可能不同 |
| **FOS (AP-1)** | 不显著 | #8, 1.66 | **路线B 特有**——机械应力+炎症响应 |
| **MYOD1** | 路线A zone1 显著 | 无 | **路线A 特有**——去神经后再生尝试 |
| **MAF** | 路线A zone5 高/zone1 低 | 无 | **路线A 特有**——去神经时被抑制的快肌 TF |
| **NR4A3** | #3, 2.53 | #3, 5.89 | 两条路线都活跃，路线B 更高 |

## 生成的关键图

| 图 | 路线A | 路线B | 包含内容 |
|:--|:----:|:----:|:--------|
| TF 活性热图 | ✅ | ✅ | Zone×TF（前 20 个可变 TF） |
| 关键 TF 箱线图 | ✅ | ✅ | RUNX1/MAF/MYOD1/FOS/ATF3 的 Zone 分布 |
| TF-靶基因网络 | 可选 | 可选 | 仅 top 5 TF |

## 注意点

1. **GRNBoost2-Only 模式**：因 cisTarget 数据库基因名不匹配（ENSEMBL IDs vs HGNC），跳过 cisTarget 验证。直接使用 GRNBoost2 的 adjacencies 计算 TF 活性（取 top 50 靶基因的均值表达）。
2. **Zone5 出现在两条路线中**：这是故意设计的健康对照端点。两条路线的 Zone5 细胞是同一批细胞，但 TF 活性略有差异（因为路线A/B 的 HVG 选择不同）。
3. **ATF3 的极高活性（路线B zone4=10.44）**：不是错误。Zone4 的 ANKRD1 高表达+机械应力响应程序使转录组异常活跃，scTour 也显示 Zone4 成熟度最高。
4. **FOS 仅在路线B 出现**：这是路线B 的核心特征——机械应力通过 AP-1 通路驱动成熟程序。路线A 的去神经化过程不涉及 FOS 激活。