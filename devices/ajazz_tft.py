import time

from PIL import Image, ImageOps, ImageSequence

from .base import HidHandle, find_hid

SIZE = 128
FRAME_BYTES = SIZE * SIZE * 2
CHUNK = 4096
MAX_FRAMES = 30


def load_frames(path):
    source = Image.open(path)
    frames = []
    for frame in ImageSequence.Iterator(source):
        image = ImageOps.fit(frame.convert("RGB"), (SIZE, SIZE), Image.LANCZOS)
        pixels = bytearray()
        for r, g, b in image.getdata():
            pixels += (((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)).to_bytes(2, "little")
        delay = max(40, frame.info.get("duration", source.info.get("duration", 100)) or 100)
        frames.append((bytes(pixels), delay))
        if len(frames) >= MAX_FRAMES:
            break
    return frames


def find_interfaces():
    infos = []
    for info in find_hid(0x0C45, {0x8009, 0x800A}):
        name = (info.get("product_string") or "").upper()
        if info["product_id"] == 0x800A and "AK820" not in name:
            continue
        infos.append(info)
    pages = {i["usage_page"]: i for i in infos}
    if 0xFF13 in pages and 0xFF67 not in pages and 0xFF68 in pages:
        return "legacy", pages[0xFF13], pages[0xFF68]
    if 0xFF67 in pages:
        return "web", None, pages[0xFF67]
    return None, None, None


def upload_web(data_info, frames):
    header = bytearray([0xFF] * 256)
    header[0] = len(frames)
    for i, (_, delay) in enumerate(frames[:-1]):
        header[i + 1] = min(255, delay // 5)
    header[len(frames)] = 0x00
    payload = bytes(header) + b"".join(p for p, _ in frames)

    total = (len(payload) + CHUNK - 1) // CHUNK
    dev = HidHandle(data_info["path"])
    try:
        acked = True
        for index in range(total):
            chunk = payload[index * CHUNK:(index + 1) * CHUNK]
            head = [0xAA, 0x50, index & 0xFF, index >> 8, total & 0xFF, total >> 8, 0x50, 0x06]
            dev.write([0x00] + head + list(chunk), 1 + 8 + CHUNK)
            if acked:
                acked = bool(dev.read(64, 1000 if index == 0 else 1500))
            else:
                time.sleep(0.01)
    finally:
        dev.close()


def legacy_exchange(dev, command, sub=0, value=0):
    packet = [0] * 64
    packet[0:3] = [0x04, command, sub]
    packet[8:10] = [value & 0xFF, value >> 8]
    time.sleep(0.035)
    dev.send_feature([0x00] + packet, 65)
    time.sleep(0.05)
    reply = dev.get_feature(0x00, 65)
    reply = reply[1:] if len(reply) == 65 else reply
    return reply


def legacy_ack(reply, command):
    if len(reply) < 4 or reply[0] != 0x04 or reply[1] != command or reply[3] != 0x01:
        raise OSError(f"Toetsenbord weigerde commando {command:02x}")


def upload_legacy(control_info, data_info, frames, slot=1):
    payload = bytearray([0xFF] * 256)
    payload[0] = len(frames)
    if len(frames) == 1:
        payload[1] = 0
    else:
        for i, (_, delay) in enumerate(frames):
            payload[i + 1] = max(1, min(255, delay // 2))
    payload += b"".join(p for p, _ in frames)
    payload += b"\xff" * (-len(payload) % CHUNK)
    chunks = len(payload) // CHUNK

    control = HidHandle(control_info["path"])
    data = HidHandle(data_info["path"])
    try:
        for _ in range(10):
            reply = legacy_exchange(control, 0x18, 0, 0)
            if any(reply) and list(reply[:4]) != [4, 0x18, 0, 0xFF]:
                break
            time.sleep(0.3)
        legacy_ack(reply, 0x18)
        try:
            legacy_ack(legacy_exchange(control, 0x72, slot, chunks), 0x72)
            for index in range(chunks):
                data.write([0x00] + list(payload[index * CHUNK:(index + 1) * CHUNK]), CHUNK + 1)
                if not data.read(64, 1000):
                    raise OSError(f"Geen bevestiging voor blok {index + 1}/{chunks}")
            legacy_ack(legacy_exchange(control, 0x02, 0, 0), 0x02)
        except Exception:
            legacy_exchange(control, 0xF0, 0, 1)
            raise
        time.sleep(0.1)
    finally:
        control.close()
        data.close()


def upload(path):
    kind, control, data = find_interfaces()
    if kind is None:
        return "Geen Ajazz via kabel gevonden. Het scherm kan alleen via de USB-kabel worden ingesteld."
    frames = load_frames(path)
    if kind == "web":
        upload_web(data, frames)
    else:
        upload_legacy(control, data, frames)
    return f"Verstuurd ({len(frames)} frame(s)). Zie je het niet? Druk Fn + Delete om tussen klok en afbeelding te wisselen."
