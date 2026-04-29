@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo Building GT.exe for Windows using PyInstaller
echo ============================================================
echo.

echo Installing project dependencies...
py -m pip install -r requirements.txt
if errorlevel 1 goto error

echo.
echo Installing PyInstaller...
py -m pip install pyinstaller
if errorlevel 1 goto error

echo.
echo Building executable...
py -m PyInstaller --onefile --windowed --name GT GT.py
if errorlevel 1 goto error

echo.
echo Build complete.
echo Your executable is here:
echo dist\GT.exe
echo.
echo You may copy dist\GT.exe to another Windows computer.
echo Automatic NOAA/RSTN mode still requires internet access.
echo.
pause
exit /b 0

:error
echo.
echo Build failed. Check the error message above.
echo Common fixes:
echo - Install Python from https://www.python.org/downloads/windows/
echo - Tick "Add python.exe to PATH"
echo - Run this file from the project folder
echo - Check your internet connection for dependency installation
echo.
pause
exit /b 1
