@echo off
set PROFILE_DIR=%LOCALAPPDATA%\NetSuiteAutomationProfile
if not exist "%PROFILE_DIR%" mkdir "%PROFILE_DIR%"

where chrome >nul 2>nul
if %ERRORLEVEL%==0 (
    start "" chrome --remote-debugging-port=9222 --user-data-dir="%PROFILE_DIR%" "https://3559546.app.netsuite.com"
) else (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%PROFILE_DIR%" "https://3559546.app.netsuite.com"
)
