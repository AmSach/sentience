@echo off
echo ================================
echo   Sentience v4.0 Installer
echo ================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Installing core dependencies...
pip install flask flask-cors requests lz4 psutil --quiet

echo [2/3] Installing optional dependencies...
pip install sentence-transformers chromadb numpy --quiet 2>nul

echo [3/3] Installing GUI dependencies...
pip install PySide6 --quiet 2>nul

echo.
echo ================================
echo   Installation Complete!
echo ================================
echo.
echo Next steps:
echo 1. Get a free API key from https://console.groq.com
echo 2. Set it: set GROQ_API_KEY=gsk_your_key_here
echo 3. Run: python sentience.py
echo.
echo Or use Ollama for 100%% local:
echo 1. Install: https://ollama.com
echo 2. Run: ollama pull llama3.2
echo 3. Run: python sentience.py
echo.

pause
