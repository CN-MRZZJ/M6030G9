from aim_can import load_dll, Link
import time
dll = load_dll(); link = Link(dll, baud=1000, channels=(0,1)); link.open()
REQ={1:0x601,2:0x602,3:0x603}
def flush():
    for ch in (0,1): link.recv(ch)
def rd(st, idx, sub, tries=3):
    for t in range(tries):
        flush()
        link.send(0, REQ[st], [0x40, idx&0xFF,(idx>>8)&0xFF,sub,0,0,0,0], send_type=1)
        end=time.time()+0.12
        while time.time()<end:
            for ch in (0,1):
                for rid,data,e in link.recv(ch):
                    if (0x580<=rid<=0x5FF and data[1]==(idx&0xFF)
                            and data[2]==((idx>>8)&0xFF) and data[3]==sub):
                        n={0x4F:1,0x4B:2,0x43:4}.get(data[0])
                        if n: return int.from_bytes(bytes(data[4:4+n]),'little')
        time.sleep(0.01)
    return None
def wr(st, idx, sub, val, size):
    cs={1:0x2F,2:0x2B,4:0x23}[size]
    p=[cs,idx&0xFF,(idx>>8)&0xFF,sub]+[(val>>(8*i))&0xFF for i in range(size)]
    flush(); link.send(0, REQ[st], (p+[0,0,0,0])[:8], send_type=1)
    end=time.time()+0.2; ack=None
    while time.time()<end:
        for ch in (0,1):
            for rid,data,e in link.recv(ch):
                if 0x580<=rid<=0x5FF and data[0] in (0x60,0x80): ack=data[0]
        time.sleep(0.005)
    return ack
for st in (1,2,3):
    link.send(0,0x000,[0x01,st],send_type=1); time.sleep(0.02)

print("=== K1: 写只读对象是否真的生效？ ===")
v0 = rd(1,0x1000,0)
ack = wr(1,0x1000,0,999,2)
v1 = rd(1,0x1000,0)
print("  1000h 原=%s 写999 ACK=%s 读回=%s  -> %s" % (v0, hex(ack or 0), v1,
      "只回ACK未生效" if v1==v0 else "真的被改了!!"))
v0 = rd(1,0x6064,0)
ack = wr(1,0x6064,0,12345,4)
v1 = rd(1,0x6064,0)
print("  6064h 原=%s 写12345 ACK=%s 读回=%s -> %s" % (v0, hex(ack or 0), v1,
      "只回ACK未生效" if abs(v1-v0)<5 else "真的被改了!!"))

print()
print("=== K2: 状态字是否反映使能 ===")
wr(1,0x6060,0,3,1)
wr(1,0x6040,0,0x0000,2); time.sleep(0.15)
print("  6040=0x0000 -> 6041=0x%04X" % (rd(1,0x6041,0) or 0))
wr(1,0x6040,0,0x000F,2); time.sleep(0.15)
print("  6040=0x000F -> 6041=0x%04X" % (rd(1,0x6041,0) or 0))
wr(1,0x6040,0,0x010F,2); time.sleep(0.15)
print("  6040=0x010F -> 6041=0x%04X" % (rd(1,0x6041,0) or 0))

print()
print("=== K3: 四组 TPDO 的映射表 vs 实际帧 ===")
for idx,name in ((0x1A00,"TPDO1"),(0x1A01,"TPDO2"),(0x1A02,"TPDO3"),(0x1A03,"TPDO4")):
    cnt = rd(1,idx,0); maps=[]
    for k in range(1,(cnt or 0)+1):
        maps.append("0x%08X"%(rd(1,idx,k) or 0))
    cob = rd(1,0x1800+(idx-0x1A00),1)
    print("  %-6s 映射条目=%s  %s   COB-ID=0x%03X" % (name, cnt, " ".join(maps), cob or 0))

print()
print("=== K4: 触发各组 TPDO，抓实际帧 ===")
def capture(ms=0.4):
    got={}
    end=time.time()+ms
    while time.time()<end:
        for ch in (0,1):
            for rid,data,e in link.recv(ch):
                if 0x180<=rid<=0x1FF or 0x280<=rid<=0x2FF or 0x380<=rid<=0x3FF or 0x480<=rid<=0x4FF:
                    got.setdefault(rid, []).append(bytes(data))
        time.sleep(0.003)
    return got
# 速度模式、速度0，保证不动
wr(1,0x6060,0,3,1); wr(1,0x6040,0,0x000F,2); time.sleep(0.1)
flush(); link.send(0,0x401,[0x0F,0x00,0x03,0,0,0,0],send_type=1)
g=capture(0.4)
for rid in sorted(g):
    d=g[rid][0]
    print("  发 RPDO3 后收到 0x%03X  DLC=%d  %s" % (rid, len(d), " ".join("%02X"%b for b in d)))
flush(); link.send(0,0x301,[0,0,0,0, 0xE8,0x03,0,0],send_type=1)
g=capture(0.4)
for rid in sorted(g):
    d=g[rid][0]
    print("  发 RPDO2 后收到 0x%03X  DLC=%d  %s" % (rid, len(d), " ".join("%02X"%b for b in d)))
flush(); link.send(0,0x501,[0,0,0,0],send_type=1); link.send(0,0x080,[0x00],send_type=1)
g=capture(0.4)
for rid in sorted(g):
    d=g[rid][0]
    print("  发 RPDO4+SYNC 后收到 0x%03X  DLC=%d  %s" % (rid, len(d), " ".join("%02X"%b for b in d)))
for st in (1,2,3):
    link.send(0,0x000,[0x01,st],send_type=1); time.sleep(0.01)
for ch in (0x401,0x402,0x403):
    for k in range(3):
        link.send(0,ch,[0x0F,0x01,0x03,0,0,0,0],send_type=1); time.sleep(0.01)
print()
print("收尾: 节点1 速度=%s 报警=%s" % (rd(1,0x606C,0), rd(1,0x260E,0)))
link.close()
