# -*- coding: utf-8 -*-
"""创芯 USBCAN-II / CANalyst-II 64-bit CANopen 调试脚本（AIM 伺服）"""
import ctypes
import sys
import time
from ctypes import (Structure, c_uint, c_ubyte, c_uint16, POINTER, byref, windll)

VCI_USBCAN2 = 4
STATUS_OK = 1

# 波特率 -> (Timing0, Timing1)
TIMING = {
    1000: (0x00, 0x14), 800: (0x00, 0x16), 500: (0x00, 0x1C),
    250: (0x01, 0x1C), 125: (0x03, 0x1C), 100: (0x04, 0x1C),
}


class VCI_INIT_CONFIG(Structure):
    _fields_ = [("AccCode", c_uint), ("AccMask", c_uint), ("Reserved", c_uint),
                ("Filter", c_ubyte), ("Timing0", c_ubyte),
                ("Timing1", c_ubyte), ("Mode", c_ubyte)]


class VCI_CAN_OBJ(Structure):
    _fields_ = [("ID", c_uint), ("TimeStamp", c_uint),
                ("TimeFlag", c_ubyte), ("SendType", c_ubyte),
                ("RemoteFlag", c_ubyte), ("ExternFlag", c_ubyte),
                ("DataLen", c_ubyte), ("Data", c_ubyte * 8),
                ("Reserved", c_ubyte * 3)]


class CAN(Structure):
    _fields_ = [("ID", c_uint), ("TimeStamp", c_uint),
                ("TimeFlag", c_ubyte), ("SendType", c_ubyte),
                ("RemoteFlag", c_ubyte), ("ExternFlag", c_ubyte),
                ("DataLen", c_ubyte), ("Data", c_ubyte * 8)]


def load_dll(path="./ControlCAN.dll"):
    dll = windll.LoadLibrary(path)
    dll.VCI_OpenDevice.argtypes = [c_uint, c_uint, c_uint]
    dll.VCI_InitCAN.argtypes = [c_uint, c_uint, c_uint, POINTER(VCI_INIT_CONFIG)]
    dll.VCI_StartCAN.argtypes = [c_uint, c_uint, c_uint]
    dll.VCI_ResetCAN.argtypes = [c_uint, c_uint, c_uint]
    dll.VCI_CloseDevice.argtypes = [c_uint, c_uint]
    dll.VCI_ClearBuffer.argtypes = [c_uint, c_uint, c_uint]
    dll.VCI_Transmit.argtypes = [c_uint, c_uint, c_uint, ctypes.c_void_p, c_uint]
    dll.VCI_Receive.argtypes = [c_uint, c_uint, c_uint, ctypes.c_void_p, c_uint, c_uint]
    dll.VCI_GetReceiveNum.argtypes = [c_uint, c_uint, c_uint]
    return dll


class Link:
    def __init__(self, dll, baud=1000, channels=(0, 1), filter_mode=1):
        self.dll = dll
        self.t0, self.t1 = TIMING[baud]
        self.channels = channels
        self.filter_mode = filter_mode

    def open(self):
        r = self.dll.VCI_OpenDevice(VCI_USBCAN2, 0, 0)
        if r != STATUS_OK:
            raise RuntimeError("VCI_OpenDevice failed: %s" % r)
        for ch in self.channels:
            cfg = VCI_INIT_CONFIG(0, 0xFFFFFFFF, 0,
                                  self.filter_mode, self.t0, self.t1, 0)
            ri = self.dll.VCI_InitCAN(VCI_USBCAN2, 0, ch, byref(cfg))
            rs = self.dll.VCI_StartCAN(VCI_USBCAN2, 0, ch) if ri == STATUS_OK else 0
            self.dll.VCI_ClearBuffer(VCI_USBCAN2, 0, ch)
            print("ch%d init=%d start=%d" % (ch, ri, rs))

    def send(self, ch, can_id, data, send_type=1):
        d = (c_ubyte * 8)()
        n = len(data)
        for i, b in enumerate(data):
            d[i] = b
        obj = VCI_CAN_OBJ(can_id, 0, 0, send_type, 0, 0, n, d, (c_ubyte * 3)())
        return self.dll.VCI_Transmit(VCI_USBCAN2, 0, ch, ctypes.cast(ctypes.pointer(obj), ctypes.c_void_p), 1)

    def recv(self, ch, count=64, wait=0):
        buf = (VCI_CAN_OBJ * count)()
        n = self.dll.VCI_Receive(VCI_USBCAN2, 0, ch, ctypes.cast(buf, ctypes.c_void_p), count, wait)
        out = []
        if n > 0:
            for i in range(n):
                o = buf[i]
                out.append((o.ID & 0x7FF,
                            list(o.Data[:o.DataLen]),
                            o.ExternFlag))
        return out

    def close(self):
        for ch in self.channels:
            self.dll.VCI_ResetCAN(VCI_USBCAN2, 0, ch)
        self.dll.VCI_CloseDevice(VCI_USBCAN2, 0)


def fmt(frames):
    return ["0x%03X [%s]" % (i, " ".join("%02X" % b for b in d)) for i, d, e in frames]


def sdo_read(link, tx_ch, rx_chs, index, sub, node_id=0x600, wait=0.3):
    req = [0x40, index & 0xFF, (index >> 8) & 0xFF, sub, 0, 0, 0, 0]
    link.send(tx_ch, node_id, req, send_type=1)
    time.sleep(0.02)
    got = []
    end = time.time() + wait
    while time.time() < end:
        for ch in rx_chs:
            got += link.recv(ch)
        time.sleep(0.01)
    return req, got


if __name__ == "__main__":
    dll = load_dll()
    print("DLL loaded:", dll._name)
    link = Link(dll, baud=1000, channels=(0, 1))
    link.open()

    print("== 探测: 发 SDO 读 6040h 到 0x600，两通道都听 ==")
    req, got = sdo_read(link, 0, (0, 1), 0x6040, 0, wait=0.5)
    print("  TX:", " ".join("%02X" % b for b in req))
    if not got:
        print("  RX: 无")
    for line in fmt(got):
        print("  RX", line)

    print("== 探测: 发 0x123 测试帧，验证发送 ==")
    link.send(0, 0x123, [0xAA, 0xBB, 0xCC])
    time.sleep(0.1)
    for ch in (0, 1):
        frames = link.recv(ch)
        print("  ch%d RX: %s" % (ch, fmt(frames) or "无"))

    link.close()

