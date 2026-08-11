# webUI 背景主题设计规划（v1）

> 状态：规划待确认 · 2026-08-11
> 目标：在现有 3 主题（浅白/深色/蓝色）基础上，增加护眼、羊皮纸、二次元、专业科研等背景主题

## 1. 现状

- 主题机制已存在：`data-theme` 属性 + CSS 变量（`--bg/--panel/--border/--text/--primary/...`），3 套定义（`light/dark/blue`，index.html L10-53）
- 切换函数 `setTheme(theme)`（L3052）：设属性 + 高亮按钮 + `localStorage['memomics-theme']` 持久化
- 设置区按钮硬编码 3 个（L738-741）
- 页面背景 = `body { background: var(--bg) }`，**纯色**，无纹理/渐变/图片

## 2. 核心设计决策：背景 = 新主题（扩展 data-theme），不做主题/背景正交

| 方案 | 说明 | 取舍 |
|---|---|---|
| **A（推荐）** 背景作为新主题 | 新增 `data-theme` 值，每主题 = 变量集 + 背景层纹理 | 改动最小、复用现有机制、切换逻辑零改动；"配色+纹理"打包，符合直觉 |
| B 主题/背景正交 | `data-theme`（配色）× `data-bg`（纹理）两维独立组合 | 灵活但复杂度翻倍（按钮矩阵、持久化双键、组合测试）——本期不做 |

## 3. 背景主题清单（6 个新增 + 3 个现有）

| 主题 | data-theme | 配色核心 | 背景层（body::before，纯 CSS，零图片） |
|---|---|---|---|
| 护眼 | `eye` | 柔绿米白 `#e8f3e8` 底 / 深绿灰文字，低对比 | 极淡径向渐变（无纹理，避免干扰阅读） |
| 羊皮纸 | `parchment` | 米黄泛旧 `#f2e3c6` 底 / 棕褐文字 | 噪点 + 边缘暗角（CSS repeating-radial-gradient 模拟纸纹） |
| 二次元 | `anime` | 浅粉→浅紫渐变底 / 深紫文字 | 对角渐变 + 顶部柔光（纯 CSS；如用户提供本地图，assets/ 放图走 `--bg-image` 变量兜底） |
| 科研专业 | `sci` | 石墨深底 `#0f172a` / 冷白文字 | **网格点阵**（repeating-linear-gradient 细线，类代码编辑器） |
| 暖阳 | `sunset` | 暖橙→米色渐变 / 深棕文字 | 水平渐变 + 底部暖光 |
| 暮色 | `dusk` | 深蓝紫 `#1e1b3a` / 淡紫文字 | 星点（radial-gradient 多点）+ 顶部微光 |

现有 3 个（浅白/深色/蓝色）保留不动。

## 4. 实现结构

```
:root → 默认（浅白）
[data-theme="dark"|"blue"|"eye"|"parchment"|"anime"|"sci"|"sunset"|"dusk"] {
  --bg / --panel / --border / --text / --text-light / --primary / --primary-light /
  --accent / --success / --warning / --danger / --tool-bg / --code-bg / --code-fg
}
body::before {   /* 背景纹理层，每主题用 --bg-image / --bg-overlay 变量 */
  content:""; position:fixed; inset:0; z-index:-1; pointer-events:none;
  background: var(--bg-image, none);
}
```

- **JS 配置数组**（新增 `THEME_PRESETS`）：`[{id:'eye', label:'🌿 护眼', desc:'柔绿低对比'}, ...]`
- 设置区按钮**动态渲染**（从 THEME_PRESETS 生成色卡按钮，替换 3 个硬编码按钮）——以后加主题只改数组
- `setTheme` 逻辑复用（已兼容任意 data-theme 值）；`cycleTheme` 的 order 数组改为从 THEME_PRESETS 推导
- 主题按钮加**色卡预览**（每按钮顶部小块背景色），点选即切

## 5. 兼容性检查项（实施时）

1. **硬编码色值适配**：147 处硬编码多为语义色（成功/警告/危险）可通用；抽查 `#e3f2fd`（primary-light 相关）、`#1a1a2e`（dark 主题专用）等是否跟随变量——不跟随的组件在新主题下可能突兀，逐项评估是否改 var()
2. **气泡/代码块**：聊天气泡、代码高亮用 `--code-bg/--code-fg` 变量的不用动；检查 Mermaid 图表背景
3. **文字对比度**：羊皮纸/二次元浅底配深字；sci 深底配冷白字——按 WCAG 4.5:1 粗查
4. **localStorage 兼容**：已存 `memomics-theme=dark` 的老用户不受影响；未知值（如手动改坏）回退 light——`setTheme` 增加白名单校验
5. **启动恢复**：现有启动时读 localStorage 设 data-theme 的逻辑（搜 `memomics-theme` 读取处）自动覆盖新主题

## 6. 实施范围（确认后执行）

| # | 改动 | 文件 |
|---|---|---|
| 1 | 新增 6 套 `[data-theme=...]` 变量集 + `body::before` 背景层 | `webui/index.html` |
| 2 | `THEME_PRESETS` 配置数组 + 设置区按钮动态渲染 + 色卡预览 | 同上 |
| 3 | `setTheme` 白名单校验 + `cycleTheme` 动态 order | 同上 |
| 4 | 硬编码色值抽查适配（预计 5-10 处改 var()） | 同上 |
| 5 | 测试：切换/持久化/刷新恢复/各主题对比度抽查（TestClient + 前端逻辑单测） | `webui/tests/` |

## 7. 待确认问题

1. 二次元背景：**纯 CSS 渐变版**（零依赖、离线可用）够不够？还是要**本地图片**（需你提供图源，放 `webui/assets/bg-anime.jpg`，代码走 `--bg-image` 变量 + 纯 CSS 兜底）？
2. "其他常用专业背景"还想要哪些？（当前给了科研网格/暖阳/暮色 3 个，可增删）
3. 背景是否要影响**聊天气泡底色**（现在气泡用 --panel 跟随主题）？还是只动页面大背景、气泡保持白色？

## 8. 二次元主题升级（v2 增补，2026-08-11）

用户要求：**真实二次元图片 + 动态设计 + 思考状态联动**。

### 8.1 背景层三级结构（仅 anime 主题）

```
body::before  静态背景图层   --bg-image: url(assets/bg-anime.jpg)（用户提供图源）
body::after   动态粒子层     canvas 或 CSS 动画（樱花/星光漂浮，见 8.2）
#anime-overlay 思考联动层    .thinking 时叠加光晕/呼吸（见 8.3）
```

### 8.2 动态设计（CSS + Canvas 双档）

| 档位 | 实现 | 效果 | CPU |
|---|---|---|---|
| 轻量（默认） | CSS keyframes：背景图缓慢缩放（Ken Burns 20s 周期）+ 渐变光晕流动 | 背景"活着" | ~0% |
| 中量（可开关） | `<canvas>` 粒子层：樱花/星点 40-60 粒，随风漂浮、回绕 | 二次元氛围感 | ~2-5% |
| 思考加速 | agent thinking 时：粒子速度 ×2.5 + 光晕脉冲频率提升（见 8.3） | 感知"在思考" | 瞬时 |

- 粒子层**独立 canvas**（fixed, z-index 背景与内容之间，pointer-events:none），`requestAnimationFrame` + `document.hidden` 时暂停（省电）
- 设置区加"动态效果"开关（localStorage 持久化：`memomics-bg-anim`）

### 8.3 思考联动（.thinking 状态）

- **信号源**：ws 消息 `type:"thinking"` / `"reasoning"` / `"tool_start"`（已有事件流，前端 handleMessage 分支挂接）
- **表现**：agent 思考/工具执行期间 body 加 `.thinking` 类：
  - 背景图轻微放大（scale 1.03，慢呼吸 3s 周期）
  - 粒子速度提升（canvas 变量乘数 1→2.5）
  - 顶部光晕脉冲（opacity 0.4→0.8）
- **结束**：`complete` / `agent_reply` 时移除类 → 恢复常态
- 性能：全部 transform/opacity 动画（GPU 合成），无 layout 抖动

### 8.4 图源（待用户确认）

| 选项 | 说明 | 风险 |
|---|---|---|
| A 用户提供本地图 | 放 `webui/assets/bg-anime.jpg`（建议 1920×1080+，≤2MB） | 无 |
| B 我下载免费图 | 从 Unsplash/Pixabay 类源拉图 | 网络不稳、版权需商用许可核对 |
| C 先代码占位 | 樱花/星空 CSS+canvas 氛围版，图后补 | 不是"二次元的图" |

### 8.5 其他主题兼容

- 非 anime 主题：body::before 继续用纯色/纹理（CSS），无 canvas 粒子（省电）
- 切换主题时：销毁/重建粒子 canvas（避免多主题残留）
- 移动端：粒子数减半（matchMedia 检测）

## 9. 实施记录（2026-08-11 已落地）

- **9 主题**：light/dark/blue（原有）+ eye 护眼 / parchment 羊皮纸 / anime 二次元 / sci 科研 / sunset 暖阳 / dusk 暮色——全部 CSS 变量集
- **背景纹理层**：`body::before`（z-index:-1）——anime 粉紫渐变+Ken Burns 缩放、sci 网格点阵、parchment 纸纹噪点、dusk 星点、sunset/eye 渐变
- **二次元装饰**：`#anime-deco` 用 MemOmics 企鹅吉祥物（`/assets/penguin.png`）半透明漂浮（6s 浮动动画），思考时加速（2.4s）；后续换真二次元图只改这一处
- **粒子层**：`#bg-particles` canvas（46 粒粉/紫光点，移动端 22 粒），`document.hidden` 暂停省电，开关 `memomics-bg-anim`（设置区"动态效果"复选框）
- **思考联动**：ws `thinking`/`tool_start`/`agent_running` → `body.thinking`（背景呼吸光晕 + 粒子 ×2.5 + 角标"💭 思考中…"）；`complete`/`cancelled`/`error` → 恢复；`_thinkCount` 引用计数防多信号抖动
- **设置区**：`THEME_PRESETS` 数组动态渲染 9 色卡按钮（flex-wrap）+ 动态效果开关；`setTheme` 白名单校验（未知值回退 light）；`cycleTheme` 按数组循环
- 校验：esprima 整块 JS 语法 OK；test_theme_backgrounds.py 9 用例（主题/元素/资源/JS/白名单）；全量 254 passed
