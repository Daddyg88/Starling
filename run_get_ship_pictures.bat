@echo off
rem Double-click to download the ship pictures from the Elite Dangerous wiki (needs internet).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" tools\get_ship_pictures.py
pause
