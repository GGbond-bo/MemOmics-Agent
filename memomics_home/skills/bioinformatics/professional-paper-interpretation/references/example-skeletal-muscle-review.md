# 实战案例：The hallmarks of skeletal muscle health

## 任务
用户要求从专业编辑角度解读 Nature Metabolism 2026 综述文章。

## 工具链
1. `skill_view(name='paper-summary')` → 获取 run.py 脚本
2. `skill_view(name='nature-reader')` → 路由协议（pdf-text 格式检测）
3. `terminal` → 运行 `python scripts/run.py extract --tier1 --pdf <path> --out <dir>`
4. `read_file` → 读取 fulltext.txt（185909 chars, 3610 lines）+ metadata.json

## 提取结果
- 文本：185909 chars
- 图片：1 张（fig_09_09.png）
- 图表说明：5 个（Figure 1-5 captions）

## 解读输出结构
1. **基本信息表** — 28页综述，16位作者，Marco Sandri 通讯
2. **核心问题** — 领域缺统一框架 → 引用 Hallmarks of Cancer/Aging → 提出 7 hallmark
3. **研究思路 Mermaid** — 7 个互联 hallmark 围绕 Muscle Mass 中心枢纽
4. **核心贡献逐项拆解** — 代谢/蛋白质稳态/基因组/兴奋性/结构/再生/串扰
5. **结构化写作逻辑** — 总-分-总 + 每个 hallmark 按固定模板展开
6. **与用户研究关联** — 骨骼肌衰老 scRNA-seq 的 6 个具体应用方向

## 关键经验
- 综述文章用"概念框架图"而非"实验流程图"
- 用户说"重新解读/不满意"时必须换模板，不能重跑同一逻辑
- 28页综述需要精选关键段落（每 hallmark 的 Measurability/Disease/Modifiability 三维度），不需要逐字读完
- 图片提取可能只拿到 1 张（PDF 矢量图嵌入），但 captions 有 5 个可做文字解读
