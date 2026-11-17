from aim_can import load_dll, Link
import time
dll = load_dll(); link = Link(dll, baud=1000, channels=(0,1)); link.open()
REQ={1:0x601,2:0x602,3:0x603}
RPDO1={1:0x201,3:0x203}
def rd(st, idx, sub, tries=2):
    for t in range(tries):
        for ch in (0,1): link.recv(ch)
        link.send(0, REQ[st], [0x40, idx&0xFF,(idx>>8)&0xFF,sub,0,0,0,0], send_type=1)
        end=time.time()+0.06
        while time.time()<end:
            for ch in (0,1):
                for rid,data,e in link.recv(ch):
                    if (0x580<=rid<=0x5FF and data[1]==(idx&0xFF)
                            and data[2]==((idx>>8)&0xFF) and data[3]==sub):
                        n={0x4F:1,0x4B:2,0x43:4}.get(data[0])
                        if n: return int.from_bytes(bytes(data[4:4+n]),'little')
        time.sleep(0.005)
    return None
def wr(st, idx, sub, val, size):
    cs={1:0x2F,2:0x2B,4:0x23}[size]
    p=[cs,idx&0xFF,(idx>>8)&0xFF,sub]+[(val>>(8*i))&0xFF for i in range(size)]
    link.send(0, REQ[st], (p+[0,0,0,0])[:8], send_type=1); time.sleep(0.1)
def f1pos(pos):
    p=int(pos)&0xFFFFFFFF
    return [0x2F,0x00,0x01, p&0xFF,(p>>8)&0xFF,(p>>16)&0xFF,(p>>24)&0xFF]
for st in (1,2,3):
    link.send(0,0x000,[0x01,st],send_type=1); time.sleep(0.02)

p={}
for st in (1,3):
    p[st]=rd(st,0x6064,0) or 0
    wr(st,0x607A,0,p[st],4); wr(st,0x6060,0,1,1); time.sleep(0.1); wr(st,0x6040,0,0x000F,2)
time.sleep(0.3)
print("两台已进入位置模式并保持当前位置：1号=%d 3号=%d" % (p[1],p[3]))
print("现在开始 4 秒静止采样（请不要碰 1、3 号）...\n")
rec={1:{"pos":[],"cur":[]},3:{"pos":[],"cur":[]}}
t0=time.perf_counter()
k=0
while time.perf_counter()-t0 < 4.0:
    for st in (1,3):
        link.send(0,RPDO1[st],f1pos(p[st]),send_type=1)
    for st in (1,3):
        v=rd(st,0x6064,0)
        if v is not None: rec[st]["pos"].append(v)
    for st in (1,3):
        c=rd(st,0x6078,0)
        if c is not None: rec[st]["cur"].append(c)
    k+=1
    time.sleep(0.01)
for st in (1,3):
    ps=rec[st]["pos"]; cs=rec[st]["cur"]
    if ps:
        print("%d号: 位置采样 %d 次  范围 %d~%d  峰峰=%d 计数   电流 %d~%d (峰峰 %d)" % (
            st, len(ps), min(ps), max(ps), max(ps)-min(ps),
            min(cs) if cs else 0, max(cs) if cs else 0, (max(cs)-min(cs)) if cs else 0))
for st in (1,3):
    wr(st,0x6060,0,3,1); wr(st,0x60FF,0,0,4); wr(st,0x6040,0,0x010F,2)
print("已切回速度模式并停止")
link.close()
