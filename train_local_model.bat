@echo off
rem Trains the local answer model, tests it and writes the report.
rem Plug the laptop in first: training is 1-2 hours of CPU work. If it is interrupted,
rem run this file again and it continues from the last finished epoch.
cd /d "%~dp0"
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set PY=".venv\Scripts\python.exe"

if not exist %PY% (
    echo Run run.bat once first to set the project up.
    goto :error
)
%PY% -c "import torch, transformers" 2>nul
if errorlevel 1 (
    echo Installing the model runtime. This downloads about 300 MB...
    %PY% -m pip install --disable-pip-version-check torch --index-url https://download.pytorch.org/whl/cpu || goto :error
    %PY% -m pip install --disable-pip-version-check -r requirements-model.txt || goto :error
)

echo.
echo [1/4] Building the training set
%PY% -m training.data || goto :error
echo.
echo [2/4] Training (the slow step)
%PY% -m training.train --resume --threads 4 || goto :error
echo.
echo [3/4] Testing the model
%PY% -m training.test_model || goto :error
echo.
echo [4/4] Writing the report
%PY% -m training.report || goto :error
echo.
echo Done. The report is in the report folder: Local_Model_Training_and_Testing_Report.docx
echo Restart run.bat and choose "Local model" under "Answer by".
pause
goto :eof

:error
echo.
echo Something failed. The message above says what.
pause
