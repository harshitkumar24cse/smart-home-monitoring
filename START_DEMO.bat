@echo off
title Smart Home Monitor - backend (keep this window open)
cd /d "%~dp0backend"

if not exist "..\.venv\Scripts\python.exe" (
  echo Setup has not been done on this computer yet.
  echo Double-click SETUP.bat first ^(once^), then START_DEMO.bat again.
  pause
  exit /b 1
)

echo ============================================================
echo   Smart Home Monitor
echo ============================================================
echo.
choice /c YN /m "Start with empty data (delete old readings and alerts)"
if errorlevel 2 goto start
if exist smarthome.db del smarthome.db
if exist smarthome.db (
  echo.
  echo Could not delete old data - is another backend window still open? Close it and try again.
  pause
  exit /b
)
echo Old data deleted.

:start
echo.
echo To open the dashboard on your PHONE, type this in the phone's browser:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do for /f "tokens=*" %%b in ("%%a") do echo     http://%%b:8000
echo   (phone and laptop must be on the same Wi-Fi or hotspot;
echo    if more than one address is shown, try the one starting 192.168 or 172.20)
echo.
echo The dashboard will open in your browser in a few seconds.
echo KEEP THIS WINDOW OPEN. Closing it stops the app.
echo ============================================================
echo.

start "" cmd /c "timeout /t 5 >nul & start http://127.0.0.1:8000"
"..\.venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
echo.
echo The backend stopped. If you see "address already in use", another backend window is still open.
pause
