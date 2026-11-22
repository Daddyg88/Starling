@echo off
rem Makes her voice run on your NVIDIA graphics card instead of the processor (about ten times faster: her sentences start almost at once).
rem Source install only (needs the .venv folder that setup.bat makes). Needs about 3 GB of disk and an internet connection. Safe: if the
rem graphics-card version does not work on this PC, the original one is put back and nothing changes.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo This needs the full source install: run setup.bat first, it makes the .venv folder this uses.
  pause
  exit /b 1
)
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
.venv\Scripts\python.exe -c "import torch; print('  torch', torch.__version__, '- graphics card usable:', torch.cuda.is_available())"
.venv\Scripts\python.exe -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)"
if not errorlevel 1 (
  echo.
  echo It already uses the graphics card. Nothing to do.
  pause
  exit /b 0
)
for %%V in (cu126 cu124 cu128 cu118) do call :try %%V
echo.
echo None of the graphics-card versions worked on this PC, so I am putting the original one back.
.venv\Scripts\python.exe -m pip install --force-reinstall --no-deps torch --index-url https://download.pytorch.org/whl/cpu
echo.
echo Her voice still works exactly as before ^(on the processor^). Tell Ben what this window said.
pause
exit /b 1

:try
echo.
echo ---- Trying the %1 version ^(about 2.5 GB, please wait^) ----
.venv\Scripts\python.exe -m pip install --force-reinstall --no-deps torch --index-url https://download.pytorch.org/whl/%1
if errorlevel 1 goto :eof
.venv\Scripts\python.exe -c "import torch,sys; print('  torch', torch.__version__, '- graphics card usable:', torch.cuda.is_available()); sys.exit(0 if torch.cuda.is_available() else 1)"
if errorlevel 1 goto :eof
echo.
echo ===== It worked. Start Starling: her voice now runs on your graphics card. =====
echo The log will say "Voice engine is running on: cuda".
pause
exit /b 0
