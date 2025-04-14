@echo off
setlocal enabledelayedexpansion

REM Set up a Python virtual environment and run video_cropper.py

REM Variables
set "PYTHON_SCRIPT=main.py"
set "VENV_DIR=venv"
set "SCRIPT_DIR=%~dp0"
set "FAST_START=FALSE"

REM Navigate to the script directory
cd /d "%SCRIPT_DIR%" || (
    echo Failed to set current directory.
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist "%VENV_DIR%" (
    echo Creating virtual environment...
    python -m venv "%VENV_DIR%"
)

REM Activate virtual environment
call "%VENV_DIR%\Scripts\activate.bat" || (
    echo Failed to activate virtual environment.
    pause
    exit /b 1
)

REM Always install/update dependencies to ensure consistency
echo Checking/Installing dependencies...
pip install -r requirements.txt --upgrade

REM Run the Python script
echo Starting %PYTHON_SCRIPT%...
python "%PYTHON_SCRIPT%"

REM Deactivate virtual environment
deactivate

pause
