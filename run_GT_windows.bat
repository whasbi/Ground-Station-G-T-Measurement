@echo off
setlocal
cd /d "%~dp0"
echo Starting Ground Station G/T Measurement Software...
py GT.py
if errorlevel 1 (
    echo.
    echo If Python is not installed, install it from https://www.python.org/downloads/windows/
    echo Make sure to tick "Add python.exe to PATH" during installation.
    echo.
    pause
)
