@echo off
REM ============================================================
REM  Coleta manual. Duplo clique.
REM  Sem argumento = todas as contas configuradas.
REM ============================================================
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

echo.
echo   ======================================================
echo    COLETA
echo   ======================================================
echo.
echo   Enter = todas as contas autorizadas
echo   Ou digite o slug de uma conta especifica.
echo.

set /p ALVO="Alvo [todas]: "
if "%ALVO%"=="" set ALVO=todas

echo.
".venv\Scripts\python.exe" cli.py coletar %ALVO%

echo.
echo   ------------------------------------------------------
echo   Painel: painel.bat      Alertas: alertas.bat
echo   ------------------------------------------------------
echo.
pause
