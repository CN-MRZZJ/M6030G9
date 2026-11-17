from aim_can import load_dll, Link
import time
dll = load_dll(); link = Link(dll, baud=1000, channels=(0,1)); link.open()
REQ={1:0x601,2:0x602,3:0x603}
def rd(st, idx, sub, tries=5):
    for t in range(tries):
        for ch in (0,1): link.recv(ch)
        link.send(0, REQ[st], [0x40, idx&0xFF,(idx>>8)&0xFF,sub,0,0,0,0], send_type=1)
        end=time.time()+0.15
        while time.time()<end:
            for ch in (0,1):
                for rid,data,e in link.recv(ch):
                    if (0x580<=rid<=0x5FF and data[1]==(idx&0xFF)
                            and data[2]==((idx>>8)&0xFF) and data[3]==sub):
                        n={0x4F:1,0x4B:2,0x43:4}.get(data[0])
                        if n: return int.from_bytes(bytes(data[4:4+n]),'little')
        time.sleep(0.02)
    return None
items = [
 (0x2601,0,"输出使能 2601"),
 (0x6060,0,"工作模式 6060"),
 (0x6041,0,"状态字 6041"),
 (0x6040,0,"控制字 6040"),
 (0x60F9,1,"速度环P 60F9:1"),
 (0x60F9,2,"速度环I 60F9:2"),
 (0x60FB,1,"位置环P 60FB:1"),
 (0x60FB,2,"位置环I 60FB:2"),
 (0x60FB,3,"位置环D 60FB:3"),
 (0x6081,0,"梯形速度 6081"),
 (0x6083,0,"加速度 6083"),
 (0x2618,0,"静止最大输出 2618"),
 (0x261D,0,"最大允许电流 261D"),
 (0x2609,0,"DIR 2609"),
 (0x2619,0,"模式选择 2619"),
 (0x2612,0,"温度 2612"),
 (0x6078,0,"实际电流 6078"),
 (0x260E,0,"报警 260E"),
]
print("%-22s %10s %10s %10s" % ("参数","1号(从)","2号(主)","3号(从)"))
print("-"*58)
for idx,sub,name in items:
    vals=[]
    for st in (1,2,3):
        v = rd(st, idx, sub)
        vals.append("None" if v is None else (("0x%04X"%v) if idx in (0x6041,0x6040) else str(v)))
    mark = "  <<<" if len(set(vals))>1 else ""
    print("%-22s %10s %10s %10s%s" % (name, vals[0], vals[1], vals[2], mark))
link.close()
