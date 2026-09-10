@echo off
REM Executa agora o que estiver em pedidos\, sem esperar o vigia.
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo   [X] Ambiente nao instalado. Rode instalar.bat primeiro.
    pause
    exit /b 1
)

echo.
echo   Processando a fila de pedidos...
echo.
".venv\Scripts\python.exe" scripts\fila.py

echo.
echo   Resultados em pedidos\feitos\
echo.
pause
