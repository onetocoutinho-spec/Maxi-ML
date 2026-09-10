@echo off
REM ============================================================
REM  Vigia continuo. Deixe esta janela aberta.
REM  Fecha a janela = para de vigiar.
REM ============================================================
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title Zion ML - Vigia

if not exist ".venv\Scripts\python.exe" (
    echo   [X] Ambiente nao instalado. Rode instalar.bat primeiro.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" vigia.py %*

echo.
echo   O vigia parou.
pause
