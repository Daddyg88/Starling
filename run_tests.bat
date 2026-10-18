@echo off
rem Double-click this file to check that everything in STARLING works.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m unittest discover -s tests -t . -v
echo.
pause
