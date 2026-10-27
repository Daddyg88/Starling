@echo off
rem Optional: installs the small AI chat model for open conversation. Needs about 400 MB of disk and an internet connection.
rem Run this once, then turn on "Small AI model for open chat" in Starling's Personality settings.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Please run setup.bat first.
  pause
  exit /b 1
)
echo Step 1 of 2: installing the add-on that runs the model...
.venv\Scripts\python.exe -m pip install llama-cpp-python --only-binary :all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
if errorlevel 1 (
  echo.
  echo The add-on could not be installed. Starling still works exactly as before, just without the AI chat.
  pause
  exit /b 1
)
echo.
echo Step 2 of 2: downloading the model (about 400 MB)...
.venv\Scripts\python.exe -m core.model_download
echo.
echo Finished. Close Starling, open it again, and switch on "Small AI model for open chat" in the Personality settings.
pause
