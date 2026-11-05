@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe main.py
type "%APPDATA%\LiteRGB\litergb.log"
pause
