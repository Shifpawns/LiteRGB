import ctypes
import logging
import os
import threading

READ = 1
WRITE = 0
BYTE_DATA = 2
WORD_DATA = 3
BLOCK_DATA = 5

MUTEX_NAME = "Global\\Access_SMBUS.HTP.Method"
DRAM_BUSES = {
    (0x1022, 0x790B),
    (0x8086, 0x3A30), (0x8086, 0xA123), (0x8086, 0x2085), (0x8086, 0xA2A3),
    (0x8086, 0xA323), (0x8086, 0x06A3), (0x8086, 0xA3A3), (0x8086, 0x43A3),
    (0x8086, 0x7AA3), (0x8086, 0x7A23), (0x8086, 0x7F23),
}


def find_library(lib_folder):
    candidates = [
        os.path.join(lib_folder, "PawnIOLib.dll"),
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "PawnIO", "PawnIOLib.dll"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


class SmbusBus:
    def __init__(self, lib, handle, name):
        self.lib = lib
        self.handle = handle
        self.name = name
        self.pci = (0, 0)
        self.mutex = None
        self.lock = threading.Lock()

        out = (ctypes.c_uint64 * 3)()
        if self.execute(b"ioctl_identity", [0], out) == 0:
            self.pci = (out[2] & 0xFFFF, (out[2] >> 16) & 0xFFFF)
        self.execute(b"ioctl_set_sleep_mode", [2], (ctypes.c_uint64 * 1)())
        try:
            self.mutex = ctypes.windll.kernel32.CreateMutexA(None, False, MUTEX_NAME.encode())
        except Exception:
            self.mutex = None

    def execute(self, name, values, out):
        data = (ctypes.c_uint64 * max(1, len(values)))(*values)
        returned = ctypes.c_size_t(0)
        return self.lib.pawnio_execute(self.handle, name, data, len(values), out, len(out),
                                       ctypes.byref(returned))

    def xfer(self, addr, read_write, command, size, payload=b""):
        raw = bytearray(40)
        raw[:len(payload)] = payload
        values = [addr, read_write, command, size] + [int.from_bytes(raw[i:i + 8], "little") for i in range(0, 40, 8)]
        out = (ctypes.c_uint64 * 5)()
        with self.lock:
            if self.mutex:
                ctypes.windll.kernel32.WaitForSingleObject(self.mutex, 0xFFFFFFFF)
            try:
                status = self.execute(b"ioctl_smbus_xfer", values, out)
            finally:
                if self.mutex:
                    ctypes.windll.kernel32.ReleaseMutex(self.mutex)
        if status != 0:
            raise OSError(f"SMBus transfer failed on {self.name} at 0x{addr:02X}")
        return b"".join(int(v).to_bytes(8, "little") for v in out)

    def read_byte(self, addr, command):
        return self.xfer(addr, READ, command, BYTE_DATA)[0]

    def write_byte(self, addr, command, value):
        self.xfer(addr, WRITE, command, BYTE_DATA, bytes([value]))

    def write_word(self, addr, command, value):
        self.xfer(addr, WRITE, command, WORD_DATA, value.to_bytes(2, "little"))

    def write_block(self, addr, command, data):
        self.xfer(addr, WRITE, command, BLOCK_DATA, bytes([len(data)]) + bytes(data))


def open_dram_buses(lib_folder):
    path = find_library(lib_folder)
    if path is None:
        return []
    try:
        lib = ctypes.WinDLL(path)
    except OSError as error:
        logging.info("PawnIO not usable: %s", error)
        return []

    lib.pawnio_open.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    lib.pawnio_load.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
    lib.pawnio_execute.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_uint64), ctypes.c_size_t,
                                   ctypes.POINTER(ctypes.c_size_t)]
    lib.pawnio_close.argtypes = [ctypes.c_void_p]
    for function in (lib.pawnio_open, lib.pawnio_load, lib.pawnio_execute, lib.pawnio_close):
        function.restype = ctypes.c_long

    buses = []
    modules = [("SmbusI801.bin", None), ("SmbusPIIX4.bin", 0), ("SmbusPIIX4.bin", 1)]
    for module, port in modules:
        blob_path = os.path.join(lib_folder, "pawnio", module)
        if not os.path.exists(blob_path):
            continue
        with open(blob_path, "rb") as f:
            blob = f.read()
        handle = ctypes.c_void_p()
        if lib.pawnio_open(ctypes.byref(handle)) != 0:
            logging.info("PawnIO open failed, run LiteRGB as administrator for RAM support")
            return buses
        if lib.pawnio_load(handle, blob, len(blob)) != 0:
            lib.pawnio_close(handle)
            continue
        bus = SmbusBus(lib, handle, module if port is None else f"piix4_{port}")
        if port is not None and bus.execute(b"ioctl_piix4_port_sel", [port], (ctypes.c_uint64 * 1)()) != 0:
            lib.pawnio_close(handle)
            continue
        if bus.pci in DRAM_BUSES:
            buses.append(bus)
        else:
            lib.pawnio_close(handle)
    return buses
