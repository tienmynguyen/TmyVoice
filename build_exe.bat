@echo off
setlocal enabledelayedexpansion
title Building SoundboardPro Windows Executable...

echo ======================================================================
echo           SoundboardPro / TmyVoice - PyInstaller Build Script
echo ======================================================================
echo.

:: 1. Verify Python availability
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not found in your system PATH!
    echo Please install Python 3.10+ and check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

echo [1/4] Checking Python environment...
python --version

:: 2. Ensure PyInstaller is installed and up-to-date
echo.
echo [2/4] Ensuring PyInstaller is installed...
python -m pip install --upgrade pyinstaller

:: 3. Clean previous build artifacts
echo.
echo [3/4] Cleaning previous build artifacts...
if exist "build" (
    echo Removing old build directory...
    rmdir /s /q "build"
)
if exist "dist\SoundboardPro" (
    echo Removing old dist\SoundboardPro directory...
    rmdir /s /q "dist\SoundboardPro"
)

:: 4. Run PyInstaller Compilation
echo.
echo [4/4] Compiling SoundboardPro executable with PyInstaller...
echo       - Mode: --onedir, --windowed
echo       - Privileges: --uac-admin (for global hotkeys in full-screen games)
echo       - Collecting: customtkinter, sounddevice, soundfile, scipy, keyboard, pynput
echo       - Bundling: assets/
echo.

python -m PyInstaller ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --uac-admin ^
    --name "SoundboardPro" ^
    --clean ^
    --add-data "assets;assets" ^
    --collect-all "customtkinter" ^
    --collect-all "sounddevice" ^
    --collect-all "_sounddevice_data" ^
    --collect-all "soundfile" ^
    --collect-all "_soundfile_data" ^
    --collect-submodules "scipy.signal" ^
    --collect-data "scipy" ^
    --collect-all "keyboard" ^
    --collect-all "pynput" ^
    main.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo ======================================================================
    echo [ERROR] Build failed with exit code %ERRORLEVEL%.
    echo Please review the error log above.
    echo ======================================================================
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ======================================================================
echo                      BUILD COMPLETED SUCCESSFULLY!
echo ======================================================================
echo.
echo Your compiled standalone Windows application is located at:
echo   %CD%\dist\SoundboardPro\SoundboardPro.exe
echo.
echo You can run SoundboardPro.exe directly or create a desktop shortcut.
echo Configuration and custom sounds will be stored safely in:
echo   %%APPDATA%%\SoundboardPro\
echo.
pause
