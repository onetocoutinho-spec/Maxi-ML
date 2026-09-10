@echo off
REM Abre o painel mais recente de cada cliente no navegador.
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

set ACHOU=0
for /d %%C in (relatorios\*) do (
    if exist "%%C\ultimo.html" (
        echo Abrindo %%~nxC...
        start "" "%%C\ultimo.html"
        set ACHOU=1
    )
)

if "!ACHOU!"=="0" (
    echo.
    echo   Nenhum painel gerado ainda.
    echo   Rode uma coleta primeiro:
    echo.
    echo     .venv\Scripts\python.exe cli.py coletar ^<slug^>
    echo.
    pause
)
