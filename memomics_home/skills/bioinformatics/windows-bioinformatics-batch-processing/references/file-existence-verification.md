# Windows 全盘文件存在性验证（用户问"我电脑上有这个文件吗/是不是没下完"）

> 2026-08-28 实测（E:/MemOmics-Agent，C/D/E/F 四盘）。适用于：大参考文件（GRCh38 fa.gz / gencode gtf.gz 等）
> 下载前/分析前先确认用户本地是否已有完整文件，不要盲目让用户重新下载 1-2 GB 文件。

## 可靠流程（按顺序）

### 1. 先确认盘符
```bash
wmic logicaldisk get name
#   本机实测输出: C  D  E  F  （注意 D/F 可能被 bash 顶层 ls 隐藏，必须用 wmic）
```

### 2. PowerShell 全盘递归搜索（最可靠，一次覆盖所有盘）
```bash
powershell -NoProfile -Command "Get-PSDrive -PSProvider FileSystem | ForEach-Object { \$drive = \$_.Root; Write-Host \"=== \$drive ===\"; Get-ChildItem -Path \$drive -Filter '*GRCh38.primary_assembly*' -Recurse -ErrorAction SilentlyContinue -Force | Select-Object -First 10 -ExpandProperty FullName }"
```
- `-Filter` 按文件名通配；`-Recurse` 全盘递归；`-ErrorAction SilentlyContinue` 跳过权限错误；
- 要搜多个文件名就按文件名各跑一次，或 `| Where-Object { $_.Name -match 'GRCh38|gencode' }`。

### 3. 区分"下载中/未完成" vs "完整文件"
- 下载工具残留：`*.part` `*.crdownload` `*.td` `*.downloading`（找在 360Downloads / 123pan / Downloads 等）
```bash
find /e/360Downloads /e/123pan /c/Users/23136/Downloads -maxdepth 2 \( -iname "*.part" -o -iname "*.crdownload" -o -iname "*.td" -o -iname "*.downloading" -o -iname "*.tmp" \) 2>/dev/null | grep -iE "gencode|GRCh38|genome|gtf|fa" | head
```
- 常见参考目录：`/e/ref* /e/refere* /e/genome* /e/gencode* /e/index* /e/data/ref* /e/reference*`

### 4. 完整性最终判定
- gzip 文件：`gzip -t <file>`（能走完 = gzip 流完整，未截断）
- 大参考文件可与远程 `curl -sI <url>` 的 `Content-Length` 比对大小
- 注意区分近似文件：`GRCh38.H3K4me3-zscore.rDHS-V3.txt.gz`（ChIP 区域文件）≠ `GRCh38.primary_assembly.genome.fa.gz`；猴 T2T gtf ≠ 人 gencode gtf。正则要精确。

### 5. 结论判定
- 全盘搜索 0 匹配 + 无下载残留 + 无参考目录 → **明确答复"文件不存在（连下载中残留都没有）"**，然后提议下载方案
- 只报"E 盘浅层没搜到"是不够的——必须 wmic 确认盘符 + PowerShell 全盘递归后才算查完

## ⚠️ 坑：MSYS/git-bash 下 `cmd //c "dir /s /b ..."` 参数被吞
- 现象：`cmd //c "dir /s /b E:\\*GRCh38*"` 只打印 cmd 版本 banner，没有搜索结果（MSYS 把 `\\` 和通配符转义掉了）
- 教训：**不要在 git-bash 里用 `cmd //c dir /s /b` 做全盘搜索**——参数传递不可靠
- 修复：用 PowerShell `Get-ChildItem -Recurse`（上面第 2 步），或 `MSYS_NO_PATHCONV=1 cmd /c "dir /s /b ..."`
- 同源坑（已有记录）：`cmd.exe //c` MSYS 转义 / PowerShell `$_` 转义，见 `batch-concurrency-monitoring-pitfalls.md`

## 2026-08-28 实例结论
- 用户问 GRCh38.primary_assembly.genome.fa.gz / gencode.v32.primary_assembly.annotation.gtf.gz 是否在本地
- 四盘全搜 = 不存在（唯一近似文件是 /e/tmp/ 的 H3K4me3 与 /e/专利/ 的猴 T2T gtf）
- 判定：需重新从 EBI 下载，下载后 `gzip -t` 验证