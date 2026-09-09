@echo off
REM Configura o Telegram como canal de alertas.
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   [X] Ambiente nao instalado. Rode instalar.bat primeiro.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" scripts\telegram_setup.py
pause
