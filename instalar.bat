@echo off
REM ============================================================
REM  zion-ml - instalacao (Windows). Duplo clique para rodar.
REM  Cria o ambiente virtual, instala as dependencias e testa.
REM ============================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

echo.
echo   zion-ml - instalando
echo   ------------------------------------------------------
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo   [X] Python nao encontrado no PATH.
    echo.
    echo   Instale em https://python.org/downloads e marque
    echo   "Add Python to PATH" na primeira tela do instalador.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo   Criando ambiente virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo   [X] Falhou ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)

echo   Instalando dependencias...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo   [X] Falhou ao instalar as dependencias.
    pause
    exit /b 1
)

echo.
echo   ------------------------------------------------------
echo   Instalado. Clientes e contas registrados:
echo   ------------------------------------------------------
echo.
".venv\Scripts\python.exe" cli.py contas

echo.
echo   ------------------------------------------------------
echo   PROXIMO PASSO: autorizar uma conta
echo.
echo     .venv\Scripts\python.exe scripts\autorizar.py enio-toldos-principal
echo.
echo   Tenha em maos o App ID, a Secret Key e o Redirect URI
echo   do seu app no DevCenter do Mercado Livre.
echo   ------------------------------------------------------
echo.
pause
