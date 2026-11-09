@echo off
rem OPTIONAL TEST (for testers): tries the Australian voice (MeloTTS) in its OWN private folder, so it cannot touch or break Starling.
rem It makes australian_test\ next to this file, installs MeloTTS there (a few GB and 10+ minutes the first time, needs the internet),
rem then makes australian_sample.wav. Play that file to hear the voice, and send the file australian_test\log.txt back.
rem Version 2 (0.89.5): the first try failed because MeloTTS asks for OLD versions of two add-ons that must be compiled (fugashi, tokenizers),
rem which needs Visual C++ and Rust. This version installs MeloTTS WITHOUT its old pins and uses modern add-ons that come ready-made.
cd /d "%~dp0"
set LOG=australian_test\log.txt
if not exist australian_test mkdir australian_test
echo Trying the Australian voice. Everything is logged to %LOG%
set PYV=3.12
echo Using Python %PYV% > %LOG%
if not exist australian_test\venv\Scripts\python.exe py -%PYV% -m venv australian_test\venv >> %LOG% 2>&1
set PY=australian_test\venv\Scripts\python.exe
%PY% -m pip install --upgrade pip >> %LOG% 2>&1
echo Step 1 of 5: installing the sound maths library (torch)...
%PY% -m pip install torch torchaudio >> %LOG% 2>&1
if errorlevel 1 goto failed
echo Step 2 of 5: installing MeloTTS itself (without its old version pins)...
%PY% -m pip install --no-deps https://github.com/myshell-ai/MeloTTS/archive/refs/heads/main.zip >> %LOG% 2>&1
if errorlevel 1 goto failed
echo Step 3 of 5: installing the add-ons it needs (modern versions)...
%PY% -m pip install --only-binary fugashi,tokenizers,mecab-python3,safetensors,numpy,scipy,numba,llvmlite,scikit-learn,python-crfsuite,regex txtsplit cached_path transformers num2words unidic_lite unidic mecab-python3 pykakasi fugashi g2p_en anyascii jamo "gruut[de,es,fr]" g2pkk librosa pydub eng_to_ipa inflect unidecode pypinyin cn2an jieba langid tqdm loguru numpy scipy soundfile nltk huggingface-hub >> %LOG% 2>&1
if errorlevel 1 goto failed
echo Step 4 of 5: language data (can take a few minutes)...
%PY% -m unidic download >> %LOG% 2>&1
echo Step 5 of 5: making a sample sentence...
%PY% tools\try_melo.py >> %LOG% 2>&1
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
