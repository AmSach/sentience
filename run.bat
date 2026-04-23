@echo off
:: Run Sentience in CLI mode

set INSTALL_DIR=%~dp0

if exist "%INSTALL_DIR%sentience_env\Scripts\activate.bat" (
    call "%INSTALL_DIR%sentience_env\Scripts\activate.bat"
    python "%INSTALL_DIR%sentience_app.py" --cli
) else (
    python "%INSTALL_DIR%sentience_app.py" --cli
)
pause
