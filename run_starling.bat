@echo off
rem Double-click this file to start STARLING and watch Elite Dangerous.
rem Press Ctrl+C in the window to stop her.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py
echo.
pause
