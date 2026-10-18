@echo off
rem Double-click to check your Elite keys, your joystick, and what STARLING would do with a sentence (presses nothing).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py --controls-test
echo.
pause
