# -*- coding: utf-8 -*-
"""扫描总线上有几台伺服在应答。
方法：对 0x600 反复发读 2615h，收集所有 0x58x 应答（去重）；
另外逐个试 0x601..0x60F，看哪些请求地址能通。
"""
import time
from aim_can import load_dll, Link

REPORT = "report_scan_bus.txt"
lines = []


def w(s=""):
    lines.append(s)


def flush(link):
    for ch in (0, 1):
        link.recv(ch)


def read_via(link, req_id, idx, sub, wait=0.25):
    """返回 [(应答ID, 值), ...] ，可能多台同时应答"""
    flush(link)
    link.send(0, req_id, [0x40, idx & 0xFF, (idx >> 8) & 0xFF, sub, 0, 0, 0, 0], send_type=1)
    out = []
    end = time.time() + wait
    while time.time() < end:
        for ch in (0, 1):
            for rid, data, e in link.recv(ch):
                if (0x580 <= rid <= 0x5FF and data[1] == (idx & 0xFF)
                        and data[2] == ((idx >> 8) & 0xFF) and data[3] == sub):
                    n = {0x4F: 1, 0x4B: 2, 0x43: 4}.get(data[0])
                    if n:
                        out.append((rid, int.from_bytes(bytes(data[4:4 + n]), "little")))
        time.sleep(0.005)
    return out


def main():
    dll = load_dll()
    link = Link(dll, baud=1000, channels=(0, 1))
    link.open()

    w("=== 1) 向 0x600 反复读站号，收集应答 ===")
    nodes = {}
    for i in range(6):
        for rid, val in read_via(link, 0x600, 0x2615, 0, wait=0.2):
            nodes.setdefault(rid, set()).add(val)
        time.sleep(0.05)

    if not nodes:
        w("  没有任何应答")
    else:
        for rid in sorted(nodes):
            w("  应答节点 0x%03X  站号读数=%s" % (rid, sorted(nodes[rid])))
    w("  >>> 在线电机数量 = %d" % len(nodes))
    w()

    w("=== 2) 逐个请求地址 0x601~0x60F 测试 ===")
    alive = []
    for req in range(0x601, 0x610):
        res = read_via(link, req, 0x2615, 0, wait=0.12)
        if res:
            ids = sorted(set(r for r, v in res))
            w("  请求 0x%03X -> 应答 %s" % (req, ", ".join("0x%03X" % i for i in ids)))
            alive.append(req)
    if not alive:
        w("  0x601~0x60F 全部无应答（说明只能走 0x600）")
    w()

    w("=== 3) 每台的 PDO3 通道 ===")
    for rid in sorted(nodes):
        r1 = read_via(link, 0x600, 0x1402, 1, wait=0.2)
        r2 = read_via(link, 0x600, 0x1802, 1, wait=0.2)
        v1 = next((v for r, v in r1 if r == rid), None)
        v2 = next((v for r, v in r2 if r == rid), None)
        w("  %s: RPDO3=%s  TPDO3=%s" % (
            "0x%03X" % rid,
            ("0x%03X" % v1) if v1 is not None else "未取到",
            ("0x%03X" % v2) if v2 is not None else "未取到"))
        time.sleep(0.05)

    link.close()
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines))
    print("done, see", REPORT)


if __name__ == "__main__":
    main()
