# -*- coding: utf-8 -*-
"""电子齿轮核查：读三台 260A/260B，再用同速度等时转动比对位置增量比例。
同时把 2 号的 261D（最大电流）恢复成出厂 7003（之前被限到 100）。
"""
import time
from aim_can import load_dll, Link

REPORT = "report_gear_check.txt"
L = []


def w(s=""):
    L.append(s)


REQ = {1: 0x601, 2: 0x602, 3: 0x603}
RPDO3 = {1: 0x401, 2: 0x402, 3: 0x403}


def flush(link):
    for ch in (0, 1):
        link.recv(ch)


def rd(link, st, idx, sub, tries=4):
    for t in range(tries):
        flush(link)
        link.send(0, REQ[st], [0x40, idx & 0xFF, (idx >> 8) & 0xFF, sub, 0, 0, 0, 0], send_type=1)
        end = time.time() + 0.15
        while time.time() < end:
            for ch in (0, 1):
                for rid, data, e in link.recv(ch):
                    if (0x580 <= rid <= 0x5FF and data[1] == (idx & 0xFF)
                            and data[2] == ((idx >> 8) & 0xFF) and data[3] == sub):
                        n = {0x4F: 1, 0x4B: 2, 0x43: 4}.get(data[0])
                        if n:
                            return int.from_bytes(bytes(data[4:4 + n]), "little")
        time.sleep(0.02)
    return None


def wr(link, st, idx, sub, val, size):
    cs = {1: 0x2F, 2: 0x2B, 4: 0x23}[size]
    p = [cs, idx & 0xFF, (idx >> 8) & 0xFF, sub] + [(val >> (8 * i)) & 0xFF for i in range(size)]
    flush(link)
    link.send(0, REQ[st], (p + [0, 0, 0, 0])[:8], send_type=1)
    time.sleep(0.1)


def f_vel(ctrl, mode, speed):
    v = int(speed)
    return [ctrl & 0xFF, ctrl >> 8, mode & 0xFF,
            v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def main():
    dll = load_dll()
    link = Link(dll, baud=1000, channels=(0, 1))
    link.open()
    for st in (1, 2, 3):
        link.send(0, 0x000, [0x01, st], send_type=1)
        time.sleep(0.03)

    w("=== 1. 电子齿轮与限流当前值 ===")
    w("%-6s %10s %10s %10s %10s %10s" % ("驱动器", "260A分子", "260B分母", "比值", "261D电流", "理论cnt/圈"))
    gear = {}
    for st in (1, 2, 3):
        num = rd(link, st, 0x260A, 0)
        den = rd(link, st, 0x260B, 0)
        cur = rd(link, st, 0x261D, 0)
        r = (num / den) if (num and den) else 0
        gear[st] = r
        w("%-6d %10s %10s %10.3f %10s %10s" % (
            st, num, den, r, cur, ("%.0f" % (32768 * r)) if r else "?"))

    # 2 号限流曾被限到 100，恢复出厂 7003，否则它跑不动
    c2 = rd(link, 2, 0x261D, 0)
    if c2 is not None and c2 < 1000:
        wr(link, 2, 0x261D, 0, 7003, 2)
        w("  [已把 2 号 261D 从 %s 恢复到 7003（出厂 3.5A）]" % c2)
    w("")

    w("=== 2. 同速度等时转动，比对位置增量 ===")
    SPEED = 300          # 电机转速
    DUR = 2.0
    for st in (1, 2, 3):
        wr(link, st, 0x6060, 0, 3, 1)
        wr(link, st, 0x60FF, 0, 0, 4)
        wr(link, st, 0x6040, 0, 0x000F, 2)
        time.sleep(0.1)
    p0 = {st: rd(link, st, 0x6064, 0) for st in (1, 2, 3)}
    w("  起始位置: %s" % p0)

    fr = f_vel(0x000F, 3, SPEED)
    t0 = time.perf_counter()
    n = 0
    while True:
        t = time.perf_counter() - t0
        if t > DUR:
            break
        for st in (1, 2, 3):
            link.send(0, RPDO3[st], fr, send_type=1)
        n += 1
        nxt = t0 + n * 0.005
        while time.perf_counter() < nxt:
            pass
    # 停
    for st in (1, 2, 3):
        for k in range(4):
            link.send(0, RPDO3[st], f_vel(0x010F, 3, 0), send_type=1)
            time.sleep(0.01)
    time.sleep(0.5)
    p1 = {st: rd(link, st, 0x6064, 0) for st in (1, 2, 3)}

    w("  结束位置: %s" % p1)
    w("")
    w("%-6s %12s %12s %10s" % ("驱动器", "位置增量", "相对1号", "按齿轮预测"))
    base = None
    for st in (1, 2, 3):
        d = (p1[st] - p0[st]) if (p1[st] is not None and p0[st] is not None) else 0
        if st == 1:
            base = d
        rel = (d / base) if base else 0
        pred = (gear[st] / gear[1]) if gear[1] else 0
        w("%-6d %12d %12.3f %10.3f  %s" % (
            st, d, rel, pred, "一致" if abs(rel - pred) < 0.1 else ("<<< 不一致")))

    w("")
    for st in (1, 2, 3):
        w("  驱动器%d: 速度反馈=%s 报警=%s" % (
            st, rd(link, st, 0x606C, 0), rd(link, st, 0x260E, 0)))
    link.close()
    open(REPORT, "w", encoding="utf-8").write("\n".join(L))
    print("done, see", REPORT)


if __name__ == "__main__":
    main()
