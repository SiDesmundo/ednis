@echo off
REM Start the EDNIS control panel. Run install.bat once first, and make sure
REM launch_chrome_debug.bat is running with NetSuite + eDesk logged in.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment missing. Run install.bat first.
    exit /b 1
)

".venv\Scripts\python.exe" command_center.py
endlocal
