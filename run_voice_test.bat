@echo off
rem Double-click to test STARLING's voice. You should hear two short tests.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py --voice-test
echo.
pause
