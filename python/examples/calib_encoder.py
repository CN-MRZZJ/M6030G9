from aim_can import load_dll, Link
import time
dll = load_dll(); link = Link(dll, baud=1000, channels=(0,1)); link.open()
REQ={1:0x601,2:0x602,3:0x603}
RPDO3={1:0x401,2:0x402,3:0x403}
def flush():
    for ch in (0,1): link.recv(ch)
def rd(st, idx, sub, tries=3):
    for t in range(tries):
        flush()
        link.send(0, REQ[st], [0x40, idx&0xFF,(idx>>8)&0xFF,sub,0,0,0,0], send_type=1)
        end=time.time()+0.08
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
    flush(); link.send(0, REQ[st], (p+[0,0,0,0])[:8], send_type=1); time.sleep(0.12)
def fv(ctrl,spd):
    v=int(spd)
    return [ctrl&0xFF, ctrl>>8, 0x03, v&0xFF,(v>>8)&0xFF,(v>>16)&0xFF,(v>>24)&0xFF]
for st in (1,2,3):
    link.send(0,0x000,[0x01,st],send_type=1); time.sleep(0.02)
SPD=300
for st in (1,2,3):
    wr(st,0x6060,0,3,1); wr(st,0x60FF,0,0,4); wr(st,0x6040,0,0x000F,2); time.sleep(0.08)
print("=== 精确标定：指令 %d rpm(电机)，采样 6 秒 ===" % SPD)
p_start = {st: rd(st,0x6064,0) for st in (1,2,3)}
t0 = time.perf_counter(); samples=[]
k=0
while True:
    t = time.perf_counter()-t0
    if t > 6.0: break
    for st in (1,2,3):
        link.send(0, RPDO3[st], fv(0x000F,SPD), send_type=1)
    if k % 40 == 0:   # 约每 0.2s 采一次
        row = {st:(rd(st,0x6064,0), rd(st,0x606C,0)) for st in (1,2,3)}
        samples.append((time.perf_counter()-t0, row))
    k+=1
    nxt = t0 + k*0.005
    while time.perf_counter()<nxt: pass
for st in (1,2,3):
    for kk in range(4):
        link.send(0, RPDO3[st], fv(0x010F,0), send_type=1); time.sleep(0.01)
time.sleep(0.4)
print()
print("%-8s %10s %12s %12s %12s" % ("时刻s","606C","位置","Δ位置","点数/电机圈"))
for i,(t,row) in enumerate(samples):
    if i == 0 or i == len(samples)-1:
        for st in (1,2,3):
            p,v = row[st]
            dp = p - p_start[st] if (p is not None and p_start[st] is not None) else 0
            sv = -1 if v==65535 else (v or 0)
            rate = (dp / (sv/10.0/60.0*t)) if (t>0 and sv>100) else 0
            print("%-8.2f d%d %7s %12s %12d %12.0f" % (t, st, v, p, dp, rate))
print()
# 用首尾差算
t_first, row_f = samples[1] if len(samples)>1 else samples[0]
t_last, row_l = samples[-1]
dt = t_last - t_first
print("时间窗 %.2f s" % dt)
for st in (1,2,3):
    dp = row_l[st][0]-row_f[st][0]
    vavg = ((row_l[st][1] if row_l[st][1] not in (65535,None) else 0) + (row_f[st][1] or 0))/2.0/10.0
    revs = vavg/60.0*dt
    print("  驱动%d: Δ=%d 计数, 平均速度=%.1f rpm, 转数=%.3f -> %.0f 计数/电机圈" % (
        st, dp, vavg, revs, (dp/revs) if revs>0.1 else 0))
link.close()
