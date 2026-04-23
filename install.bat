@echo off
echo ================================
echo Sentience v3.0 Installer
echo ================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Installing Python...
    winget install Python.Python.3.12
)

:: Install dependencies
echo Installing dependencies...
pip install -r requirements.txt

:: Install Playwright browsers
echo Installing browser...
playwright install chromium

:: Create config directory
if not exist "%USERPROFILE%\.sentience" mkdir "%USERPROFILE%\.sentience"

:: Create desktop shortcut
echo Creating shortcut...
set SCRIPT="%TEMP%\%RANDOM%-SentienceShortcut.vbs"
echo Set oWS = WScript.CreateObject("WScript.Shell") >> %SCRIPT%
echo sLinkFile = oWS.SpecialFolders("Desktop") ^& "\Sentience.lnk" >> %SCRIPT%
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> %SCRIPT%
echo oLink.TargetPath = "%CD%\sentience.py" >> %SCRIPT%
echo oLink.WorkingDirectory = "%CD%" >> %SCRIPT%
echo oLink.Save >> %SCRIPT%
cscript /nologo %SCRIPT%
del %SCRIPT%

echo.
echo ================================
echo Installation complete!
echo ================================
echo.
echo To run Sentience:
echo   1. Set your API key:
echo      set OPENAI_API_KEY=sk-...
echo      or
echo      set GROQ_API_KEY=gsk-... (free)
echo.
echo   2. Run:
echo      python sentience.py
echo.
echo Or double-click the desktop shortcut.
echo.
pause
