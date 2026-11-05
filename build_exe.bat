@echo off
cd /d "%~dp0"
.venv\Scripts\python -m pip install pyinstaller
.venv\Scripts\pyinstaller --noconfirm --onefile --noconsole --name LiteRGB --collect-all libusb_package --add-data "lib;lib" main.py
echo.
echo Klaar: dist\LiteRGB.exe
pause
