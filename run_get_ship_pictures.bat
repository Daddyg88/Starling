@echo off
rem Double-click to download the ship pictures from the Elite Dangerous wiki (needs internet).
rem Easier: open the dashboard Home page and press "Get ship pictures" on the Ship status card.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" tools\get_ship_pictures.py
) else if exist "..\.venv\Scripts\python.exe" (
    "..\.venv\Scripts\python.exe" tools\get_ship_pictures.py
) else (
    python tools\get_ship_pictures.py
)
pause
