@echo off
REM Descobre quais endpoints da API do ML o seu app consegue acessar.
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo   [X] Ambiente nao instalado. Rode instalar.bat primeiro.
    pause
    exit /b 1
)

set /p SLUG="Slug da conta [enio-toldos-principal]: "
if "%SLUG%"=="" set SLUG=enio-toldos-principal

".venv\Scripts\python.exe" scripts\diagnosticar.py %SLUG%
pause
