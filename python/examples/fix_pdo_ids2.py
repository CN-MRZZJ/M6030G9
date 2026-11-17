# -*- coding: utf-8 -*-
"""按站号逐个直接写 8 个 PDO COB-ID（不做禁用/启用两步），写完保存。"""
import sys
import time
from aim_can import load_dll, Link

REPORT = "report_pdo_fix2.txt"
lines = []


def w(s=""):
    lines.append(s)


def flush(link):
    for ch in (0, 1):
        link.recv(ch)


def rd(link, idx, sub, wait=0.25):
    flush(link)
    link.send(0, 0x600, [0x40, idx & 0xFF, (idx >> 8) & 0xFF, sub, 0, 0, 0, 0], send_type=1)
    end = time.time() + wait
    while time.time() < end:
        for ch in (0, 1):
            for rid, data, e in link.recv(ch):
                if (0x580 <= rid <= 0x5FF and data[1] == (idx & 0xFF)
                        and data[2] == ((idx >> 8) & 0xFF) and data[3] == sub):
                    n = {0x4F: 1, 0x4B: 2, 0x43: 4}.get(data[0])
                    if n:
                        return int.from_bytes(bytes(data[4:4 + n]), "little")
        time.sleep(0.005)
    return None


def wr32(link, idx, sub, val, wait=0.3):
    flush(link)
    p = [0x23, idx & 0xFF, (idx >> 8) & 0xFF, sub] + [(val >> (8 * i)) & 0xFF for i in range(4)]
    link.send(0, 0x600, p, send_type=1)
    end = time.time() + wait
    while time.time() < end:
        for ch in (0, 1):
            for rid, data, e in link.recv(ch):
                if 0x580 <= rid <= 0x5FF and data[1] == (idx & 0xFF) and data[2] == ((idx >> 8) & 0xFF) and data[3] == sub:
                    if data[0] == 0x60:
                        return "ACK"
                    if data[0] == 0x80:
                        return "ABORT 0x%08X" % int.from_bytes(bytes(data[4:8]), "little")
        time.sleep(0.005)
    return "无应答"


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    dll = load_dll()
    link = Link(dll, baud=1000, channels=(0, 1))
    link.open()

    w("=== 按站号 %d 逐个写 PDO COB-ID ===" % n)
    w("  站号 2615h = %s" % rd(link, 0x2615, 0))

    targets = [
        (0x1400, 0x200 + n, "RPDO1"), (0x1401, 0x300 + n, "RPDO2"),
        (0x1402, 0x400 + n, "RPDO3"), (0x1403, 0x500 + n, "RPDO4"),
        (0x1800, 0x180 + n, "TPDO1"), (0x1801, 0x280 + n, "TPDO2"),
        (0x1802, 0x380 + n, "TPDO3"), (0x1803, 0x480 + n, "TPDO4"),
    ]
    for idx, val, name in targets:
        old = rd(link, idx, 1)
        if old == val:
            w("  %-6s 已是 0x%03X，跳过" % (name, val))
            continue
        res = wr32(link, idx, 1, val)
        time.sleep(0.1)
        new = rd(link, idx, 1)
        w("  %-6s %04X:1  0x%03X -> 0x%03X   写入=%s  读回=%s  %s" % (
            name, idx, old if old is not None else 0, val, res,
            ("0x%03X" % new) if new is not None else "?", "OK" if new == val else "不符"))

    w()
    w("=== 保存 ===")
    flush(link)
    link.send(0, 0x600, [0x2B, 0x14, 0x26, 0x00, 0x01, 0x00, 0x00, 0x00], send_type=1)
    time.sleep(0.5)
    for i in range(10):
        time.sleep(0.3)
        v = rd(link, 0x2614, 0)
        w("  [%d] 2614h = %s (%s)" % (i + 1, v, {0: "未保存", 1: "保存中", 2: "保存完毕"}.get(v, "?")))
        if v == 2:
            break

    w()
    w("=== 最终核对 ===")
    ok = 0
    for idx, val, name in targets:
        v = rd(link, idx, 1)
        good = (v == val)
        ok += 1 if good else 0
        w("  %-6s = %s (期望 0x%03X) %s" % (
            name, ("0x%03X" % v) if v is not None else "读不到", val, "OK" if good else "不符"))
    w("  符合 %d/8" % ok)

    link.close()
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines))
    print("done, see", REPORT)


if __name__ == "__main__":
    main()
