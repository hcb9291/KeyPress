@echo off
rem  Double-click to run the app (needs Python 3.8+).
rem  For a standalone exe that needs no Python, use build.bat instead.
cd /d "%~dp0"

if not exist "main.py" goto :missing

where pythonw >nul 2>nul
if not errorlevel 1 goto :pyw
where python >nul 2>nul
if not errorlevel 1 goto :py
goto :nopython

:pyw
start "" pythonw "main.py"
exit /b 0

:py
start "" python "main.py"
exit /b 0

:missing
echo   [ERROR] main.py not found.
pause
exit /b 1

:nopython
echo   [ERROR] Python was not found. Install Python 3.8+ first,
echo   or use the prebuilt exe from the Releases page.
pause
exit /b 1
