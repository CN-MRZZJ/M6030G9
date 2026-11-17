from aim_can import load_dll, Link
import time
dll = load_dll(); link = Link(dll, baud=1000, channels=(0,1)); link.open()
print("已开卡，正在发停机命令...")
# 1) 三轮：RPDO3 里带 0x010F 停止 + 模式3 + 速度0
stop3 = [0x0F, 0x01, 0x03, 0x00, 0x00, 0x00, 0x00]
for ch in (0x401, 0x402, 0x403):
    for i in range(10):
        link.send(0, ch, stop3, send_type=1)
        time.sleep(0.005)
print("已发 RPDO3 停止帧 x30")
# 2) RPDO1 里也把目标位置锁成 0 速度模式
for ch in (0x201, 0x202, 0x203):
    for i in range(5):
        link.send(0, ch, [0x0F, 0x01, 0x03, 0x00, 0x00, 0x00, 0x00], send_type=1)
        time.sleep(0.005)
print("已发 RPDO1 停止帧 x15")
# 3) NMT 停止（让节点进入 Stopped 状态，PDO 失效 -> 不再接受运动指令）
for node in (1, 2, 3):
    for i in range(3):
        link.send(0, 0x000, [0x02, node], send_type=1)
        time.sleep(0.01)
print("已发 NMT 停止 (节点1/2/3)")
time.sleep(0.3)
link.close()
print("完成，已关卡")
