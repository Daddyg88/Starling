@echo off
rem ----------------------------------------------------------
rem STARLING setup. Double-click this file ONE time.
rem It creates a private Python environment just for STARLING
rem using Python 3.12, then installs the add-ons STARLING needs.
rem ----------------------------------------------------------
cd /d "%~dp0"

echo Creating STARLING's private Python environment...
py -3.12 -m venv .venv
if errorlevel 1 goto nopython

echo Installing add-ons...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pipfail

echo.
echo Setup finished. Now double-click run_starling.bat
pause
exit /b 0

:nopython
echo.
echo Could not find Python 3.12.
echo Open Command Prompt and type:  py -3.12 --version
echo See docs\TROUBLESHOOTING.md for help.
pause
exit /b 1

:pipfail
echo.
echo The add-ons did not install. Check your internet connection and try again.
pause
exit /b 1
