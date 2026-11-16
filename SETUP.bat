@echo off
title Smart Home Monitor - one-time setup
cd /d "%~dp0"

echo ============================================================
echo   Smart Home Monitor - one-time setup (needs internet)
echo ============================================================
echo.

rem Find Python: the "py" launcher first (python.org installs it), then "python"
set PY=
py -3 --version >nul 2>&1 && set PY=py -3
if not defined PY python --version >nul 2>&1 && set PY=python
if not defined PY (
  echo Python was not found.
  echo Install it from https://www.python.org/downloads/
  echo and tick "Add Python to PATH" during installation. Then run SETUP.bat again.
  echo.
  pause
  exit /b 1
)
echo Using:
%PY% --version
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [1/2] Creating a private Python environment in .venv ...
  %PY% -m venv .venv
  if errorlevel 1 goto failed
) else (
  echo [1/2] .venv already exists, reusing it.
)

echo [2/2] Installing packages - this can take a few minutes ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r backend\requirements.txt
if errorlevel 1 goto failed

echo.
echo ============================================================
echo   Setup finished. From now on, just double-click START_DEMO.bat
echo ============================================================
pause
exit /b 0

:failed
echo.
echo Setup FAILED. Check the internet connection and run SETUP.bat again.
echo If it keeps failing, send a screenshot of this window.
pause
exit /b 1
