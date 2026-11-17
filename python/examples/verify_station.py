from aim_can import load_dll, Link
import time
dll = load_dll(); link = Link(dll, baud=1000, channels=(0,1)); link.open()
def rd(idx, sub):
    link.send(0, 0x600, [0x40, idx & 0xFF, (idx>>8)&0xFF, sub, 0,0,0,0], send_type=1)
    time.sleep(0.06)
    for ch in (0,1):
        for rid, data, e in link.recv(ch):
            if 0x580 <= rid <= 0x5FF and data[1]==(idx&0xFF) and data[2]==((idx>>8)&0xFF):
                n = {0x4F:1,0x4B:2,0x43:4}.get(data[0])
                if n: return int.from_bytes(bytes(data[4:4+n]),'little'), rid
    return None, None
print("=== 站号与应答 ID ===")
for req in (0x600, 0x601, 0x602):
    link.send(0, req, [0x40,0x15,0x26,0x00,0,0,0,0], send_type=1)
    time.sleep(0.08)
    got=[f for ch in (0,1) for f in link.recv(ch) if 0x580 <= f[0] <= 0x5FF]
    print("  请求 0x%03X -> %s" % (req, "; ".join("0x%03X[%s]"%(r," ".join("%02X"%b for b in d)) for r,d,e in got) or "无应答"))
v, rid = rd(0x2615, 0)
print("  2615h = %s (应答自 0x%03X)" % (v, rid if rid else 0))
print("=== PDO COB-ID 现状 ===")
for idx,name in ((0x1400,"RPDO1"),(0x1401,"RPDO2"),(0x1402,"RPDO3"),(0x1403,"RPDO4"),
                 (0x1800,"TPDO1"),(0x1801,"TPDO2"),(0x1802,"TPDO3"),(0x1803,"TPDO4")):
    x,_ = rd(idx,1)
    print("  %-6s = %s" % (name, ("0x%03X"%x) if x else x))
link.close()
