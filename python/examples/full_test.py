# -*- coding: utf-8 -*-
"""SDO / PDO 全量功能测试。
PART A  SDO 逐节点读对象
PART B  SDO 写-读回-还原
PART C  SDO 中止码（写只读对象）
PART D  SDO 地址隔离性（0x600 广播 vs 0x60X 独有）
PART E  PDO 映射表读取
PART F  RPDO3 功能（速度模式，速度 0 不转）
PART G  RPDO2 功能（写梯形速度）
PART H  RPDO1 功能（位置小台阶 +2000，动后回原位）
PART I  RPDO4 + SYNC
PART J  TPDO3 触发与内容校验
"""
import time
from aim_can import load_dll, Link

REPORT = "report_fulltest.txt"
L = []


def w(s=""):
    L.append(s)


def ok(cond):
    return "PASS" if cond else "FAIL"


REQ = {1: 0x601, 2: 0x602, 3: 0x603}
RPDO1 = {1: 0x201, 2: 0x202, 3: 0x203}
RPDO2 = {1: 0x301, 2: 0x302, 3: 0x303}
RPDO3 = {1: 0x401, 2: 0x402, 3: 0x403}
RPDO4 = {1: 0x501, 2: 0x502, 3: 0x503}
TPDO3 = {1: 0x381, 2: 0x382, 3: 0x383}
TPDO1 = {1: 0x181, 2: 0x182, 3: 0x183}


def flush(link):
    for ch in (0, 1):
        link.recv(ch)


def sdo(link, st, idx, sub, payload, wait=0.12, tries=3):
    """payload[0] 是命令符；返回 (应答CS, 数据bytes, 应答ID)"""
    p = [payload[0], idx & 0xFF, (idx >> 8) & 0xFF, sub] + list(payload[1:])
    p = (p + [0, 0, 0, 0])[:8]
    for t in range(tries):
        flush(link)
        link.send(0, REQ[st], p, send_type=1)
        end = time.time() + wait
        while time.time() < end:
            for ch in (0, 1):
                for rid, data, e in link.recv(ch):
                    if (0x580 <= rid <= 0x5FF and data[1] == (idx & 0xFF)
                            and data[2] == ((idx >> 8) & 0xFF) and data[3] == sub):
                        return data[0], bytes(data[4:8]), rid
            time.sleep(0.004)
    return None, None, None


def rd(link, st, idx, sub, tries=3):
    cs, data, rid = sdo(link, st, idx, sub, [0x40], tries=tries)
    if cs in (0x4F, 0x4B, 0x43):
        n = {0x4F: 1, 0x4B: 2, 0x43: 4}[cs]
        return int.from_bytes(data[:n], "little")
    return None


def wr(link, st, idx, sub, val, size):
    cmd = {1: 0x2F, 2: 0x2B, 4: 0x23}[size]
    payload = [cmd] + [(val >> (8 * i)) & 0xFF for i in range(size)]
    cs, data, rid = sdo(link, st, idx, sub, payload)
    if cs == 0x60:
        return "ACK"
    if cs == 0x80:
        return "ABORT_0x%08X" % int.from_bytes(data[0:4], "little")
    return "NO_REPLY"


def f_vel(ctrl, mode, speed):
    v = int(speed)
    return [ctrl & 0xFF, ctrl >> 8, mode & 0xFF,
            v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def main():
    dll = load_dll()
    link = Link(dll, baud=1000, channels=(0, 1))
    link.open()
    w("================ SDO / PDO 全量测试 ================")
    w("时间: " + time.strftime("%Y-%m-%d %H:%M:%S"))

    # NMT 启动三台（PDO 前提）
    for st in (1, 2, 3):
        link.send(0, 0x000, [0x01, st], send_type=1)
        time.sleep(0.03)
    w("已发 NMT 启动: 节点 1/2/3 -> Operational")

    # ---------- PART A ----------
    w("")
    w("=== PART A: SDO 逐节点读对象 ===")
    objs = [
        (0x1000, 0, "设备类型"), (0x1018, 1, "厂商ID"), (0x1018, 2, "产品码"),
        (0x1018, 3, "版本号"), (0x1017, 0, "心跳产生ms"), (0x1016, 1, "心跳消费"),
        (0x2615, 0, "站号"), (0x2619, 0, "模式选择"), (0x2614, 0, "保存标志"),
        (0x260E, 0, "报警"), (0x2612, 0, "温度℃"), (0x6079, 0, "电压/327"),
        (0x6078, 0, "电流/2000"), (0x6064, 0, "实际位置"), (0x606C, 0, "速度/10"),
        (0x6041, 0, "状态字"), (0x6040, 0, "控制字"), (0x6060, 0, "工作模式"),
        (0x6081, 0, "梯形速度"), (0x6083, 0, "加速度"), (0x261D, 0, "最大电流"),
        (0x2618, 0, "静止最大输出"), (0x60F9, 1, "速度环P"), (0x60F9, 2, "速度环I"),
        (0x60FB, 1, "位置环P"), (0x60FB, 2, "位置环I"),
    ]
    header = "%-20s" % "对象"
    for st in (1, 2, 3):
        header += "%12s" % ("节点%d" % st)
    w(header)
    w("-" * 56)
    base = {}
    for idx, sub, name in objs:
        row = "%-20s" % ("%s(%04X:%d)" % (name, idx, sub))
        for st in (1, 2, 3):
            v = rd(link, st, idx, sub)
            row += "%12s" % ("--" if v is None else (("0x%04X" % v) if idx in (0x6040, 0x6041) else v))
            if st == 1:
                base[(idx, sub)] = v
        w(row)

    # ---------- PART B ----------
    w("")
    w("=== PART B: SDO 写-读回-还原（节点1）===")
    tests = [(0x6081, 0, 2200, 2, "梯形速度"), (0x2618, 0, 400, 2, "静止最大输出"),
             (0x6083, 0, 40000, 2, "加速度")]
    for idx, sub, newval, size, name in tests:
        orig = rd(link, 1, idx, sub)
        r1 = wr(link, 1, idx, sub, newval, size)
        back = rd(link, 1, idx, sub)
        r2 = wr(link, 1, idx, sub, orig, size)
        after = rd(link, 1, idx, sub)
        w("  %-14s 原值=%-6s 写%d->%s 读回=%-6s 还原%s 终值=%-6s  %s" % (
            name, orig, newval, r1, back, r2, after,
            ok(back == newval and after == orig)))

    # ---------- PART C ----------
    w("")
    w("=== PART C: 写只读对象应回 ABORT ===")
    r = wr(link, 1, 0x1000, 0, 123, 2)
    w("  写 1000h(设备类型) -> %s   %s" % (r, ok(r.startswith("ABORT"))))
    r = wr(link, 1, 0x6064, 0, 0, 2)
    w("  写 6064h(实际位置) -> %s   %s" % (r, ok(r.startswith("ABORT"))))

    # ---------- PART D ----------
    w("")
    w("=== PART D: SDO 地址隔离性 ===")
    # 用 0x600 广播读 2615，看是否多台应答
    flush(link)
    link.send(0, 0x600, [0x40, 0x15, 0x26, 0x00, 0, 0, 0, 0], send_type=1)
    ids = set()
    end = time.time() + 0.3
    while time.time() < end:
        for ch in (0, 1):
            for rid, data, e in link.recv(ch):
                if 0x580 <= rid <= 0x5FF:
                    ids.add(rid)
        time.sleep(0.005)
    w("  请求 0x600 -> 应答 %d 个节点 %s  %s(>1 即广播)" % (
        len(ids), sorted("0x%03X" % i for i in ids), ok(len(ids) >= 1)))
    for st in (1, 2, 3):
        flush(link)
        link.send(0, REQ[st], [0x40, 0x15, 0x26, 0x00, 0, 0, 0, 0], send_type=1)
        rs = set()
        end = time.time() + 0.25
        while time.time() < end:
            for ch in (0, 1):
                for rid, data, e in link.recv(ch):
                    if 0x580 <= rid <= 0x5FF:
                        rs.add(rid)
        w("  请求 0x%03X -> 应答 %s   隔离%s" % (
            REQ[st], sorted("0x%03X" % i for i in rs), ok(len(rs) == 1)))

    # ---------- PART E ----------
    w("")
    w("=== PART E: PDO 映射表（节点1）===")
    for idx, name in ((0x1400, "RPDO1参数"), (0x1401, "RPDO2参数"), (0x1402, "RPDO3参数"),
                      (0x1403, "RPDO4参数"), (0x1802, "TPDO3参数")):
        cob = rd(link, 1, idx, 1)
        tt = rd(link, 1, idx, 2)
        w("  %-10s COB-ID=0x%03X 传输类型=%s" % (name, cob or 0, tt))
    for idx, name in ((0x1600, "RPDO1映射"), (0x1601, "RPDO2映射"),
                      (0x1602, "RPDO3映射"), (0x1603, "RPDO4映射"),
                      (0x1A02, "TPDO3映射")):
        cnt = rd(link, 1, idx, 0)
        maps = []
        for k in range(1, (cnt or 0) + 1):
            maps.append("0x%08X" % (rd(link, 1, idx, k) or 0))
        w("  %-10s 条目=%s  映射= %s" % (name, cnt, " ".join(maps)))

    p0 = rd(link, 1, 0x6064, 0) or 0
    w("  节点1 当前位置 = %d" % p0)

    # ---------- PART F: RPDO3 ----------
    w("")
    w("=== PART F: RPDO3 功能（0x%03X，DLC=7）===" % RPDO3[1])
    wr(link, 1, 0x6060, 0, 3, 1)
    wr(link, 1, 0x6040, 0, 0x000F, 2)
    time.sleep(0.1)
    link.send(0, RPDO3[1], f_vel(0x000F, 3, 0), send_type=1)
    time.sleep(0.05)
    link.send(0, RPDO3[1], f_vel(0x000F, 1, 0), send_type=1)   # 通过 PDO 改模式=1
    time.sleep(0.12)
    m = rd(link, 1, 0x6060, 0)
    w("  PDO 写 6060=1 后读回 = %s   %s" % (m, ok(m == 1)))
    link.send(0, RPDO3[1], f_vel(0x000F, 3, 0), send_type=1)   # 改回速度模式
    time.sleep(0.1)
    w("  已改回速度模式 6060=%s" % rd(link, 1, 0x6060, 0))
    w("  速度保持 0，未产生转动（606C=%s）" % rd(link, 1, 0x606C, 0))

    # ---------- PART G: RPDO2 ----------
    w("")
    w("=== PART G: RPDO2 功能（0x%03X，DLC=8：607A+6081）===" % RPDO2[1])
    orig_6081 = rd(link, 1, 0x6081, 0)
    frame = [0x00, 0x00, 0x00, 0x00,
             0xE8, 0x03, 0x00, 0x00]      # 607A=p0(后填) 6081=1000
    pp = p0
    frame[0:4] = [(pp >> (8 * i)) & 0xFF for i in range(4)]
    link.send(0, RPDO2[1], frame, send_type=1)
    time.sleep(0.12)
    new6081 = rd(link, 1, 0x6081, 0)
    new607a = rd(link, 1, 0x607A, 0)
    w("  PDO 写后 6081=%s (期望1000)  607A=%s (期望%d)   %s" % (
        new6081, new607a, pp, ok(new6081 == 1000)))
    wr(link, 1, 0x6081, 0, orig_6081, 2)
    w("  6081 已还原为 %s" % rd(link, 1, 0x6081, 0))

    # ---------- PART H: RPDO1 ----------
    w("")
    w("=== PART H: RPDO1 功能（0x%03X，位置小台阶 +2000）===" % RPDO1[1])
    wr(link, 1, 0x607A, 0, p0, 4)
    wr(link, 1, 0x6060, 0, 1, 1)
    time.sleep(0.1)
    wr(link, 1, 0x6040, 0, 0x000F, 2)
    time.sleep(0.15)
    tgt = p0 + 2000
    fr = [0x2F, 0x00, 0x01] + [(tgt >> (8 * i)) & 0xFF for i in range(4)]
    for k in range(4):
        link.send(0, RPDO1[1], fr, send_type=1)
        time.sleep(0.02)
    time.sleep(0.6)
    pos_a = rd(link, 1, 0x6064, 0)
    w("  目标 +2000 -> 实际 Δ=%+d   %s" % ((pos_a or 0) - p0, ok(abs((pos_a or 0) - p0 - 2000) < 60)))
    # 回原位
    fr2 = [0x2F, 0x00, 0x01] + [(p0 >> (8 * i)) & 0xFF for i in range(4)]
    for k in range(4):
        link.send(0, RPDO1[1], fr2, send_type=1)
        time.sleep(0.02)
    time.sleep(0.6)
    pos_b = rd(link, 1, 0x6064, 0)
    w("  回原位 -> Δ=%+d   %s" % ((pos_b or 0) - p0, ok(abs((pos_b or 0) - p0) < 60)))

    # ---------- PART I: RPDO4 + SYNC ----------
    w("")
    w("=== PART I: RPDO4 + SYNC（0x%03X，传输类型1）===" % RPDO4[1])
    tt4 = rd(link, 1, 0x1403, 2)
    w("  RPDO4 传输类型 = %s（1=需要 SYNC）" % tt4)
    tgt2 = p0 + 4000
    fr4 = [(tgt2 >> (8 * i)) & 0xFF for i in range(4)]
    link.send(0, RPDO4[1], fr4, send_type=1)
    time.sleep(0.3)
    pos_no_sync = rd(link, 1, 0x6064, 0)
    w("  只发 RPDO4（无 SYNC）-> Δ=%+d   %s(应为 0 附近)" % (
        (pos_no_sync or 0) - p0, ok(abs((pos_no_sync or 0) - p0) < 200)))
    # 需要 0x2F 触发：先 RPDO1 给目标，再 SYNC
    link.send(0, 0x080, [0x00], send_type=1)
    time.sleep(0.1)
    fr3 = [0x2F, 0x00, 0x01] + [(tgt2 >> (8 * i)) & 0xFF for i in range(4)]
    for k in range(3):
        link.send(0, RPDO1[1], fr3, send_type=1)
        time.sleep(0.02)
    time.sleep(0.6)
    pos_sync = rd(link, 1, 0x6064, 0)
    w("  发 SYNC + RPDO1 触发 -> Δ=%+d   %s" % (
        (pos_sync or 0) - p0, ok(abs((pos_sync or 0) - p0 - 4000) < 80)))
    for k in range(4):
        link.send(0, RPDO1[1], fr2, send_type=1)
        time.sleep(0.02)
    time.sleep(0.5)

    # ---------- PART J: TPDO3 ----------
    w("")
    w("=== PART J: TPDO3 触发与内容（0x%03X）===" % TPDO3[1])
    tt3 = rd(link, 1, 0x1802, 2)
    w("  TPDO3 传输类型 = %s（255=收到 RPDO3 立即回复）" % tt3)
    flush(link)
    link.send(0, RPDO3[1], f_vel(0x000F, 3, 0), send_type=1)
    got = []
    end = time.time() + 0.3
    while time.time() < end:
        for ch in (0, 1):
            for rid, data, e in link.recv(ch):
                if rid == TPDO3[1]:
                    got.append(bytes(data))
        time.sleep(0.004)
    if got:
        d = got[0]
        pos_t = int.from_bytes(d[0:4], "little")
        st_t = int.from_bytes(d[4:6], "little")
        pos_s = rd(link, 1, 0x6064, 0)
        st_s = rd(link, 1, 0x6041, 0)
        w("  收到 TPDO3 %d 帧，DLC=%d" % (len(got), len(d)))
        w("  TPDO3 内位置=%d   SDO读6064=%d   差=%d  %s" % (
            pos_t, pos_s, abs(pos_t - pos_s), ok(abs(pos_t - pos_s) < 200)))
        w("  TPDO3 内状态=0x%04X SDO读6041=0x%04X  %s" % (
            st_t, st_s or 0, ok(st_t == st_s)))
    else:
        w("  FAIL: 未收到 TPDO3")

    # ---------- 收尾 ----------
    w("")
    w("=== 收尾 ===")
    for st in (1, 2, 3):
        link.send(0, RPDO3[st], f_vel(0x010F, 3, 0), send_type=1)
        time.sleep(0.02)
    for st in (1, 2, 3):
        for k in range(3):
            link.send(0, RPDO3[st], f_vel(0x010F, 3, 0), send_type=1)
            time.sleep(0.02)
    time.sleep(0.2)
    for st in (1, 2, 3):
        v = rd(link, st, 0x606C, 0)
        sv = -1 if v == 65535 else v
        w("  节点%d 速度=%s(%.1f rpm) 报警=%s  %s" % (
            st, v, (sv or 0) / 10.0, rd(link, st, 0x260E, 0),
            ok(sv is not None and abs(sv) < 5)))
    link.close()
    open(REPORT, "w", encoding="utf-8").write("\n".join(L))
    print("done, see", REPORT)


if __name__ == "__main__":
    main()
