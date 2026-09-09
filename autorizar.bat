@echo off
REM ============================================================
REM  Autoriza uma conta do Mercado Livre. Duplo clique.
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
echo    AUTORIZAR CONTA DO MERCADO LIVRE
echo   ======================================================
echo.
echo   Tenha em maos, do seu app no DevCenter:
echo     - App ID
echo     - Secret Key
echo     - Redirect URI (exatamente como esta cadastrado)
echo.
echo   Contas registradas:
echo.

".venv\Scripts\python.exe" cli.py contas

echo.
echo   ------------------------------------------------------
echo   Digite o slug da conta (a coluna da esquerda).
echo   Para varias de uma vez, separe por espaco.
echo   ------------------------------------------------------
echo.

set /p SLUGS="Slug(s): "

if "%SLUGS%"=="" (
    echo Nada digitado. Cancelado.
    pause
    exit /b 1
)

echo.
".venv\Scripts\python.exe" scripts\autorizar.py %SLUGS%

echo.
pause
