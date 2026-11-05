import time

from devices.ajazz_ak820 import AjazzAK820

CANDIDATES = [
    (0x01, 0, "Statisch, snelheid 0"),
    (0x01, 5, "Statisch, snelheid 5"),
    (0x07, 0, "Ademen, snelheid 0"),
    (0x07, 5, "Ademen, snelheid 5"),
    (0x06, 0, "Kleurrijk, snelheid 0"),
    (0x10, 0, "Stromen, snelheid 0"),
]

devices = AjazzAK820.detect({})
if not devices:
    print("Geen Ajazz gevonden. Sluit LiteRGB af en probeer opnieuw.")
else:
    keyboard = devices[0]
    print(f"Verbonden via: {keyboard.kind}\n")
    print("Elke stand duurt 8 seconden, in het rood. Onthoud het nummer van de stand die stil blijft staan.\n")
    for number, (mode, speed, label) in enumerate(CANDIDATES, 1):
        print(f"Stand {number}: {label}")
        keyboard.send_raw("custom", mode, (255, 0, 0), (0, 0, 0), 0, 5, speed, 0)
        time.sleep(8)
    keyboard.close()
    print("\nKlaar. Laat me weten welk nummer stil bleef staan (of geen enkele).")
