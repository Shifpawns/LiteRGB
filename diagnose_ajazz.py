import os

import hid

print("Sonix / Ajazz HID-apparaten (VID 0C45):\n")
found = False
for info in hid.enumerate(0x0C45, 0):
    found = True
    print(f"PID {info['product_id']:04X}  interface {info['interface_number']}  "
          f"usage_page {info['usage_page']:04X}  usage {info['usage']:04X}  "
          f"naam '{info.get('product_string')}'")
if not found:
    print("Niets gevonden. Zit hij via Bluetooth of op een andere manier aangesloten?")

log = os.path.join(os.environ.get("APPDATA", ""), "LiteRGB", "litergb.log")
print("\nLaatste regels uit het logbestand:\n")
try:
    with open(log, encoding="utf-8", errors="replace") as f:
        lines = [line for line in f if "AK820" in line or "ajazz" in line.lower() or "Lost" in line]
    print("".join(lines[-15:]) or "(geen regels over de Ajazz)")
except OSError:
    print("(logbestand niet gevonden)")
