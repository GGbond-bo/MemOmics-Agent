# 脚本赋渐变填充：Error 1200 Internal error（实测记录）

## 现象（2026-10-03，本机 Illustrator，Windows）

```jsx
var g = doc.gradients.add();
g.type = GradientType.LINEAR;
g.gradientStops[0].color = c1;   // 不报错
g.gradientStops[1].color = c2;   // 不报错
var grect = ly.pathItems.rectangle(150, 420, 150, 70);
grect.filled = true;
grect.fillColor = g;             // ← Error 1200: Internal error（行号指向这一行）
```

VBS 侧完整报错：

```
run_jsx.vbs(8, 1) Adobe Illustrator: Error 1200: Internal error
Line: 67
->      grect.filled = true; grect.fillColor = g; grect.stroked = false;
```

## 已试过的两路（都失败）

| 路线 | 结果 |
|---|---|
| 新建渐变 `doc.gradients.add()` 后赋给 `fillColor` | `assign_fail: Internal error` |
| 改用文档自带默认渐变 `doc.gradients[0]` 赋给 `fillColor` | `assign_fail: Internal error` |

→ 失败发生在**赋值动作**上，不在渐变创建/stop 设色上（前者不抛错、对象也建出来了——回传串里 `gradients=6`）。

## 判定

这是**脚本 API 层限制**（该版本的渐变色板对象不能经 ExtendScript 直接赋给 pathItem 填充），**不是 COM 通道问题**——同一次脚本里矩形/椭圆/多边形/贝塞尔/文字/分组/删画板/导出/存盘全部成功。

## 替代路线（按推荐顺序）

1. **让用户手填一次**：把形状画好、图层分好，用户手动点渐变；脚本后续只改尺寸/位置/文字。交付里如实写明"渐变需手动填"。
2. **从 SVG 绕**：在 SVG 里用 `<linearGradient>` 定义渐变，`doc.importFile(new File(x.svg))` 或 `placedItems` 置入 —— 进入 Illustrator 后是可用对象，再 `expandStyle`/嵌入。
3. **叠色近似**：两个同形状、不同纯色、不同 `opacity` 的对象叠放，视觉上近似线性渐变（脚本可控，无需渐变 API）。
4. **让用户先手动建一个渐变样本**，脚本只改 `gradientStops[i].color` 后**再试一次赋值**（有的版本手动建过的渐变可以被脚本赋值）——成功与否必须实测回传，不要凭猜。

## 写入脚本的姿势

无论走哪条路，**渐变段必须包 `try/catch` 并把结果记进回传串**：

```jsx
out.push("gradient_ok=" + gradOk + " (" + gradMsg + ")");
```

这样渐变失败不会让整条链（导出/存盘/关闭）中断，也顺手留下"哪一步不行"的可复核证据。

> ⚠️ 换一台机器/换 Illustrator 版本时先重跑一次探针，不要沿用"渐变一定不行"的结论——这条是**版本相关**的观测，不是永久事实。