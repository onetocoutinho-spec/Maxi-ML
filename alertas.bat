@echo off
REM Mostra os alertas das ultimas 24h.
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo   [X] Ambiente nao instalado. Rode instalar.bat primeiro.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" cli.py alertas --horas 24
echo.
pause
