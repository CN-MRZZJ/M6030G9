# -*- coding: utf-8 -*-
"""用 SDO 和 PDO 两种方式让电机转动。
安全约束：低速(默认120rpm)、每段仅2秒、finally 里强制停机。
"""
import sys
import time
from aim_can import load_dll, Link

REPORT = "report_spin.txt"
lines = []


def w(s=""):
    lines.append(s)


class Node:
    def __init__(self, link, station, req_id=0x600):
        self.link = link
        self.station = station
        self.req_id = req_id

    # ---- SDO ----
    def _sdo(self, index, sub, payload, wait=0.25):
        req = [payload[0], index & 0xFF, (index >> 8) & 0xFF, sub] + list(payload[1:])
        req = (req + [0, 0, 0, 0])[:8]
        self.link.send(0, self.req_id, req, send_type=1)
        got = []
        end = time.time() + wait
        while time.time() < end:
            for ch in (0, 1):
                for rid, data, ext in self.link.recv(ch):
                    if 0x580 <= rid <= 0x5FF:
                        got.append((rid, data))
            time.sleep(0.005)
        return req, got

    def read(self, index, sub):
        req, got = self._sdo(index, sub, [0x40, 0, 0, 0, 0, 0, 0, 0])
        for rid, data in got:
            if data[1] == (index & 0xFF) and data[2] == ((index >> 8) & 0xFF) and data[3] == sub:
                if data[0] in (0x4F, 0x4B, 0x43):
                    n = {0x4F: 1, 0x4B: 2, 0x43: 4}[data[0]]
                    return int.from_bytes(bytes(data[4:4 + n]), "little"), data
        return None, None

    def write(self, index, sub, value, size):
        cs = {1: 0x2F, 2: 0x2B, 4: 0x23}[size]
        payload = [cs] + [(value >> (8 * i)) & 0xFF for i in range(size)] + [0] * (7 - size)
        req, got = self._sdo(index, sub, payload)
        for rid, data in got:
            if data[0] == 0x60:
                return "ACK", req, data
            if data[0] == 0x80:
                return "ABORT 0x%08X" % int.from_bytes(bytes(data[4:8]), "little"), req, data
        return "无应答", req, None

    def nmt_start(self):
        # NMT: COB-ID 0x000, data [0x01, node]
        self.link.send(0, 0x000, [0x01, self.station], send_type=1)
        time.sleep(0.05)


def fmt_frame(can_id, data):
    return "0x%03X [%s]" % (can_id, " ".join("%02X" % b for b in data))


def main():
    rpm = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    dll = load_dll()
    link = Link(dll, baud=1000, channels=(0, 1))
    link.open()

    station, _ = None, None
    # 先确定站号（尝试 0x600 请求）
    probe = Node(link, 0, 0x600)
    st, raw = probe.read(0x2615, 0)
    w("=== 准备 ===")
    w("  站号 2615h = %s" % st)
    probe.station = st if st else 1

    for idx, name in ((0x1400, "RPDO1 COB-ID"), (0x1402, "RPDO3 COB-ID"),
                      (0x1403, "RPDO4 COB-ID"), (0x1802, "TPDO3 COB-ID")):
        v, _ = probe.read(idx, 1)
        w("  %-14s = %s" % (name, ("0x%03X" % v) if v is not None else "读不到"))

    hb, _ = probe.read(0x1017, 0)
    w("  心跳产生 1017h = %s" % hb)

    rpdo3, _ = probe.read(0x1402, 1)
    pdo_id = rpdo3 if rpdo3 else (0x400 + probe.station)
    w("  -> PDO 将发往 0x%03X" % pdo_id)
    w()

    try:
        # ================= 方法一：SDO =================
        w("=== 方法一：SDO 控制（6060h / 60FFh / 6040h）===")
        for idx, sub, val, size, name in (
            (0x6060, 0, 3, 1, "工作模式=速度模式"),
            (0x60FF, 0, rpm, 4, "目标速度=%d" % rpm),
            (0x6040, 0, 0x000F, 2, "控制字=0x000F 启动"),
        ):
            res, req, _ = probe.write(idx, sub, val, size)
            w("  写 %-22s [%s] -> %s" % (name, " ".join("%02X" % b for b in req), res))
            time.sleep(0.05)

        w("  -- 采样实际速度(606Ch/10=rpm) --")
        for i in range(8):
            time.sleep(0.22)
            v, _ = probe.read(0x606C, 0)
            pos, _ = probe.read(0x6064, 0)
            w("    t=%.2fs  606Ch=%-6s (%.1f rpm)  位置=%s" % (
                (i + 1) * 0.22, v, (v or 0) / 10.0, pos))

        for idx, sub, val, size, name in (
            (0x60FF, 0, 0, 4, "目标速度=0"),
            (0x6040, 0, 0x010F, 2, "控制字=0x010F 停止"),
        ):
            res, req, _ = probe.write(idx, sub, val, size)
            w("  写 %-22s [%s] -> %s" % (name, " ".join("%02X" % b for b in req), res))
        time.sleep(0.3)
        v, _ = probe.read(0x606C, 0)
        w("  停机后 606Ch=%s" % v)
        w()

        # ================= 方法二：PDO =================
        w("=== 方法二：PDO 控制（RPDO3，DLC=7）===")
        probe.nmt_start()
        w("  已发 NMT 启动 (0x000: 01 %02X)" % probe.station)

        # RPDO3 默认映射: 6040(2B) + 6060(1B) + 60FF(4B)
        def build_pdo(ctrl, mode, speed):
            d = [ctrl & 0xFF, (ctrl >> 8) & 0xFF, mode & 0xFF]
            d += [(speed >> (8 * i)) & 0xFF for i in range(4)]
            return d

        frame = build_pdo(0x000F, 3, rpm)
        w("  发送 %s" % fmt_frame(pdo_id, frame))
        for i in range(6):
            link.send(0, pdo_id, frame, send_type=1)
            time.sleep(0.05)
        w("  -- 采样实际速度 --")
        for i in range(6):
            time.sleep(0.22)
            v, _ = probe.read(0x606C, 0)
            pos, _ = probe.read(0x6064, 0)
            w("    t=%.2fs  606Ch=%-6s (%.1f rpm)  位置=%s" % (
                (i + 1) * 0.22, v, (v or 0) / 10.0, pos))

        stop = build_pdo(0x010F, 3, 0)
        w("  发送停止 %s" % fmt_frame(pdo_id, stop))
        for i in range(6):
            link.send(0, pdo_id, stop, send_type=1)
            time.sleep(0.05)
        time.sleep(0.3)
        v, _ = probe.read(0x606C, 0)
        w("  停机后 606Ch=%s" % v)

    finally:
        # 兜底：无论出什么错都停机
        try:
            probe.write(0x60FF, 0, 0, 4)
            probe.write(0x6040, 0, 0x010F, 2)
            w("[兜底] 已发送停机命令")
        except Exception as e:
            w("[兜底] 停机异常: %s" % e)
        link.close()
        open(REPORT, "w", encoding="utf-8").write("\n".join(lines))
        print("done, see", REPORT)


if __name__ == "__main__":
    main()
