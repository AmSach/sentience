@echo off
echo ========================================
echo   Sentience Windows Build Script
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    pause
    exit /b 1
)

:: Install build dependencies
echo Installing PyInstaller...
pip install pyinstaller

:: Build the exe
echo Building executable...
pyinstaller sentience.spec --clean

if exist "dist\Sentience.exe" (
    echo.
    echo ========================================
    echo   Build successful!
    echo ========================================
    echo.
    echo Executable: dist\Sentience.exe
    echo.
    
    :: Create distribution folder
    if not exist "release" mkdir release
    copy dist\Sentience.exe release\
    copy README.md release\
    echo.
    echo Distribution folder: release\
    echo.
) else (
    echo Build failed! Check the error messages above.
)

pause
