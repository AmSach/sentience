@echo off
:: Sentience Windows Installer v2.1
:: Run as Administrator, from the extracted folder

title Sentience Installer

echo ================================================
echo   Sentience v2.1 - Local AI Computer Installer
echo ================================================
echo.

:: Check if running as admin
net session >nul 2>&1
if errorlevel 1 (
    echo WARNING: Not running as Administrator.
    echo Some features may not work.
    echo.
)

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo.
    echo Please install Python 3.11+ from:
    echo https://www.python.org/downloads/
    echo.
    echo IMPORTANT: Check "Add Python to PATH" during installation!
    echo.
    pause
    exit /b 1
)

echo [1/5] Python found:
python --version
echo.

:: Create virtual environment
echo [2/5] Creating virtual environment...
python -m venv sentience_env
call sentience_env\Scripts\activate.bat
echo Virtual environment activated.
echo.

:: Install dependencies
echo [3/5] Installing dependencies...
pip install --upgrade pip
pip install flask flask-cors anthropic openai groq python-dotenv pyyaml pypdf reportlab python-docx openpyxl lz4 requests
echo.

:: Install GUI dependencies
echo [4/5] Installing GUI and browser automation...
pip install pyside6 playwright
playwright install chromium
echo.

:: Create shortcuts
echo [5/5] Creating shortcuts...

:: Get current directory
set INSTALL_DIR=%~dp0

:: Create desktop shortcut using PowerShell
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%USERPROFILE%\Desktop\Sentience.lnk'); $sc.TargetPath = '%INSTALL_DIR%sentience_env\Scripts\python.exe'; $sc.Arguments = '%INSTALL_DIR%sentience_app.py'; $sc.WorkingDirectory = '%INSTALL_DIR%'; $sc.Description = 'Sentience - Local AI Computer'; $sc.Save()"

:: Create start menu shortcut
if not exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs" mkdir "%APPDATA%\Microsoft\Windows\Start Menu\Programs"
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%APPDATA%\Microsoft\Windows\Start Menu\Programs\Sentience.lnk'); $sc.TargetPath = '%INSTALL_DIR%sentience_env\Scripts\python.exe'; $sc.Arguments = '%INSTALL_DIR%sentience_app.py'; $sc.WorkingDirectory = '%INSTALL_DIR%'; $sc.Description = 'Sentience - Local AI Computer'; $sc.Save()"

echo.
echo ================================================
echo   Installation Complete!
echo ================================================
echo.
echo Sentience is now installed.
echo.
echo Launch options:
echo   1. Desktop shortcut: "Sentience"
echo   2. Start Menu: Sentience
echo   3. Run: run.bat (CLI mode)
echo   4. Run: run-ui.bat (GUI mode)
echo.
echo First time setup:
echo   1. Launch Sentience
echo   2. Go to Settings ^> BYOK Keys
echo   3. Add your OpenAI/Anthropic/Groq API key
echo.
pause
