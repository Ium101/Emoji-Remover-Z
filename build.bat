@echo off
cd /d "%~dp0"
echo ====================================================
echo   Emoji Remover Z - Build Script
echo ====================================================
echo.

py -3.14 --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.14 not found via py launcher.
    echo Make sure Python 3.14 is installed from python.org
    pause
    exit /b 1
)

echo [1/5] Using Python 3.14...
py -3.14 --version
echo.

echo [2/5] Generating icon...

py -3.14 -m pip install --quiet Pillow
if errorlevel 1 (
    echo ERROR: Could not install Pillow for icon generation.
    pause
    exit /b 1
)

py -3.14 "emoji-remover-z.py" --generate-icon
if errorlevel 1 (
    echo ERROR: Could not generate icon.
    pause
    exit /b 1
)

if not exist "%~dp0emoji_remover_z.ico" (
    echo ERROR: Icon file was not created.
    pause
    exit /b 1
)

echo.

echo [3/5] Installing PyInstaller for Python 3.14...
py -3.14 -m pip install pyinstaller --quiet
if errorlevel 1 (
    echo ERROR: Could not install PyInstaller.
    pause
    exit /b 1
)

echo [4/5] Building executable...

rem Wipe any previous build/spec cache so PyInstaller can never reuse a
rem stale .spec file that points at a since-deleted or relocated icon path.
if exist "build" rmdir /s /q "build" >nul 2>&1

py -3.14 -m PyInstaller --onefile --windowed --name "Emoji_Remover_Z" ^
    --icon "%~dp0emoji_remover_z.ico" ^
    --distpath . --workpath build --specpath build ^
    --noconfirm ^
    "emoji-remover-z.py"

if errorlevel 1 (
    echo ERROR: Build failed. See above for details.
    del /q emoji_remover_z.ico >nul 2>&1
    del /q emoji_remover_z.png >nul 2>&1
    pause
    exit /b 1
)

echo.
echo Cleaning up build files...
rmdir /s /q build >nul 2>&1
del /q emoji_remover_z.ico >nul 2>&1
del /q emoji_remover_z.png >nul 2>&1

echo.
echo [5/5] Creating Desktop and Start Menu shortcuts...

set "ERZ_EXE=%~dp0Emoji_Remover_Z.exe"
set "ERZ_DIR=%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=New-Object -ComObject WScript.Shell;" ^
  "$d=$s.CreateShortcut([IO.Path]::Combine($env:USERPROFILE,'Desktop','Emoji Remover Z.lnk'));" ^
  "$d.TargetPath=$env:ERZ_EXE;$d.WorkingDirectory=$env:ERZ_DIR;$d.Description='Remove emojis and styled text from filenames and folders';$d.IconLocation=$env:ERZ_EXE+',0';$d.Save();" ^
  "$m=[IO.Path]::Combine($env:APPDATA,'Microsoft','Windows','Start Menu','Programs','Emoji Remover Z.lnk');" ^
  "$sm=$s.CreateShortcut($m);" ^
  "$sm.TargetPath=$env:ERZ_EXE;$sm.WorkingDirectory=$env:ERZ_DIR;$sm.Description='Remove emojis and styled text from filenames and folders';$sm.IconLocation=$env:ERZ_EXE+',0';$sm.Save()"

if errorlevel 1 (
    echo WARNING: Could not create shortcuts.
) else (
    echo   Desktop shortcut:    %USERPROFILE%\Desktop\Emoji Remover Z.lnk
    echo   Start Menu shortcut: %APPDATA%\Microsoft\Windows\Start Menu\Programs\Emoji Remover Z.lnk
)

echo.
echo Done!
echo.
echo Your executable is at:  %~dp0Emoji_Remover_Z.exe
echo.
pause
