import ij.ImageJ;
import ij.IJ;
import ij.macro.Interpreter;

/**
 * RunIjBatch —— ImageJ 1.x 批处理启动器（MemOmics 专用）。
 *
 * 为什么需要它（2026-11-09 集群实测）：
 *   1. `ij.jar -batch macro.ijm` 在 Xvfb 虚拟屏下跑完不退出 —— AWT 事件线程非守护，
 *      JVM 常驻，只能靠外层 timeout 杀，退出码永远是 124。
 *   2. `new ImageJ(NO_SHOW)` + runMacroFile（HeadlessIJ 的做法）会卡在
 *      run("Close All") / "Save changes?" 模态框上。
 *
 * 对策：先置 Interpreter.batchMode=true（等价 -batch 的静默语义：不弹框、错误直接抛），
 *       跑完显式 System.exit(0)，把退出码交还给调用方。
 *
 * 用法:
 *   java -Xmx8g -cp "ij.jar:." RunIjBatch /path/to/macro.ijm
 *   stdout 最后一行固定为 IJ_OK 或 IJ_FAIL <异常>，供 run_ij.sh 判定。
 */
public class RunIjBatch {
    public static void main(String[] args) {
        if (args.length < 1) {
            System.err.println("usage: RunIjBatch <macro.ijm>");
            System.exit(2);
        }
        Interpreter.batchMode = true;
        ImageJ ij = new ImageJ(ImageJ.NO_SHOW);
        try {
            IJ.runMacroFile(args[0]);
            System.out.println("IJ_OK");
            System.exit(0);
        } catch (Throwable t) {
            t.printStackTrace();
            System.out.println("IJ_FAIL " + t.getClass().getSimpleName() + ": " + t.getMessage());
            System.exit(1);
        }
    }
}