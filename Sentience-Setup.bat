@echo off
title Sentience Installer
color 0A
echo.
echo  ███████╗██████╗ ██╗   ██╗██████╗  █████╗ ██████╗  █████╗ ███╗   ██╗
echo  ██╔════╝██╔══██╗██║   ██║██╔══██╗██╔══██╗██╔══██╗██╔══██╗████╗  ██║
echo  █████╗  ██║  ██║██║   ██║██████╔╝███████║██████╔╝███████║██╔██╗ ██║
echo  ██╔══╝  ██║  ██║██║   ██║██╔══██╗██╔══██║██╔══██╗██╔══██║██║╚██╗██║
echo  ███████╗██████╔╝╚██████╔╝██████╔╝██║  ██║██║  ██║██║  ██║██║ ╚████║
echo  ╚══════╝╚═════╝  ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝
echo.
echo  Local AI Computer — Double-click to run
echo.

REM Check for Python (needed for some features)
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Python not found. Some advanced features need it.
    echo [INFO] Download Python 3.10+ from python.org if you want full features.
    echo.
)

REM Check for API key
if exist ".env" (
    findstr /C:"ANTHROPIC_API_KEY" .env >nul 2>&1
    if %errorlevel% equ 0 (
        echo [OK] API key found in .env
    ) else (
        echo [SETUP] No API key detected. Launch Sentience and use BYOK Setup.
    )
) else (
    echo [SETUP] No .env found. Launch Sentience and use BYOK Setup.
)

echo.
echo ============================================================
echo.
echo  HOW TO USE:
echo.
echo  1. Double-click  Sentience.exe  to launch the app
echo  2. Click 'BYOK Setup' inside the app
echo  3. Paste your Anthropic API key (or OpenAI/Groq)
echo  4. Start chatting!
echo.
echo  For local models (offline): Install Ollama from ollama.ai
echo.
echo ============================================================
echo.
pause
