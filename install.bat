@echo off
REM One-time setup: install Python if missing, create the virtual environment,
REM install dependencies. Also checks that Chrome is present.
setlocal
cd /d "%~dp0"

REM --- Python -------------------------------------------------------------
set PY=
where py >nul 2>nul && set PY=py
if not defined PY ( where python >nul 2>nul && set PY=python )

if not defined PY (
    echo Python not found.
    where winget >nul 2>nul
    if %ERRORLEVEL%==0 (
        echo Installing Python 3.12 via winget...
        winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
        echo.
        echo Python installed. CLOSE this window, open a new one, and run install.bat again
        echo so the updated PATH takes effect.
        exit /b 0
    ) else (
        echo winget is not available. Install Python 3.10+ manually from:
        echo     https://www.python.org/downloads/windows/
        echo Tick "Add python.exe to PATH" in the installer, then run install.bat again.
        exit /b 1
    )
)

echo Using Python: %PY%
%PY% --version

REM --- Chrome (needed at runtime, not for install) ----------------------
where chrome >nul 2>nul
if not %ERRORLEVEL%==0 (
    if not exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
        echo.
        echo WARNING: Google Chrome was not found. The app needs it at runtime.
        where winget >nul 2>nul && echo Install it with:  winget install --id Google.Chrome -e
        echo Or download from: https://www.google.com/chrome/
        echo.
    )
)

REM --- venv + dependencies ---------------------------------------------
if not exist ".venv" (
    echo Creating virtual environment...
    %PY% -m venv .venv
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo Done. Next:
echo   1. Run launch_chrome_debug.bat and log into NetSuite + eDesk
echo   2. Run run.bat to start the app
endlocal
