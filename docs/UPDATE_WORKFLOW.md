# MemOmics-Agent 更新/发布工作流（持久记录，新会话必读）

> 本文档 + memomics_home/AGENTS.md 为「跨会话记忆」：任何会话接手「更新/打包/发布」任务时，先读本文。
> 最后更新：2026-10-08（hermes→memomics 改名迁移配套）

## 1. 更新什么、更新到哪里

| 项 | 规则 |
|---|---|
| 默认只更新 | MemOmics-update.zip（老用户一键更新/解压覆盖代码，保留 memomics_home/results/.venv） |
| 全量包 | MemOmics-Windows.zip / Linux.tar.gz / macOS-arm64 / macOS-x86_64 / Cluster.tar.gz —— 仅新装用户需要；一般不必每次重打，但同一天发布时建议全打保持一致 |
| 更新到哪里 | GitHub release：https://github.com/GGbond-bo/MemOmics-Agent/releases/tag/v<当天日期> |
| 版本号 | 必须=真实当天日期（如 v2026-08-31）；禁止未来日期、禁止旧 tag 覆盖（WebUI 按 tag 字符串比对） |
| 老名字迁移 | 安装里还有 `hermes_home` 时，更新/解压覆盖后**首次启动自动检测并迁移**到 `memomics_home`（只搬不删；双存在＝旧目录缺失项搬入新目录、重名保留新版；旧目录退休为 `hermes_home.migrated_<时间戳>`；config.yaml 内路径同步迁移）。**首次安装检测不到旧目录，不做任何替换**。一键更新器在覆盖前也会先跑同一检测迁移。 |
| 本地 VERSION | 打包时写 v<当天>；打完恢复 vdev-<当天> |

## 2.0 快速流程（默认：只更新 update 包）

```bash
# ① 版本日期 = 真实当天（例：2026-08-31）
# 编辑 VERSION 写入 v2026-08-31

# ② 只重打 update 所需包（本机会顺带生成 Windows.zip，但不要上传它）
powershell -ExecutionPolicy Bypass -File E:\release\_rebuild_v4.ps1 -Win

# ③ 只上传 update 包（不要上传其它 5 个平台包）
gh release upload v2026-08-31 E:/release/MemOmics-update.zip \
   --repo GGbond-bo/MemOmics-Agent --clobber

# ④ 更新说明（同步 SHA）
gh release edit v2026-08-31 --repo GGbond-bo/MemOmics-Agent \
   --notes-file E:/release/RELEASE_NOTES.md

# ⑤ 恢复仓库 VERSION = vdev-2026-08-31
```

> ⚠️ **用户偏好（2026-08-31）**：默认**只上传 MemOmics-update.zip**。
> 5 个平台全量包 **不要上传**，除非用户明确说“全量/新装机包一起传”。
> 版本号必须=真实当天日期；禁止未来日期、禁止旧 tag 覆盖。

## 2. 标准流程（每一步都做）

1. 改代码 → 跑离线测试（pytest 全量相关套件，见 §0 提示）；
2. 编译检查：python -m py_compile webui/server.py conclusion_store.py；
3. VERSION 改为 v<当天>；
4. 打包：E:\release\_rebuild_v4.ps1 -Win（只重打 update 所需；本机顺带生成 Windows.zip 但**只上传 update.zip**）；全量才不带开关；
5. 打包前确认 requirements.txt UTF-8；打包脚本内置凭据守卫（禁止 provider_keys/auth/weixin/channel_directory/model_config/state.db 等进包）；
6. 验证：E:\release\_test_update.ps1 -Version v<当天>（若脚本 exit 2 但 booted/HTTP 200 通过，再手动解包启动一次兜底）；
7. 更新 E:\release\RELEASE_NOTES.md（标题=当天、追加变更、同步全部资产 SHA256）；
8. 发布：gh release create v<当天> --repo GGbond-bo/MemOmics-Agent --notes-file E:/release/RELEASE_NOTES.md；再 upload（--clobber）——**只上传 MemOmics-update.zip**；全量包仅在用户明确要求时一并 upload；最后 release edit 更新说明；
9. 恢复 VERSION=vdev-<当天>；
10. 提交 docs/UPDATE_WORKFLOW.md + memomics_home/AGENTS.md + VERSION 到 git。

## 3. 绝不打包的内容（凭据守卫 + 手动双查）

- provider_keys.json、auth.json、weixin_account.json、channel_directory.json、model_config.json、state.db；
- memomics_home/sessions/、memomics_home/memories/、results/、uploads/、work/、.memory/、.install_path；
- 本机路径（C:/Users/23136、E:/MemOmics-Agent、E:/R-libs）、真实 API key；
- 用户测试数据/专利数据/微信聊天/个人记忆文件。

> 打包后务必逐个 zip/tar 解包抽查名字再上传。

## 4. 更新历史（最近）

| 日期 | tag | 内容 |
|---|---|---|
| 2026-08-31 | v2026-08-31 | 记忆分层 L0 结论/失败注册表 + L3 索引、待确认绑定、L2 最近轮速览、辩论 v2、BGI 技能、渲染/超时修复、全量 5 包重建 |
| 2026-10-09 | v2026-10-09 | 隐私裁剪两档（技能整排除/脱敏）+ 文献库留空 + 内部文档不进包 + 更新三件套与目录名适配 + 片头默认关闭（Win/MacARM/MacX64/update 四包） |
| 2026-08-27 | v2026-08-27 | 早期辩论/技能/稳定性（历史） |

## 5. 备注

- gh 路径：C:/Users/23136/AppData/Local/gh-cli/bin/gh.exe；默认代理 127.0.0.1:6478，不可用时 unset 后直连（已实测可用）。
- _test_update.ps1 尾部 exit 2 历史怪象：功能校验通过即可；发布前再手动解包启动一次。
- Windows 编码坑：.bat 是 GBK；含中文 .ps1 必须 UTF-8 BOM。
## 6. 2026-10-09 改版细则（技能两档裁剪 / 更新兜底 / 新装默认值）

用户当天确认的六条规则（打包脚本已落地）：

1. **技能两档裁剪**（`E:\release\_prune_skills.py`，**只作用于包副本，绝不动开发版**）：
   - 一档整技能排除：`EXCLUDE_NAMES`（课题复现/跨物种/专利策略/集群云平台/内部机制/私有技能）+ 真实密钥命中。
   - 二档脱敏后照发：`骨骼肌→示例组织`、`23136→<用户>`、`NHPABC→示例队列`、`MF_AUCell→示例评分方法`、
     `GSE278576→GSE000000`、`专利→知识产权`、`ssh3/5→node1/2`、`zhangbo11→user`、`hwfssz3→cluster` 等；
     若命中位于 `references/` → 该技能 references 整目录删（那是研究笔记），正文里枚举这些笔记的行也删。
   - 恒删：`logs/`、`_debates`、`.archive`、`.curator_backups`、`.usage.json*`、`.curator_state`；
     `skill.json` 的 `success_count/error_count/proven_params/proven_script/user_prefs/errors…` 运行字段全部剥掉。
   - 裁剪后重建 `SKILLS_INDEX.md`（`MEMOMICS_HOME=<包内 home> python -m webui.skills_registry --build --backfill-json`），
     并删掉 `SOUL.md` 里指向"未随包技能"的引用行（本次 10 行）。
2. **文献库留空**：完整包只建空 `memomics_home/papers/`；`references.json/.bib/.ris` 一律不进包。
3. **内部文档不进包**：根 `AGENTS.md`、`docs/**`（含 UPDATE_WORKFLOW.md）、`memomics_home/AGENTS.md`。
4. **更新兜底三件套随包**：`更新说明.txt`、`update_windows.bat`(+`.ps1`)、`update_macos_linux.sh`
   —— 自动定位安装目录（`memomics_home/.install_path` 优先）→ 只覆盖代码 → 跳过 `memomics_home` 等用户数据 → 不删文件。
   一键更新本身与目录名无关（`MEMOMICS_DIR` = 正在运行的代码目录）；结果页会回报实际覆盖到的目录。
5. **新装默认值**：片头默认关闭（`webui/index.html` 的 `introCfg()` 默认 `clip:'off'`）、浅色主题、无背景图。
6. **更新包根目录名** 维持 `MemOmics`（与安装目录同名，便于解压即合并覆盖）；旧包曾用 `MemOmics-update`，
   那个文件夹可以删，不影响。

发布前额外自检：`_test_update.ps1` 已加断言（技能数≥300、技能目录个人标识零残留、`docs/`/`AGENTS.md` 不在包内、
`papers` 为空、更新三件套存在、`/api/health`+`/api/update/autocheck` 带本地版本号）。