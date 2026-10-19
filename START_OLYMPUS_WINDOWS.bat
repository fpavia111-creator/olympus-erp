@echo off
setlocal
cd /d "%~dp0"
echo.
echo =====================================
echo       OLYMPUS ERP LOCAL v0.4
echo =====================================
echo.
echo Single-user local prototype - not a hosted ERP and no production integrations.
where py >nul 2>&1
if errorlevel 1 (
  echo Python launcher not found. Install Python 3.11 or newer and read README.md.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
  if errorlevel 1 (echo Python 3.11 or newer is required. & pause & exit /b 1)
  py -3 -m venv .venv
  if errorlevel 1 (echo Could not create the virtual environment. & pause & exit /b 1)
)
echo Installing local Olympus application...
".venv\Scripts\python.exe" -m pip install -e ".[pdf]"
if errorlevel 1 (echo Setup failed. Check network and permissions. & pause & exit /b 1)
echo.
echo Local page: http://127.0.0.1:8765
echo Keep this window open. Press Ctrl+C to stop the app.
start "" "http://127.0.0.1:8765"
".venv\Scripts\olympus-web.exe" --workspace . --port 8765
pause
