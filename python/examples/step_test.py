# -*- coding: utf-8 -*-
"""受控台阶测试：把 1、3 各走一个已知的 +20000 脉冲台阶，看是否走得动、走得准。"""
import time
from aim_can import load_dll, Link

REPORT = "report_step.txt"
lines = []


def w(s=""):
    lines.append(s)


RPDO1 = {1: 0x201, 2: 0x202, 3: 0x203}
RPDO3 = {1: 0x401, 2: 0x402, 3: 0x403}
REQ = {1: 0x601, 2: 0x602, 3: 0x603}


def rd(link, st, idx, sub, tries=5):
    for t in range(tries):
        for ch in (0, 1):
            link.recv(ch)
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
    link.send(0, REQ[st], (p + [0, 0, 0, 0])[:8], send_type=1)
    time.sleep(0.08)


def f1(ctrl, pos):
    p = int(pos) & 0xFFFFFFFF
    return [ctrl & 0xFF, ctrl >> 8, 0x01,
            p & 0xFF, (p >> 8) & 0xFF, (p >> 16) & 0xFF, (p >> 24) & 0xFF]


def main():
    dll = load_dll()
    link = Link(dll, baud=1000, channels=(0, 1))
    link.open()

    for st in (1, 2, 3):
        link.send(0, 0x000, [0x01, st], send_type=1)
        time.sleep(0.02)

    w("=== 测试前状态 ===")
    for st in (1, 2, 3):
        w("  站号%d: 模式=%s 状态字=0x%04X 位置=%s 速度=%s 报警=%s" % (
            st, rd(link, st, 0x6060, 0), rd(link, st, 0x6041, 0) or 0,
            rd(link, st, 0x6064, 0), rd(link, st, 0x606C, 0), rd(link, st, 0x260E, 0)))

    p0 = {}
    for st in (1, 3):
        p0[st] = rd(link, st, 0x6064, 0) or 0
        # 位置模式，目标先设为当前位置
        wr(link, st, 0x607A, 0, p0[st], 4)
        wr(link, st, 0x6060, 0, 1, 1)
        time.sleep(0.1)
        wr(link, st, 0x6040, 0, 0x000F, 2)
        time.sleep(0.1)
        w("  %d号就绪: 模式=%s 状态字=0x%04X 目标=%s" % (
            st, rd(link, st, 0x6060, 0), rd(link, st, 0x6041, 0) or 0,
            rd(link, st, 0x607A, 0)))

    STEP = 20000
    w("")
    w("=== 下发 +%d 脉冲台阶（每台连发 8 次 0x2F，间隔 15ms）===" % STEP)
    try:
        for st in (1, 3):
            tgt = p0[st] + STEP
            for k in range(8):
                link.send(0, RPDO1[st], f1(0x000F, tgt), send_type=1)
                time.sleep(0.015)
                link.send(0, RPDO1[st], f1(0x002F, tgt), send_type=1)
                time.sleep(0.015)

        w("")
        w("=== 观察 2.5 秒 ===")
        t0 = time.perf_counter()
        for i in range(10):
            time.sleep(0.25)
            row = []
            for st in (1, 3):
                p = rd(link, st, 0x6064, 0)
                v = rd(link, st, 0x606C, 0)
                row.append("%d号: Δ=%+7d 速度=%s" % (
                    st, (p - p0[st]) if p is not None else 0, v))
            w("  t=%.2fs  %s" % (time.perf_counter() - t0, "   ".join(row)))
    finally:
        w("")
        w("=== 结果 ===")
        for st in (1, 3):
            p = rd(link, st, 0x6064, 0)
            d = (p - p0[st]) if p is not None else 0
            w("  %d号: 目标 +%d  实际 %+d   完成率 %.1f%%  报警=%s" % (
                st, STEP, d, d / STEP * 100.0, rd(link, st, 0x260E, 0)))
        # 收尾：回到起始位置附近
        for st in (1, 3):
            for k in range(5):
                link.send(0, RPDO1[st], f1(0x000F, p0[st]), send_type=1)
                time.sleep(0.015)
                link.send(0, RPDO1[st], f1(0x002F, p0[st]), send_type=1)
                time.sleep(0.015)
            time.sleep(0.3)
            wr(link, st, 0x6060, 0, 3, 1)
            wr(link, st, 0x60FF, 0, 0, 4)
            wr(link, st, 0x6040, 0, 0x010F, 2)
        w("  已切回速度模式并停止")
        link.close()
        open(REPORT, "w", encoding="utf-8").write("\n".join(lines))
        print("done, see", REPORT)


if __name__ == "__main__":
    main()
