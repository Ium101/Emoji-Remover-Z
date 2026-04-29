@echo off
echo ====================================================
echo   Emoji Remover Z - Build Script
echo ====================================================
echo.

REM Try py launcher with Python 3.14 explicitly
py -3.14 --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.14 not found via py launcher.
    echo Make sure Python 3.14 is installed from python.org
    pause
    exit /b 1
)

echo [1/3] Using Python 3.14...
py -3.14 --version
echo.

echo [2/3] Installing PyInstaller for Python 3.14...
py -3.14 -m pip install pyinstaller --quiet
if errorlevel 1 (
    echo ERROR: Could not install PyInstaller.
    pause
    exit /b 1
)

echo [3/3] Building executable...
py -3.14 -m PyInstaller --onefile --windowed --name "EmojiRemoverZ" emoji-remover-z.py

if errorlevel 1 (
    echo ERROR: Build failed. See above for details.
    pause
    exit /b 1
)

echo.
echo Done!
echo.
echo Your executable is at:  dist\EmojiRemoverZ.exe
echo.
pause
