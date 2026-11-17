# -*- coding: utf-8 -*-
"""读取 AIM 伺服对象字典，输出到 report.txt（UTF-8）"""
import time
from aim_can import load_dll, Link, fmt

REPORT = "report.txt"
lines = []


def w(s=""):
    lines.append(s)


def decode(cs, data):
    if cs == 0x4F:
        return "UNSIGNED8 = %d" % data[4]
    if cs == 0x2B:
        return "UNSIGNED16 = %d" % (data[4] | (data[5] << 8))
    if cs == 0x4B:
        return "UNSIGNED16 = %d" % (data[4] | (data[5] << 8))
    if cs == 0x43:
        return "UNSIGNED32 = %d" % int.from_bytes(bytes(data[4:8]), "little")
    if cs == 0x60:
        return "WRITE_OK"
    if cs == 0x80:
        ab = int.from_bytes(bytes(data[4:8]), "little")
        return "ABORT 0x%08X" % ab
    return "CS=0x%02X" % cs


def sdo_read(link, index, sub, wait=0.25):
    req = [0x40, index & 0xFF, (index >> 8) & 0xFF, sub, 0, 0, 0, 0]
    link.send(0, 0x600, req, send_type=1)
    got = []
    end = time.time() + wait
    while time.time() < end:
        for ch in (0, 1):
            for f in link.recv(ch):
                if 0x580 <= f[0] <= 0x5FF:
                    got.append(f)
        time.sleep(0.01)
    return req, got


def main():
    dll = load_dll()
    link = Link(dll, baud=1000, channels=(0, 1))
    link.open()

    w("=== 1. 扫描应答节点（对 0x600~0x607 各发一次读 0x6041）===")
    responders = {}
    for req_id in range(0x600, 0x608):
        link.send(0, req_id, [0x40, 0x41, 0x60, 0x00, 0, 0, 0, 0], send_type=1)
        time.sleep(0.03)
        for ch in (0, 1):
            for f in link.recv(ch):
                if 0x580 <= f[0] <= 0x5FF:
                    responders.setdefault(f[0], set()).add(hex(req_id))
    if responders:
        for rid in sorted(responders):
            w("  应答节点 0x%03X  <- 请求 %s" % (rid, ", ".join(sorted(responders[rid]))))
    else:
        w("  无应答")
    w()

    w("=== 2. 读关键对象（请求 0x600）===")
    objs = [
        (0x1000, 0, "设备类型"),
        (0x1018, 1, "厂商ID"),
        (0x1018, 2, "产品代码"),
        (0x1018, 3, "版本号"),
        (0x1017, 0, "心跳产生间隔(ms)"),
        (0x1016, 1, "心跳消费"),
        (0x2615, 0, "站号"),
        (0x2619, 0, "模式选择"),
        (0x2601, 0, "输出使能"),
        (0x2614, 0, "参数保存标志"),
        (0x6061, 0, "当前工作模式"),
        (0x6060, 0, "工作模式设定"),
        (0x6041, 0, "状态字"),
        (0x6040, 0, "控制字"),
        (0x6064, 0, "实际位置"),
        (0x606C, 0, "实际速度"),
        (0x260E, 0, "报警代码"),
        (0x2612, 0, "系统温度"),
        (0x6079, 0, "系统电压"),
    ]
    for idx, sub, name in objs:
        req, got = sdo_read(link, idx, sub)
        tag = "%s (%04X:%d)" % (name, idx, sub)
        if not got:
            w("  %-28s -> 无应答" % tag)
            continue
        seen = set()
        for rid, data, ext in got:
            key = (rid, tuple(data))
            if key in seen:
                continue
            seen.add(key)
            w("  %-28s <- 0x%03X [%s]  %s" % (
                tag, rid, " ".join("%02X" % b for b in data),
                decode(data[0], data)))
    w()

    link.close()
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines))
    print("done, see", REPORT)


if __name__ == "__main__":
    main()
