# 纯 ATAC 跨物种 CRE 保守性专利独权模板

## 与常规生物信息学专利的区别

常规专利通常依赖多组学整合（scRNA+ATAC+Hi-C），但纯 ATAC 方法
有其独特优势:
1. 数据获取成本低（仅需 ATAC-seq）
2. A25 防御更强（物理测量锚点更直接）
3. B 类 CRE 检出是纯 ATAC 独有的核心创新点
4. 从权可以为 RNA/Hi-C 留口子但主方案不依赖

## 纯 ATAC 独权公式

```
独立权利要求 = 
  [ATAC-seq fragment 矩阵输入] 
  + [liftOver 坐标映射 + peak calling] 
  + [三层递进：序列→可及性→TF结合] 
  + [进化锚点校准权重] 
  + [B 类 CRE 检出] 
  + [A/B/C/D 分类输出]
```

## 五锚点 A25 防御

详见 cross-species-atac-conservation/references/patent-a25-defense.md

## 对比现有技术声明模板

"现有技术（phastCons/GERP/HAL）仅能评估序列保守性，
无法区分'序列保守但 TF 结合模式分歧'的 B 类 CRE。
本方法首次通过整合三层证据——
序列保守性、染色质可及性保守性和 TF 结合动态保守性——
实现了对 B 类 CRE 的系统性检出。
B 类 CRE 的生物学意义在于:
此类元件在序列和可及性层面高度保守，
但在 TF 结合模式上产生物种间分歧，
是造成'动物模型分子机制无法外推到人'的核心分子基础之一。"
