@echo off
:: Run Sentience in GUI mode

set INSTALL_DIR=%~dp0

if exist "%INSTALL_DIR%sentience_env\Scripts\activate.bat" (
    call "%INSTALL_DIR%sentience_env\Scripts\activate.bat"
    start "" pythonw "%INSTALL_DIR%sentience_app.py"
) else (
    start "" pythonw "%INSTALL_DIR%sentience_app.py"
)
