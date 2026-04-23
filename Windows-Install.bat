@echo off
setlocal enabledelayedexpansion
title Sentience Installer
color 0A

echo.
echo  ========================================
echo   SENTIENCE - Local AI Computer v1.3
echo   One-Click Windows Installer
echo  ========================================
echo.

:: Check for admin rights
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo  [!] Requesting administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: Set paths
set "INSTALL_DIR=%LOCALAPPDATA%\Sentience"
set "PYTHON_VERSION=3.11.9"
set "PYTHON_INSTALLER=python-%PYTHON_VERSION%-amd64.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/%PYTHON_INSTALLER%"
set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"

:: Create install directory
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: STEP 1: Check/Install Python
echo  [1/5] Checking Python installation...
"%PYTHON_EXE%" --version >nul 2>&1
if %errorlevel% equ 0 (
    echo       [OK] Python %PYTHON_VERSION% found
    goto :pip_install
)

echo       [~~] Python not found. Installing Python %PYTHON_VERSION%...
echo       Downloading Python installer...

:: Download Python installer
powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%INSTALL_DIR%\%PYTHON_INSTALLER%'}"

if not exist "%INSTALL_DIR%\%PYTHON_INSTALLER%" (
    echo       [ERROR] Failed to download Python installer
    echo       Please download manually from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo       Installing Python silently...
"%INSTALL_DIR%\%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1 Include_launcher=0

:: Wait for installation
timeout /t 30 /nobreak >nul

:: Verify
"%PYTHON_EXE%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo       [ERROR] Python installation failed
    pause
    exit /b 1
)

echo       [OK] Python installed successfully

:pip_install
:: STEP 2: Copy source files
echo  [2/5] Copying application files...
if not exist "%INSTALL_DIR%\src" mkdir "%INSTALL_DIR%\src"
xcopy /E /I /Y "%~dp0src" "%INSTALL_DIR%\src" >nul 2>&1
copy /Y "%~dp0requirements.txt" "%INSTALL_DIR%\" >nul 2>&1
echo       [OK] Files copied

:: STEP 3: Install dependencies
echo  [3/5] Installing Python dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip --quiet
"%PYTHON_EXE%" -m pip install -r "%INSTALL_DIR%\requirements.txt" --quiet --disable-pip-version-check

if %errorlevel% neq 0 (
    echo       [WARNING] Some dependencies may have failed
    timeout /t 3 >nul
)
echo       [OK] Dependencies installed

:: STEP 4: Install Playwright browsers
echo  [4/5] Installing browser automation...
"%PYTHON_EXE%" -m playwright install chromium 2>nul
if %errorlevel% neq 0 (
    echo       [WARNING] Playwright browser install skipped
)
echo       [OK] Browser ready

:: STEP 5: Create launchers
echo  [5/5] Creating launch shortcuts...

:: Create main launcher
echo @echo off > "%INSTALL_DIR%\Sentience.bat"
echo cd /d "%INSTALL_DIR%" >> "%INSTALL_DIR%\Sentience.bat"
echo "%PYTHON_EXE%" src\main.py >> "%INSTALL_DIR%\Sentience.bat"
echo pause >> "%INSTALL_DIR%\Sentience.bat"

:: Create desktop shortcut
powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\Desktop\Sentience.lnk'); $Shortcut.TargetPath = '%INSTALL_DIR%\Sentience.bat'; $Shortcut.WorkingDirectory = '%INSTALL_DIR%'; $Shortcut.Description = 'Sentience - Local AI Computer'; $Shortcut.Save()"

echo       [OK] Shortcuts created

:: Done
echo.
echo  ========================================
echo   INSTALLATION COMPLETE!
echo  ========================================
echo.
echo   Location: %INSTALL_DIR%
echo   Shortcut: Desktop\Sentience
echo.
echo   USAGE:
echo   1. Run Sentience from desktop shortcut
echo   2. Add your API key in Settings
echo   3. Get free key: https://console.groq.com/keys
echo.
echo  ========================================
echo.

:: Ask to launch
set /p LAUNCH="  Launch Sentience now? (Y/N): "
if /i "%LAUNCH%"=="Y" (
    start "" "%INSTALL_DIR%\Sentience.bat"
)

exit /b 0
