@echo off
rem  Build a standalone single-file Windows exe (no Python needed on the target PC).
rem  Output: dist\KeyPresser.exe
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto :nopython

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating virtual environment ...
    python -m venv .venv || goto :fail
)

echo [2/3] Installing PyInstaller ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pyinstaller || goto :fail

echo [3/3] Building ...
".venv\Scripts\python.exe" -c "import sys,os,pathlib;pathlib.Path('tcl_path.txt').write_text(os.path.join(sys.base_prefix,'tcl'),encoding='utf-8')" || goto :fail
set /p TCLDIR=<tcl_path.txt
del /q tcl_path.txt
if not exist "%TCLDIR%" goto :fail

".venv\Scripts\pyinstaller.exe" --noconfirm --clean --onefile --windowed --name KeyPresser ^
  --icon "assets\icon.ico" ^
  --add-data "assets;assets" ^
  --add-data "sounds;sounds" ^
  --add-data "themes.json;." ^
  --add-data "tts_synth.ps1;." ^
  --add-data "%TCLDIR%;tcl" ^
  main.py || goto :fail

echo.
echo Done:  dist\KeyPresser.exe
echo.
pause
exit /b 0

:nopython
echo   [ERROR] Python not found. Install Python 3.8+ (tick "Add python.exe to PATH").
pause
exit /b 1

:fail
echo.
echo   Build failed.
pause
exit /b 1
