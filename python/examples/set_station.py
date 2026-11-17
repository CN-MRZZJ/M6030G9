# -*- coding: utf-8 -*-
"""改站号：写 2615h = 目标站号，然后 2614h = 1 保存到 EEPROM。
保存后必须断电重启，新站号才生效。
"""
import sys
import time
from aim_can import load_dll, Link

REPORT = "report_station.txt"
lines = []


def w(s=""):
    lines.append(s)


def read16(link, index, sub, req_id=0x600, wait=0.2):
    link.send(0, req_id, [0x40, index & 0xFF, (index >> 8) & 0xFF, sub, 0, 0, 0, 0], send_type=1)
    got = []
    end = time.time() + wait
    while time.time() < end:
        for ch in (0, 1):
            for rid, data, ext in link.recv(ch):
                if 0x580 <= rid <= 0x5FF and data[1] == (index & 0xFF) and data[2] == ((index >> 8) & 0xFF):
                    got.append((rid, data))
        time.sleep(0.01)
    if not got:
        return None, None
    rid, data = got[0]
    if data[0] in (0x4B, 0x2B):
        return (data[4] | (data[5] << 8)), (rid, data)
    if data[0] == 0x4F:
        return data[4], (rid, data)
    return None, (rid, data)


def write16(link, index, sub, value, req_id=0x600, wait=0.25):
    req = [0x2B, index & 0xFF, (index >> 8) & 0xFF, sub,
           value & 0xFF, (value >> 8) & 0xFF, 0, 0]
    link.send(0, req_id, req, send_type=1)
    ack = None
    end = time.time() + wait
    while time.time() < end:
        for ch in (0, 1):
            for rid, data, ext in link.recv(ch):
                if 0x580 <= rid <= 0x5FF and data[0] in (0x60, 0x80):
                    ack = (rid, data)
        time.sleep(0.01)
    return req, ack


def main():
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    dll = load_dll()
    link = Link(dll, baud=1000, channels=(0, 1))
    link.open()

    w("=== 改站号为 %d ===" % target)

    cur, raw = read16(link, 0x2615, 0)
    w("  当前站号 2615h = %s" % cur)

    req, ack = write16(link, 0x2615, 0, target)
    tx = " ".join("%02X" % b for b in req)
    if ack and ack[1][0] == 0x60:
        w("  写 2615h = %d   TX[%s]  -> ACK" % (target, tx))
    elif ack:
        w("  写 2615h = %d   TX[%s]  -> ABORT 0x%08X" % (
            target, tx, int.from_bytes(bytes(ack[1][4:8]), "little")))
    else:
        w("  写 2615h = %d   TX[%s]  -> 无应答" % (target, tx))

    time.sleep(0.2)
    new, raw = read16(link, 0x2615, 0)
    w("  读回 2615h = %s" % new)

    # 保存标志：0未保存 1保存中 2保存完毕
    pre, _ = read16(link, 0x2614, 0)
    w("  保存前 2614h = %s" % pre)

    req, ack = write16(link, 0x2614, 0, 1)
    tx = " ".join("%02X" % b for b in req)
    if ack and ack[1][0] == 0x60:
        w("  写 2614h = 1     TX[%s]  -> ACK" % tx)
    elif ack:
        w("  写 2614h = 1     TX[%s]  -> ABORT 0x%08X" % (
            tx, int.from_bytes(bytes(ack[1][4:8]), "little")))
    else:
        w("  写 2614h = 1     TX[%s]  -> 无应答" % tx)

    # 轮询保存状态
    for i in range(10):
        time.sleep(0.3)
        st, _ = read16(link, 0x2614, 0)
        w("  [%d] 2614h = %s  (%s)" % (
            i + 1, st, {0: "未保存", 1: "保存中", 2: "保存完毕"}.get(st, "?")))
        if st == 2:
            break

    link.close()
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines))
    print("done, see", REPORT)


if __name__ == "__main__":
    main()

