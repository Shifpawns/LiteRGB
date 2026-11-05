# LiteRGB

Kleine RGB-manager voor Windows zonder services, account of telemetrie. Eén proces, ongeveer 50 MB RAM, zit in het systeemvak.

LiteRGB raakt geen fan- of pompsnelheden aan; die laat je aan FanControl over.

## Ondersteunde apparaten

| Apparaat | Wat werkt |
| --- | --- |
| NZXT Kraken Elite (2023) | LCD: sensoren, afbeelding/GIF of standaard NZXT-scherm |
| NZXT RGB & Fan Controller | RGB per led |
| Lian Li Uni Hub SL Infinity | RGB per led (8 binnen + 12 buiten per fan) |
| Corsair K95 RGB Platinum | RGB per toets + lichtbalk |
| SteelSeries Aerox 9 | 3 zones, via kabel en dongle |
| MSI Z390 Gaming Edge AC (Mystic Light) | Onboard, JRGB1, JRGB2, JRAINBOW1 |
| Gigabyte B850 AORUS ELITE WIFI7 ICE (RGB Fusion) | Onboard-leds + de 3 ARGB-headers per led (hier zitten de Thermalright-fans op) |
| Ajazz AK820 Pro | Ingebouwde effecten van het toetsenbord (geen live golf per toets), afbeelding/GIF op het schermpje (alleen via kabel) |
| PS5 DualSense | Lichtbalk, via kabel en Bluetooth |
| Corsair RGB RAM (Vengeance RGB DDR5, Dominator, Vengeance Pro DDR4 en meer) | Per led, alleen als administrator en met PawnIO (zie hieronder) |

Effecten: uit, statisch, ademen, kleurcyclus, regenboog golf, verloop. Per apparaat kun je een eigen effect kiezen of laten synchroniseren.

## Snel starten (alleen de .exe)

Download `LiteRGB.exe` bij de nieuwste release op https://github.com/Shifpawns/LiteRGB/releases en start hem. Python is dan niet nodig. Updates gaan via Instellingen > "Zoeken naar updates"; LiteRGB zoekt ook zelf bij het opstarten.

Een nieuwe versie uitbrengen: verhoog `VERSION` in `main.py` en push naar `main`. GitHub maakt dan zelf de tag, bouwt de exe en zet hem bij de releases.

## Installeren vanuit de broncode

1. Installeer Python 3.12 van python.org (vink "Add to PATH" aan).
2. Pak deze map uit, bijvoorbeeld naar `C:\Tools\LiteRGB`.
3. Dubbelklik `install.bat`.
4. **Sluit SignalRGB, NZXT CAM, iCUE, SteelSeries GG, L-Connect en MSI Center** en haal ze uit je opstartprogramma's. Anders vechten ze om dezelfde apparaten.
5. Start met `start.bat`. Instellingen > "Starten met Windows" zet autostart aan.

Werkt iets niet? Start `debug.bat`, dan zie je het logbestand.

Liever een losse .exe? Draai `build_exe.bat`, het resultaat staat in `dist\LiteRGB`.

## CPU-temperatuur op het LCD (optioneel)

Vloeistoftemperatuur en CPU-belasting werken altijd. Voor de CPU-temperatuur:

1. Download LibreHardwareMonitor en kopieer `LibreHardwareMonitorLib.dll` (en `HidSharp.dll`) naar een map `lib` naast `main.py`.
2. `.venv\Scripts\python -m pip install pythonnet`
3. Start LiteRGB als administrator. Zet daarna "Starten met Windows" opnieuw aan, dan start hij voortaan met adminrechten.

Recente LibreHardwareMonitor-versies hebben ook de PawnIO-driver nodig; die installer zit bij LibreHardwareMonitor.

## Instellingen die je misschien moet aanpassen

Alles staat in `%APPDATA%\LiteRGB\config.json`:

- `lianli_fans_per_channel`: aantal fans per poort op de Uni Hub, bijvoorbeeld `[3, 0, 0, 0]`. Klopt dit, dan loopt de golf netjes over je fans.
- `nzxt_leds_per_channel`: aantal leds per kanaal op de NZXT-controller.
- `gigabyte_argb_leds`: aantal leds per ARGB-header op het Gigabyte-bord (ARGB_V2_1, _2, _3), standaard `[32, 32, 32]`. Zitten je 3 Thermalright-fans in serie op header 1, zet dan het totaal aantal leds van de 3 fans op de eerste plek en de rest op 0.

Herstart LiteRGB na het aanpassen.

## Opslaan in apparaten

De knop "Opslaan in apparaten" (tabblad Verlichting) zet je huidige instelling in het geheugen van de apparaten zelf, zodat ze die tonen als LiteRGB niet draait. Er wordt vertaald naar het ingebouwde effect dat er het dichtst bij zit:

| LiteRGB | MSI | NZXT controller | Corsair K95 | Aerox 9 |
| --- | --- | --- | --- | --- |
| Statisch | Statisch | Vast | Kleurwissel met 1 kleur | 3 zones |
| Ademen | Ademen | Ademen | Puls | Huidige kleuren |
| Kleurcyclus | Kleurwissel | Spectrum | Kleurwissel willekeurig | Regenboog |
| Regenboog golf | Regenbooggolf | Regenboogstroom | Regenbooggolf | Regenboog |
| Verloop | Kleurgolf | Vervagen tussen 2 kleuren | Kleurgolf | Huidige kleuren |

Lian Li SL Infinity en het Kraken-LCD kunnen niets opslaan. Corsair is experimenteel: OpenRGB heeft dit alleen getest op de K70 MK2.
Druk niet te vaak op de knop, het geheugen van apparaten slijt van veel schrijfacties.

Testen: opslaan, LiteRGB afsluiten, pc helemaal uit (stroom eraf) en weer aan.

## Opmerkingen nieuwe apparaten

- **Ajazz AK820 Pro**: het toetsenbord krijgt het dichtstbijzijnde ingebouwde effect (statisch, ademen, spectrum, regenboogstroom). Per-toets live effecten zijn te traag over dit protocol. Bluetooth-modus wordt niet ondersteund, kabel en 2.4 GHz-ontvanger wel. Het schermpje stel je in via het tabblad Ajazz-scherm, alleen met de USB-kabel. Via de ontvanger: als het toetsenbord slaapt, druk op een toets, LiteRGB probeert het elke 10 seconden opnieuw. Sluit de Ajazz-driver.
- **DualSense**: Steam Input kan de lichtbalk overschrijven als een game draait. Via Bluetooth kost het iets meer accu.
- **Corsair RGB RAM**: RAM zit op de SMBus van het moederbord. Daarvoor zijn nodig:
  1. De PawnIO-driver, te installeren via https://pawnio.eu (dezelfde driver die OpenRGB en LibreHardwareMonitor gebruiken).
  2. LiteRGB als administrator starten.
  De modules staan al in `lib\pawnio`. Zonder PawnIO of adminrechten slaat LiteRGB de RAM gewoon over. Uitzetten kan met `"ram_support": false` in config.json. RAM wordt één keer gezocht bij het opstarten.

## Kraken LCD

- Blijft het scherm zwart of raar? Zet "Beeldformaat" op `rgb565`.
- Bij afsluiten gaat het scherm terug naar het standaard NZXT-vloeistofscherm.
- Het LCD streamt live; er wordt niets naar het flashgeheugen van de Kraken geschreven.

## Let op

- MSI-kleuren worden alleen in RAM gezet (niet opgeslagen in het BIOS), net als OpenRGB doet.
- Protocollen komen uit de SignalRGB-plugins op je pc en uit OpenRGB/liquidctl.
