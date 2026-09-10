@echo off
REM Acrescenta um concorrente por link do anuncio.
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
echo   ======================================================
echo    VIGIAR UM CONCORRENTE
echo   ======================================================
echo.
echo   Cole o link do concorrente - anuncio ou ficha de
echo   catalogo, tanto faz. O sistema pergunta a API o que
echo   e aquele ID e cadastra do jeito certo.
echo.
echo   Se quiser alerta de preco, informe depois qual anuncio
echo   SEU ele enfrenta.
echo.

set /p SLUG="Conta [enio-toldos-principal]: "
if "%SLUG%"=="" set SLUG=enio-toldos-principal

set /p LINK="Link do concorrente: "
if "%LINK%"=="" (
    echo Nada informado. Cancelado.
    pause
    exit /b 1
)

set /p APELIDO="Apelido (Enter pula): "
set /p ALVO="MLB do SEU anuncio equivalente (Enter pula): "

echo.
if "%ALVO%"=="" (
    ".venv\Scripts\python.exe" cli.py vigiar %SLUG% "%LINK%" --apelido "%APELIDO%"
) else (
    ".venv\Scripts\python.exe" cli.py vigiar %SLUG% "%LINK%" --apelido "%APELIDO%" --comparar-com %ALVO%
)

echo.
pause
