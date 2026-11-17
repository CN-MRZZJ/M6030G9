# -*- coding: utf-8 -*-
"""零速使能测试：只切换模式/使能，目标速度固定为 0，不让电机转动。
所有写入都可逆，最后一次写 0x010F 停机。
"""
import time
from aim_can import load_dll, Link

REPORT = "report_enable.txt"
lines = []


def w(s=""):
    lines.append(s)


def sdo_write(link, index, sub, value, size, wait=0.25):
    cs = {1: 0x2F, 2: 0x2B, 4: 0x23}[size]
    req = [cs, index & 0xFF, (index >> 8) & 0xFF, sub, 0, 0, 0, 0]
    for i in range(size):
        req[4 + i] = (value >> (8 * i)) & 0xFF
    link.send(0, 0x600, req, send_type=1)
    ack = None
    end = time.time() + wait
    while time.time() < end:
        for ch in (0, 1):
            for rid, data, ext in link.recv(ch):
                if 0x580 <= rid <= 0x5FF and data[0] in (0x60, 0x80):
                    ack = (rid, data)
        time.sleep(0.01)
    return req, ack


def sdo_read(link, index, sub, wait=0.2):
    req = [0x40, index & 0xFF, (index >> 8) & 0xFF, sub, 0, 0, 0, 0]
    link.send(0, 0x600, req, send_type=1)
    got = []
    end = time.time() + wait
    while time.time() < end:
        for ch in (0, 1):
            for rid, data, ext in link.recv(ch):
                if 0x580 <= rid <= 0x5FF:
                    got.append((rid, data))
        time.sleep(0.01)
    return got


def val16(frames, default=None):
    for rid, data in frames:
        if data[0] in (0x4B, 0x2B):
            return data[4] | (data[5] << 8)
        if data[0] == 0x4F:
            return data[4]
    return default


def main():
    dll = load_dll()
    link = Link(dll, baud=1000, channels=(0, 1))
    link.open()
    w("=== 零速使能测试（目标速度恒为 0）===")

    def do_write(index, sub, value, size, name):
        req, ack = sdo_write(link, index, sub, value, size)
        tx = " ".join("%02X" % b for b in req)
        if ack:
            ok = "ACK" if ack[1][0] == 0x60 else "ABORT 0x%08X" % int.from_bytes(
                bytes(ack[1][4:8]), "little")
            w("  写 %-22s %s  TX[%s]  -> %s" % (name, "=%d" % value, tx, ok))
        else:
            w("  写 %-22s %s  TX[%s]  -> 无应答" % (name, "=%d" % value, tx))
        return ack

    def do_read(index, sub, name):
        frames = sdo_read(link, index, sub)
        if not frames:
            w("  读 %-22s -> 无应答" % name)
            return None
        rid, data = frames[0]
        hexs = " ".join("%02X" % b for b in data)
        v = val16(frames)
        w("  读 %-22s <- 0x%03X [%s]  = %s" % (name, rid, hexs, v))
        return v

    w("--- 初始状态 ---")
    do_read(0x6041, 0, "状态字")
    do_read(0x2619, 0, "模式选择")
    do_read(0x6060, 0, "工作模式")
    do_read(0x260E, 0, "报警代码")

    w("--- 1) 切速度模式 6060h=3 ---")
    do_write(0x6060, 0, 3, 1, "工作模式")
    time.sleep(0.1)
    do_read(0x6060, 0, "工作模式")

    w("--- 2) 目标速度设 0 : 60FFh=0 ---")
    do_write(0x60FF, 0, 0, 4, "目标速度")
    time.sleep(0.1)

    w("--- 3) 使能 : 6040h=0x000F ---")
    do_write(0x6040, 0, 0x000F, 2, "控制字")
    time.sleep(0.3)
    do_read(0x6041, 0, "状态字")
    do_read(0x606C, 0, "实际速度")
    do_read(0x6064, 0, "实际位置")

    w("--- 4) 停机 : 6040h=0x010F ---")
    do_write(0x6040, 0, 0x010F, 2, "控制字(停止)")
    time.sleep(0.2)
    do_read(0x6041, 0, "状态字")
    do_read(0x606C, 0, "实际速度")

    link.close()
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines))
    print("done, see", REPORT)


if __name__ == "__main__":
    main()

