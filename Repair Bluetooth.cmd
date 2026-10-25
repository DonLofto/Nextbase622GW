@echo off
setlocal
rem Run as administrator for the read-only disk check and safe card ejection.
py -3 -c "import sys; sys.exit(sys.version_info < (3,9))" >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0persistent-repair\repair.py" %*
) else (
    python -c "import sys; sys.exit(sys.version_info < (3,9))" >nul 2>&1
    if errorlevel 1 (
        echo Python 3.9 or newer is required. Install Python, then reopen this file.
        exit /b 1
    )
    python "%~dp0persistent-repair\repair.py" %*
)
set "task_result=%errorlevel%"
if not defined NB_REPAIR_NO_PAUSE pause
exit /b %task_result%
