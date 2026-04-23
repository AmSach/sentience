@echo off
:: Simple Windows installer for Sentience
:: Run this file to install

echo ==========================================
echo   Sentience v2.0 Installer
echo ==========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found!
    echo Please install Python 3.11+ from https://python.org
    echo Make sure to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

:: Get install directory
set INSTALL_DIR=%LOCALAPPDATA%\Sentience

echo Installing to: %INSTALL_DIR%
echo.

:: Create directory
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Copy files
echo Copying files...
xcopy /E /I /Y "%~dp0*" "%INSTALL_DIR%\" >nul 2>&1

:: Install dependencies
echo Installing dependencies (this may take a few minutes)...
cd /d "%INSTALL_DIR%"
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet

:: Install Playwright
echo Installing browser automation...
python -m playwright install chromium --quiet

:: Create launcher
echo @echo off> "%INSTALL_DIR%\sentience.bat"
echo cd /d "%INSTALL_DIR%">> "%INSTALL_DIR%\sentience.bat"
echo python cli.py %%*>> "%INSTALL_DIR%\sentience.bat"

:: Add to PATH
echo Adding to PATH...
setx PATH "%PATH%;%INSTALL_DIR%" >nul 2>&1

:: Create desktop shortcut
echo Creating desktop shortcut...
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%USERPROFILE%\Desktop\Sentience.lnk'); $s.TargetPath = '%INSTALL_DIR%\sentience.bat'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Save()"

echo.
echo ==========================================
echo   Installation Complete!
echo ==========================================
echo.
echo To start Sentience:
echo   1. Open a NEW terminal (to refresh PATH)
echo   2. Run: sentience
echo.
echo Or double-click the desktop shortcut.
echo.
pause
