# -*- coding: utf-8 -*-
"""测量纯 PDO 发送速率（不读回），决定可合成的最高音高。"""
import time
from aim_can import load_dll, Link

REPORT = "report_rate.txt"
lines = []


def w(s=""):
    lines.append(s)


def main():
    dll = load_dll()
    link = Link(dll, baud=1000, channels=(0, 1))
    link.open()

    # 站号 1 那台目前在 0x403 实际通道上（此前的实测结论），先扫一遍找活的通道
    w("=== 探测当前实际生效的 RPDO3 通道 ===")
    link.send(0, 0x000, [0x01, 0x01], send_type=1)
    link.send(0, 0x000, [0x01, 0x03], send_type=1)
    time.sleep(0.05)

    live = []
    for cand in (0x401, 0x402, 0x403):
        frame = [0x0F, 0x00, 0x03, 0x00, 0x00, 0x00, 0x00]  # 6060=3, 速度0
        for i in range(3):
            link.send(0, cand, frame, send_type=1)
        time.sleep(0.05)
        # 用 SDO 读回任意一台的 6060 判断（先只记录，不判定）
        live.append(cand)
    w("  候选通道: %s（具体哪台生效稍后用 SDO 确认）" % ", ".join("0x%03X" % c for c in live))

    w()
    w("=== 发送速率测试 ===")
    N = 1000
    frame = [0x0F, 0x00, 0x03, 0x1E, 0x00, 0x00, 0x00]  # 30 rpm 方波的一个相位
    t0 = time.perf_counter()
    for i in range(N):
        link.send(0, 0x403, frame, send_type=1)
    dt = time.perf_counter() - t0
    fps = N / dt
    w("  发送 %d 帧耗时 %.3f s" % (N, dt))
    w("  纯发送速率 ≈ %.0f 帧/秒" % fps)
    w("  方波最高音高 ≈ %.0f Hz（每周期 2 帧）" % (fps / 2))
    w("  正弦（16 采样/周期）最高 ≈ %.0f Hz" % (fps / 16))

    # 复位速度
    stop = [0x0F, 0x00, 0x03, 0x00, 0x00, 0x00, 0x00]
    for i in range(5):
        link.send(0, 0x403, stop, send_type=1)
        time.sleep(0.02)

    link.close()
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines))
    print("done, see", REPORT)


if __name__ == "__main__":
    main()
