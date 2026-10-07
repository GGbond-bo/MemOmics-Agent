# L1 bigWig 本机读取 — WSL 迁移 + pybigwig 安装（2026-08-31 全链实测通过）

> 状态：✅ 本机 WSL 已可跑 L1 批量打分。**禁止再说"本机做不了 bigWig 读取"**（2026-08-31 完成验证）。
> 背景：Windows 上 pip pybigwig ❌ / conda-forge pybigwig ❌ / rtracklayer ❌ / 手写解析 ❌ / UCSC 命令行无 Windows 版——**WSL 是这台机器唯一本机路径**（详见 `bigwig-windows-read.md` 调试链）。

## 环境现状（2026-08-31 实测）

- WSL2 2.7.12（微软商店 store 版）+ Ubuntu 26.04 LTS，Python 3.14.4
- 发行版名称：`Ubuntu`（store 版注册名），Version=2
- vhdx 已迁移到 **`E:\WSL\Ubuntu\ext4.vhdx`**（C 盘已清空）
- root 直连可用：`wsl.exe -d Ubuntu -u root -- bash -lc "..."`（OOBE 重启后已解锁，**无需创建 Unix 用户即可跑 root 命令**）
- pybigwig **0.3.25** 已装（apt 官方包）
- bigWig 资源：`E:/专利/L1_resources/`（phyloP100way 9.2G / phastCons100way 5.5G / phyloP30way 7.9G），WSL 内挂载点 = `/mnt/e/专利/L1_resources/`

## 全链命令（照抄即可）

```bash
# 1. 首次 apt（已做，幂等）
wsl.exe -d Ubuntu -u root -- bash -lc "apt-get update -qq && apt-get install -y -qq python3-pybigwig python3-pip"

# 2. 验证装好
wsl.exe -d Ubuntu -u root -- bash -lc "python3 -c 'import pyBigWig; print(pyBigWig.__version__)'"

# 3. 真实打分测试（E盘 bigWig 经 /mnt/e 流式读，秒开）
wsl.exe -d Ubuntu -u root -- bash -lc "
python3 <<'EOF'
import pyBigWig, time
b = pyBigWig.open('/mnt/e/专利/L1_resources/hg38.phyloP100way.bw')
print('chroms:', len(b.chroms()))          # 356
vals = b.values('chr1', 1000000, 1002000)  # 2000bp 区间
mean = sum(v for v in vals if v is not None) / len(vals)
print('mean phyloP =', round(mean,3))
EOF"
```

结果参考：chr1:1,000,000-1,002,000 → phyloP -0.580 / phastCons 0.0194，覆盖 2000/2000 bp。读 9.2G 文件打开耗时 0.0s。

## WSL vhdx C→E 迁移（实测成功，import-in-place 法）

**HKLM BasePath=E:\WSL 注册表对 store 版 WSL 不生效**——装完不管你设没设 BasePath，vhdx 都落在 C 盘。迁移必须手动：

```bash
# ① 停 WSL
wsl.exe --shutdown

# ② 找 vhdx —— ⚠️ 路径带花括号！find 少了 {} 会报"目录不存在"
#    C:\Users\<user>\AppData\Local\wsl\{1fb83261-xxxx}\ext4.vhdx
SRC="/c/Users/23136/AppData/Local/wsl/{1fb83261-d85b-441f-a959-737a7a7c481d}/ext4.vhdx"

# ③ 复制（跨盘 1.4GB 约 1 分钟），校验字节数一致
mkdir -p /e/WSL/Ubuntu
cp "$SRC" /e/WSL/Ubuntu/ext4.vhdx && ls -la /e/WSL/Ubuntu/ext4.vhdx   # 1490026496 bytes

# ④ 注销 C 盘旧注册（删 C 盘原 vhdx）→ 原地注册 E 盘新 vhdx
wsl.exe --unregister Ubuntu
wsl.exe --import-in-place Ubuntu "E:\\WSL\\Ubuntu\\ext4.vhdx"

# ⑤ 验证：v1 显示 Ubuntu Stopped V2；wsl -d Ubuntu -u root 能进；C 盘 AppData\Local\wsl 下应无残留
wsl.exe -l -v
```

**为什么用 import-in-place 而不是 export/import**：export 要重新打包 1.4GB tar + import 再解包，慢一倍；import-in-place 直接注册现成 vhdx，秒级完成。store 版 wsl.exe 2.7.12 原生支持。

## 关键坑

1. **vhdx 路径带花括号** `{guid}`——`find /c/Users/... -name "*.vhdx"` 才能找到，手拼路径必须带 `{}`。
2. **unregister 会删 C 盘原 vhdx**——先 cp 成功并校验字节数，再 unregister，别用 mv（万一 cp 半路失败旧文件也没了）。
3. **Ubuntu 26.04 pip3 默认未装**——`python3 --version` 有了但 `pip3` 不存在，直接 `apt install python3-pip`。
4. **pybigwig 优先 apt 官方包**（`python3-pybigwig`，0.3.25+dfsg，和 PyPI 同版本）——**别 pip install pybigwig**，两个层面都别：
   - **Windows 侧根本无 wheel**（2026-09-14 经 PyPI JSON API 复核）：pyBigWig 0.3.25 只发 `manylinux`（cp39/cp310/cp311/cp312/cp313）+ macOS，**零 `win_amd64`**。所以 `.venv/Scripts/pip.exe install pyBigWig` 必退源码编译（需 MSVC + libcurl + libBigWig C 库）→ 失败。判定法：venv 目录名 `Scripts/` = Windows 本机 pip（`sys.platform=='win32'`），`bin/` = Linux/macOS——用户问"是不是撞到 linux 环境"时，`.venv/Scripts/` 就是 Windows，不是 linux，别混淆。
   - **WSL 侧 Python 3.14 太新**：PyPI 现有 wheel 无 3.14 版要源码编译，apt 免编译。
5. **git-bash 里 taskkill 用 `//F //T //PID`** 会被原样传参报"无效参数"，改用 `powershell.exe Stop-Process -Id ...`。
6. WSL 命令输出可能是 **UTF-16LE**（subprocess 里 `.decode('utf-16-le')`；bash 管道里 `tr -d '\0'` 可清洗）。
7. OOBE 锁定期（首次初始化等建用户）期间 `wsl -u root` 会超时——**重启即解锁**，不用在窗口里等。

## L1 打分脚本骨架（人侧 peak CSV → 均值分）

```python
import pyBigWig, pandas as pd
bw = pyBigWig.open('/mnt/e/专利/L1_resources/hg38.phyloP100way.bw')
df = pd.read_csv('/mnt/e/专利/human_Hf_peaks.csv')
# 第一列格式 chr1_1000_2000 → 拆 3 列
coords = df.iloc[:,0].astype(str).str.split('_', expand=True)
scores = []
for c, s, e in zip(coords[0], coords[1].astype(int), coords[2].astype(int)):
    v = bw.stats(c, s, e, type='mean')[0]
    scores.append(v if v is not None else float('nan'))
df['phyloP_mean'] = scores
df.to_csv('/mnt/e/专利/human_L1_phyloP.csv', index=False)
```
猴侧（T2T-MFA8 坐标）：先基因锚定 ortholog → hg38 坐标（见 SKILL.md L1 基因锚定节）再打同一套 hg38 轨道——phyloP100way 本身含 100 哺乳动物比对、食蟹猴在内，无需猴自己的轨道。