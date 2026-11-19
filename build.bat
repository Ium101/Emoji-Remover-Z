@echo off
cd /d "%~dp0"
echo ====================================================
echo   Emoji Remover Z - Setup Script
echo ====================================================
echo.
echo   Runs straight from emoji-remover-z.py - no .exe is built.
echo.

py -3.14 --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.14 not found via py launcher.
    echo Make sure Python 3.14 is installed from python.org
    pause
    exit /b 1
)

echo [1/4] Using Python 3.14...
py -3.14 --version
echo.

echo [2/4] Generating icon...

py -3.14 -m pip install --quiet Pillow
if errorlevel 1 (
    echo ERROR: Could not install Pillow for icon generation.
    pause
    exit /b 1
)

rem The PNG stays next to the script (the app uses it as its window icon).
rem Windows shortcuts cannot use a .png as their icon (only .ico/.exe/.dll),
rem so the .ico is generated into a separate per-user folder, just for the
rem shortcuts, and nothing but the .png is left in the program folder.
set "ERZ_ICODIR=%LOCALAPPDATA%\Emoji Remover Z"
if not exist "%ERZ_ICODIR%" mkdir "%ERZ_ICODIR%"

pushd "%ERZ_ICODIR%"
py -3.14 "%~dp0emoji-remover-z.py" --generate-icon
set "ERZ_ICON_RC=%errorlevel%"
popd

if not "%ERZ_ICON_RC%"=="0" (
    echo ERROR: Could not generate icon.
    pause
    exit /b 1
)
if not exist "%ERZ_ICODIR%\emoji_remover_z.ico" (
    echo ERROR: Icon file was not created.
    pause
    exit /b 1
)
copy /y "%ERZ_ICODIR%\emoji_remover_z.png" "%~dp0emoji_remover_z.png" >nul
del /q "%ERZ_ICODIR%\emoji_remover_z.png" >nul 2>&1
if not exist "%~dp0emoji_remover_z.png" (
    echo ERROR: PNG icon was not created.
    pause
    exit /b 1
)
echo   Icon (app window):  %~dp0emoji_remover_z.png
echo   Icon (shortcuts):   %ERZ_ICODIR%\emoji_remover_z.ico
echo.

echo [3/4] Removing old compiled build (if any)...
rem Earlier versions of this script produced a PyInstaller .exe here.
rem Delete any leftovers so nothing stale is left to point at.
if exist "%~dp0Emoji_Remover_Z.exe" del /q "%~dp0Emoji_Remover_Z.exe" >nul 2>&1
if exist "%~dp0build" rmdir /s /q "%~dp0build" >nul 2>&1
if exist "%~dp0Emoji_Remover_Z.spec" del /q "%~dp0Emoji_Remover_Z.spec" >nul 2>&1
if exist "%~dp0emoji_remover_z.ico" del /q "%~dp0emoji_remover_z.ico" >nul 2>&1
echo.

echo [4/4] Creating Desktop and Start Menu shortcuts...

rem Find pythonw.exe (runs the .py without a console window) from Python 3.14.
set "ERZ_PYEXE="
for /f "delims=" %%i in ('py -3.14 -c "import sys;print(sys.executable)"') do set "ERZ_PYEXE=%%i"
set "ERZ_PYW=%ERZ_PYEXE:python.exe=pythonw.exe%"
if not exist "%ERZ_PYW%" set "ERZ_PYW=%ERZ_PYEXE%"

set "ERZ_PY=%~dp0emoji-remover-z.py"
set "ERZ_ICO=%ERZ_ICODIR%\emoji_remover_z.ico"
set "ERZ_DIR=%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$q=[char]34;" ^
  "$s=New-Object -ComObject WScript.Shell;" ^
  "$d=$s.CreateShortcut([IO.Path]::Combine($env:USERPROFILE,'Desktop','Emoji Remover Z.lnk'));" ^
  "$d.TargetPath=$env:ERZ_PYW;$d.Arguments=$q+$env:ERZ_PY+$q;$d.WorkingDirectory=$env:ERZ_DIR;$d.Description='Remove emojis and styled text from filenames and folders';$d.IconLocation=$env:ERZ_ICO+',0';$d.Save();" ^
  "$m=[IO.Path]::Combine($env:APPDATA,'Microsoft','Windows','Start Menu','Programs','Emoji Remover Z.lnk');" ^
  "$sm=$s.CreateShortcut($m);" ^
  "$sm.TargetPath=$env:ERZ_PYW;$sm.Arguments=$q+$env:ERZ_PY+$q;$sm.WorkingDirectory=$env:ERZ_DIR;$sm.Description='Remove emojis and styled text from filenames and folders';$sm.IconLocation=$env:ERZ_ICO+',0';$sm.Save()"

if errorlevel 1 (
    echo WARNING: Could not create shortcuts.
) else (
    echo   Desktop shortcut:    %USERPROFILE%\Desktop\Emoji Remover Z.lnk
    echo   Start Menu shortcut: %APPDATA%\Microsoft\Windows\Start Menu\Programs\Emoji Remover Z.lnk
    echo   Runs:                %ERZ_PYW% "%ERZ_PY%"
)

echo.
echo Done!
echo.
echo No executable was built - both shortcuts run emoji-remover-z.py directly.
echo Keep emoji_remover_z.png next to the script (the app window icon).
echo.
pause
