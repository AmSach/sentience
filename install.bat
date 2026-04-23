@echo off
echo ========================================
echo   Sentience - Local AI Computer
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python 3.10+ from https://python.org
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

:: Create venv
echo Creating virtual environment...
python -m venv venv
call venv\Scripts\activate.bat

:: Install dependencies
echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt

:: Create config dir
if not exist "%USERPROFILE%\.sentience" mkdir "%USERPROFILE%\.sentience"

echo.
echo ========================================
echo   Installation complete!
echo ========================================
echo.
echo To run Sentience:
echo   1. Set your API key:
echo      set GROQ_API_KEY=your_key_here
echo.
echo   2. Run: python src\main.py
echo.
echo Or use run.bat
echo.
echo Get free API key from: https://console.groq.com
pause
