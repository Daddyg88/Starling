@echo off
rem OPTIONAL TEST (for testers): tries the Australian voice (MeloTTS) in its OWN private folder, so it cannot touch or break Starling.
rem It makes australian_test\ next to this file, installs MeloTTS there (a few GB and 10+ minutes the first time, needs the internet),
rem then makes australian_sample.wav. Play that file to hear the voice, and send the file australian_test\log.txt back.
cd /d "%~dp0"
set LOG=australian_test\log.txt
if not exist australian_test mkdir australian_test
echo Trying the Australian voice. Everything is logged to %LOG%
set PYV=3.11
py -%PYV% --version >nul 2>&1
if errorlevel 1 set PYV=3.10
py -%PYV% --version >nul 2>&1
if errorlevel 1 set PYV=3.12
echo Using Python %PYV% > %LOG%
if not exist australian_test\venv\Scripts\python.exe py -%PYV% -m venv australian_test\venv >> %LOG% 2>&1
australian_test\venv\Scripts\python.exe -m pip install --upgrade pip >> %LOG% 2>&1
echo Step 1 of 3: installing MeloTTS (this is the long one)...
australian_test\venv\Scripts\python.exe -m pip install https://github.com/myshell-ai/MeloTTS/archive/refs/heads/main.zip >> %LOG% 2>&1
if errorlevel 1 goto failed
echo Step 2 of 3: language data...
australian_test\venv\Scripts\python.exe -m unidic download >> %LOG% 2>&1
echo Step 3 of 3: making a sample sentence...
australian_test\venv\Scripts\python.exe tools\try_melo.py >> %LOG% 2>&1
if errorlevel 1 goto failed
echo.
echo It worked. Play australian_sample.wav. Then send australian_test\log.txt back.
pause
exit /b 0
:failed
echo.
echo It did not work. That is fine, nothing in Starling was changed. Send australian_test\log.txt back.
pause
exit /b 1
