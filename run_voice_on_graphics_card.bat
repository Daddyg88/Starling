@echo off
rem Makes her voice run on your NVIDIA graphics card instead of the processor (about ten times faster: her sentences start almost at once).
rem Works for the installed Starling (the .venv folder sits one level up) and for a source install (.venv next to this file). Needs about 3 GB of disk and an internet connection. Safe: if the
rem graphics-card version does not work on this PC, the original one is put back and nothing changes.
cd /d "%~dp0"
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"
if not defined PY (
  echo I could not find Starling's Python ^(the .venv folder^).
  echo Looked in: %CD%\.venv  and  %CD%\..\.venv
  echo Take a photo of this window and show Ben.
  pause
  exit /b 1
)
echo Using Starling's Python: %PY%
echo.
echo Close Starling before you go on. Press any key to start.
pause >nul
echo.
echo Checking for an NVIDIA graphics card...
nvidia-smi >nul 2>&1
if errorlevel 1 (
  echo.
  echo I could not find an NVIDIA graphics card driver ^(nvidia-smi did not run^).
  echo This only helps PCs with an NVIDIA card. If you have one, update its driver from nvidia.com and run this again.
  pause
  exit /b 1
)
echo Found it.
echo.
echo What her voice runs on now:
%PY% -c "import torch; print('  torch', torch.__version__, '- graphics card usable:', torch.cuda.is_available())"
%PY% -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)"
if not errorlevel 1 (
  echo.
  echo It already uses the graphics card. Nothing to do.
  pause
  exit /b 0
)
set "DONE="
for %%V in (cu126 cu124 cu128 cu118) do if not defined DONE call :try %%V
if defined DONE (
  echo.
  echo ===== It worked. Start Starling: her voice now runs on your graphics card. =====
  echo The log will say "Voice engine is running on: cuda".
  pause
  exit /b 0
)
echo.
echo None of the graphics-card versions worked on this PC, so I am putting the original one back.
%PY% -m pip install --force-reinstall --no-deps torch --index-url https://download.pytorch.org/whl/cpu
echo.
echo Her voice still works exactly as before ^(on the processor^). Tell Ben what this window said.
pause
exit /b 1

:try
echo.
echo ---- Trying the %1 version ^(about 2.5 GB, please wait^) ----
%PY% -m pip install --force-reinstall --no-deps torch --index-url https://download.pytorch.org/whl/%1
if errorlevel 1 goto :eof
%PY% -c "import torch,sys; print('  torch', torch.__version__, '- graphics card usable:', torch.cuda.is_available()); sys.exit(0 if torch.cuda.is_available() else 1)"
if errorlevel 1 goto :eof
set "DONE=1"
goto :eof
