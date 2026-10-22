@echo off
REM ===== J.A.R.V.I.S -> JARVIS.exe =====
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :fail

python -m PyInstaller --noconfirm --clean --windowed --name JARVIS ^
  --icon assets\jarvis.ico ^
  --add-data "assets;assets" ^
  --collect-all _sounddevice_data ^
  --collect-all miniaudio ^
  --collect-all soundfile ^
  --collect-all _soundfile_data ^
  --collect-data speech_recognition ^
  --collect-all edge_tts ^
  --collect-data certifi ^
  --collect-submodules keyring ^
  --hidden-import keyring.backends.Windows ^
  --hidden-import pyttsx3.drivers ^
  --hidden-import pyttsx3.drivers.sapi5 ^
  --hidden-import send2trash.win ^
  main.py
if errorlevel 1 goto :fail

echo.
echo Fertig:  dist\JARVIS\JARVIS.exe
echo (Daten, Logs und Einstellungen liegen weiterhin in C:\jarvis)
pause
exit /b 0

:fail
echo.
echo BUILD FEHLGESCHLAGEN - siehe Meldungen oben.
pause
exit /b 1
