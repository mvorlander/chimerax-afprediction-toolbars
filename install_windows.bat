@echo off
setlocal
cd /d "%~dp0"

echo ChimeraX AF Prediction Toolbars installer
echo Folder: %CD%
echo.

set "PYTHON_CMD="
where py >nul 2>nul
if %ERRORLEVEL%==0 set "PYTHON_CMD=py -3"

if not defined PYTHON_CMD (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    where python3 >nul 2>nul
    if %ERRORLEVEL%==0 set "PYTHON_CMD=python3"
)

if not defined PYTHON_CMD (
    echo Could not find Python.
    echo.
    echo Install Python 3 from https://www.python.org/downloads/windows/
    echo and tick "Add python.exe to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo Using Python:
%PYTHON_CMD% --version
echo.

%PYTHON_CMD% install_chimerax_bundle.py
set "STATUS=%ERRORLEVEL%"

echo.
if "%STATUS%"=="0" (
    echo Install finished.
    echo Restart ChimeraX, then open the AF toolbar tab.
) else (
    echo Install failed.
    echo If ChimeraX was not found automatically, run from PowerShell:
    echo py install_chimerax_bundle.py --chimerax "C:\Path\To\ChimeraX.exe"
)
echo.
pause
exit /b %STATUS%
