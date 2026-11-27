@echo off
rem Starts Uni Help and opens it in the browser.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up for the first time. This takes a few minutes...
    python -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt || goto :error
)

echo.
echo Uni Help is starting at http://127.0.0.1:8000
echo Keep this window open. Press Ctrl+C to stop.
echo.
start "" http://127.0.0.1:8000
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
goto :eof

:error
echo.
echo Setup failed. Check that Python 3.10 or newer is installed and you are online.
pause
