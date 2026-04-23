@echo off
echo ========================================
echo Sentience - Local AI Computer Installer
echo ========================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed!
    echo.
    echo Please install Python 3.11+ from:
    echo https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo [1/4] Python found. Installing dependencies...
python -m pip install --upgrade pip --quiet
pip install PySide6 requests python-dotenv pyperclip playwright --quiet

echo [2/4] Installing Playwright browsers...
playwright install chromium

echo [3/4] Creating shortcut...
echo @echo off > Sentience.bat
echo cd /d "%%~dp0" >> Sentience.bat
echo python src\main.py >> Sentience.bat

echo [4/4] Creating startup config...
if not exist ".env" (
    echo # Sentience Configuration > .env
    echo # Add your API keys below: >> .env
    echo. >> .env
    echo # Groq (free): https://console.groq.com/keys >> .env
    echo GROQ_API_KEY= >> .env
    echo. >> .env
    echo # OpenAI: https://platform.openai.com/api-keys >> .env
    echo OPENAI_API_KEY= >> .env
    echo. >> .env
    echo # Anthropic: https://console.anthropic.com/ >> .env
    echo ANTHROPIC_API_KEY= >> .env
)

echo.
echo ========================================
echo INSTALLATION COMPLETE!
echo ========================================
echo.
echo TO RUN:
echo   - Double-click Sentience.bat
echo   - Or run: python src\main.py
echo.
echo TO CONFIGURE:
echo   - Edit .env file and add your API keys
echo   - Or configure in-app Settings menu
echo.
echo Supported providers:
echo   - Groq (free tier available)
echo   - OpenAI
echo   - Anthropic
echo   - Ollama (100%% local)
echo.
pause