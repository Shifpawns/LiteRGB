@echo off
cd /d "%~dp0"
py -3 -m venv .venv || python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
echo.
echo Klaar. Start LiteRGB met start.bat
pause
