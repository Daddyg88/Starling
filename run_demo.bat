@echo off
rem Double-click this file to watch STARLING react to a pretend play session.
rem You do NOT need Elite Dangerous running for this.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py --demo
echo.
pause
