@echo off
:: Quick launcher - run this after installation
cd /d "%LOCALAPPDATA%\Sentience"
"%LOCALAPPDATA%\Programs\Python\Python311\python.exe" src\main.py
if %errorlevel% neq 0 (
    echo.
    echo Error running Sentience. Try running Windows-Install.bat first.
    pause
)
