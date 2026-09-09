@echo off
REM Mapeia quem disputa cada produto de catalogo da conta.
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
echo    MAPA DE CONCORRENTES
echo   ======================================================
echo.
echo   Percorre seus anuncios de catalogo e descobre todos os
echo   vendedores do mesmo produto: preco, frete, reputacao.
echo.

set /p SLUG="Slug da conta [enio-toldos-principal]: "
if "%SLUG%"=="" set SLUG=enio-toldos-principal

set /p CEP="CEP de referencia para o frete [01001000]: "
if "%CEP%"=="" set CEP=01001000

set /p PROC="Procurar algum concorrente pelo nome (Enter pula): "

echo.
if "%PROC%"=="" (
    ".venv\Scripts\python.exe" cli.py mapear %SLUG% --cep %CEP% --detalhado
) else (
    ".venv\Scripts\python.exe" cli.py mapear %SLUG% --cep %CEP% --procurar "%PROC%" --detalhado
)

echo.
pause
