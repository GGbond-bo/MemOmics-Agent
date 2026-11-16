# 集群上安装并调用 ImageJ（1.x，无图形界面）—— 实测配方 2026-11-09

安装位置：`/cluster/share/user/ImageJ`（NFS 共享，node3/node1/node4 三节点直接可用）
装好的东西：ImageJ **1.54g**（`ij.jar`）+ 自带 JRE 1.8.0_345 + 虚拟屏 `envs/ij_xvfb/bin/Xvfb`（conda-forge `xorg-xvfb-server`）

## 安装步骤（只能在 node3，只有它有外网）

```bash
cd /cluster/share/user/ImageJ
# 1) 下载（官方页面实测链接；curl 老版本不认 --retry-all-errors，用 wget -c 续传）
wget -c -nv --tries=5 --timeout=60 https://wsr.imagej.net/distros/linux/ij154-linux64-java8.zip
# 2) 校验：包内顶层是 ImageJ/ 目录，启动器文件名字就叫 ImageJ（2013 版，无显示时会挂死，不要用）
unzip -t ij154-linux64-java8.zip && unzip -q -o ij154-linux64-java8.zip
mv ImageJ/* . && rmdir ImageJ          # 压平
# 3) 装虚拟屏（装到自有 env，不动 zhangxiao6 的工作环境）
export CONDA_PKGS_DIRS=/cluster/share/user/.conda_pkgs
/cluster/share/zhangxiao6/software/miniconda3/bin/conda create -y -q \
  -p /cluster/share/user/envs/ij_xvfb -c conda-forge xorg-xvfb-server
```
⚠️ 包名是 **`xorg-xvfb-server`**，`xorg-server` / `xorg-xvfb` 在 conda-forge 上都不存在。

## 调用方式：`run_ij.sh`（自动起停 Xvfb）

```bash
cd /cluster/share/user/ImageJ && ./run_ij.sh 你的宏.ijm
```
脚本逻辑：`DISPLAY` 为空且 `/tmp/.X99-lock` 不存在 → 起 `Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp`
→ 用自带 JRE 跑 `-jar ij.jar -batch 宏` → 退出时 kill Xvfb。
可调环境变量：`IJ_XMX`(默认 4g)、`IJ_DISPLAY`(默认 :99)、`IJ_XVFB`。

MemOmics 侧调用：
```
remote_cluster(action="run", node="node1",
  command="cd /cluster/share/user/ImageJ && ./run_ij.sh examples/demo_particles.ijm")
```

## 🔴 四个必须记住的坑（都实测过）

1. **`java -jar ij.jar -batch 宏` 只适合纯计算**：`newImage`/`getStatistics`/`saveAs` 正常，但
   `open()` 和任何 `run("...")` 都会 `java.awt.HeadlessException`（内部调 `IJ.init()` 建菜单栏）。
2. **`new ImageJ(ImageJ.NO_SHOW)` 也救不了**：构造时仍 `new Frame()`（ImageJ.java:148）→ 无显示必抛。
   自建 `HeadlessIJ.java` 启动类实测同样失败（保留在安装目录仅供参看）。
3. **包里原生启动器 `ImageJ-linux64` 在无 DISPLAY 时静默挂死**（实测 300s 不返回）→ 一律走 `run_ij.sh`。
4. **宏语言里版本函数是 `getVersion()`**，写 `IJ.getVersion()`（Java API 风格）会抛宏语法错。

## 无 X 时的应急读图（备选，不是首选）

宏里用 `eval("script", "...")` 走 Nashorn 调静态方法，可绕过 GUI 初始化：
```
s = "importClass(Packages.ij.IJ); var imp = IJ.openImage('路径'); java.lang.System.out.println(imp.getWidth());";
eval("script", s);
```
只能读图/取属性，`run()` 类命令仍然不行 → 真实分析还是要有 Xvfb。

## 验收记录（三节点实测）

| 测试 | 节点 | 结果 |
|---|---|---|
| 版本 | node3 | `VERSION=1.54g` |
| 像素统计 64×64 单点 200 | node3 | `area=4096 mean=0.04883 max=200`（与 200/4096 吻合） |
| 虚拟屏下 Analyze Particles（12 圆点） | node1 / node4 | `N_PARTICLES=12` + 写出 `out/particle_results.csv`、`out/mask_preview.png` |