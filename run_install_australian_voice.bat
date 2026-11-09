@echo off
rem OPTIONAL: installs the Australian voice for Starling without opening the dashboard. Same as the "Install Australian voice" button
rem on the Voice page. It uses its own private folder (data\melo_env), so it cannot break Starling. Delete that folder to remove it.
cd /d "%~dp0"
set PY=python
if exist ..\.venv\Scripts\python.exe set PY=..\.venv\Scripts\python.exe
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
%PY% -c "from tts import melo_install; ok, msg = melo_install.install(); print(msg); raise SystemExit(0 if ok else 1)"
pause
