# -*- coding: utf-8 -*-
"""跟随 v4：抗抖动版。
1) 先测主轴静止时位置噪声幅度
2) 跟随中用 EMA 低通 + 死区（变化太小就不发新目标）+ 限斜率
"""
import sys
import time
from aim_can import load_dll, Link

REPORT = "report_follow_v4.txt"
lines = []


def w(s=""):
    lines.append(s)


RPDO1 = {1: 0x201, 2: 0x202, 3: 0x203}
RPDO3 = {1: 0x401, 2: 0x402, 3: 0x403}
TPDO3 = {1: 0x381, 2: 0x382, 3: 0x383}
REQ = {1: 0x601, 2: 0x602, 3: 0x603}
CPR = 32768.0   # 实测 32,940 counts/电机圈（2026-11 标定）


def rd(link, st, idx, sub, tries=4):
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
    time.sleep(0.06)


def f1pos(pos):
    p = int(pos) & 0xFFFFFFFF
    return [0x2F, 0x00, 0x01, p & 0xFF, (p >> 8) & 0xFF, (p >> 16) & 0xFF, (p >> 24) & 0xFF]


def f3vel(ctrl, speed):
    v = int(speed)
    return [ctrl & 0xFF, ctrl >> 8, 0x03,
            v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 18.0
    sign = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    ratio = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    alpha = float(sys.argv[4]) if len(sys.argv) > 4 else 0.25   # 低通系数，越小越平滑
    period = 0.02
    slew = float(sys.argv[6]) if len(sys.argv) > 6 else 6000.0      # 每次更新目标最大变化
    deadband = float(sys.argv[5]) if len(sys.argv) > 5 else 12.0   # 变化小于此值不发新目标

    dll = load_dll()
    link = Link(dll, baud=1000, channels=(0, 1))
    link.open()

    for st in (1, 2, 3):
        link.send(0, 0x000, [0x01, st], send_type=1)
        time.sleep(0.02)

    p0 = {st: (rd(link, st, 0x6064, 0) or 0) for st in (1, 2, 3)}
    w("=== 跟随 v4（alpha=%.2f, 死区=%d, 限斜率=%d/20ms）===" % (alpha, deadband, slew))
    w("  零点: 1号=%d 2号=%d 3号=%d" % (p0[1], p0[2], p0[3]))

    # 1) 测主轴静止噪声
    w("")
    w("=== 主轴静止噪声测量（1.5 秒，请别碰 2 号）===")
    vals = []
    tn = time.perf_counter()
    while time.perf_counter() - tn < 1.5:
        link.send(0, RPDO3[2], f3vel(0x0000, 0), send_type=1)
        for ch in (0, 1):
            for rid, data, e in link.recv(ch):
                if len(data) >= 6 and rid == TPDO3[2]:
                    vals.append(int.from_bytes(bytes(data[0:4]), "little"))
        time.sleep(0.004)
    if len(vals) >= 2:
        w("  采样 %d 次，位置范围 %d ~ %d，峰峰噪声 %d 计数" % (
            len(vals), min(vals), max(vals), max(vals) - min(vals)))
        p0[2] = vals[-1]
    else:
        w("  采样不足")

    for st in (1, 3):
        wr(link, st, 0x607A, 0, p0[st], 4)
        wr(link, st, 0x6060, 0, 1, 1)
        time.sleep(0.1)
        wr(link, st, 0x6040, 0, 0x000F, 2)
    wr(link, 2, 0x2601, 0, 0, 2)
    time.sleep(0.2)

    pos2 = None
    d_f = 0.0
    tgt = {1: p0[1], 3: p0[3]}
    sent = {1: p0[1], 3: p0[3]}
    n = 0
    n_send = 0
    t0 = time.perf_counter()
    t_wait = t0
    t_start = None
    started = False
    last_log = 0.0

    w("")
    w("=== 等待转动（最多 90 秒）===")
    try:
        while True:
            now = time.perf_counter()
            if started and (now - t_start) > dur:
                break
            if (not started) and (now - t_wait) > 90:
                w("  未检测到转动")
                break

            link.send(0, RPDO3[2], f3vel(0x0000, 0), send_type=1)
            for ch in (0, 1):
                for rid, data, e in link.recv(ch):
                    if len(data) >= 6 and rid == TPDO3[2]:
                        pos2 = int.from_bytes(bytes(data[0:4]), "little")

            if pos2 is not None:
                d_raw = sign * (pos2 - p0[2]) * ratio
                if (not started) and abs(d_raw) > 300:
                    started = True
                    t_start = time.perf_counter()
                    w("  >>> 开始跟随 %.0f 秒" % dur)

                # 低通
                d_f = d_f + alpha * (d_raw - d_f)

                if started:
                    for st in (1, 3):
                        want = p0[st] + d_f
                        delta = want - tgt[st]
                        if abs(delta) > slew:
                            delta = slew if delta > 0 else -slew
                        tgt[st] += delta
                        # 死区：与上次真正下发值差太小就不发
                        if abs(tgt[st] - sent[st]) >= deadband:
                            link.send(0, RPDO1[st], f1pos(tgt[st]), send_type=1)
                            sent[st] = tgt[st]
                            n_send += 1

            n += 1
            tcur = time.perf_counter()
            if tcur - last_log > 2.0:
                last_log = tcur
                w("  t=%5.1fs 主轴Δ=%+8d 滤波Δ=%+8d | 1号=%s 3号=%s  下发=%d" % (
                    tcur - t0, (pos2 - p0[2]) if pos2 else 0, int(d_f),
                    rd(link, 1, 0x6064, 0), rd(link, 3, 0x6064, 0), n_send))

            nxt = t0 + (n + 1) * period
            while time.perf_counter() < nxt:
                pass
    finally:
        e = {st: rd(link, st, 0x6064, 0) or 0 for st in (1, 2, 3)}
        for st in (1, 3):
            wr(link, st, 0x6060, 0, 3, 1)
            wr(link, st, 0x60FF, 0, 0, 4)
            wr(link, st, 0x6040, 0, 0x010F, 2)
        d2 = e[2] - p0[2]
        d1 = e[1] - p0[1]
        d3 = e[3] - p0[3]
        w("")
        w("=== 对账 ===")
        w("  2号 Δ=%+d (%.2f 圈)" % (d2, d2 / CPR))
        w("  1号 Δ=%+d 跟随率 %.1f%%" % (d1, (d1 / d2 * 100) if d2 else 0))
        w("  3号 Δ=%+d 跟随率 %.1f%%" % (d3, (d3 / d2 * 100) if d2 else 0))
        w("  两台差 %+d   共下发 %d 帧（%.1f 帧/秒）" % (d1 - d3, n_send, n_send / max(0.1, time.perf_counter() - t0)))
        w("  报警: 1=%s 2=%s 3=%s" % (
            rd(link, 1, 0x260E, 0), rd(link, 2, 0x260E, 0), rd(link, 3, 0x260E, 0)))
        link.close()
        open(REPORT, "w", encoding="utf-8").write("\n".join(lines))
        print("done, see", REPORT)


if __name__ == "__main__":
    main()


