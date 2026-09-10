@echo off
REM ============================================================
REM  Pedir alguma coisa AGORA, sem esperar a rotina.
REM ============================================================
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo   [X] Ambiente nao instalado. Rode instalar.bat primeiro.
    pause
    exit /b 1
)

:menu
echo.
echo   ======================================================
echo    O QUE VOCE QUER AGORA?
echo   ======================================================
echo.
echo    1  Coletar e ver o que mudou
echo    2  Resumo do dia no Telegram
echo    3  Resumo de concorrencia no Telegram
echo    4  Mapa de concorrentes (preco, frete, reputacao)
echo    5  Alertas das ultimas 24h aqui na tela
echo    6  Abrir o painel no navegador
echo    7  Limpar alertas errados das ultimas horas
echo    8  RAIO-X da conta + enviar no Telegram
echo    0  Sair
echo.

set /p OP="Opcao: "

if "%OP%"=="1" ".venv\Scripts\python.exe" cli.py coletar todas
if "%OP%"=="2" ".venv\Scripts\python.exe" cli.py notificar --resumo
if "%OP%"=="3" ".venv\Scripts\python.exe" cli.py notificar --semanal
if "%OP%"=="4" ".venv\Scripts\python.exe" cli.py mapear todas --detalhado
if "%OP%"=="5" ".venv\Scripts\python.exe" cli.py alertas --horas 24
if "%OP%"=="6" call painel.bat
if "%OP%"=="7" ".venv\Scripts\python.exe" cli.py limpar-alertas --horas 6
if "%OP%"=="8" ".venv\Scripts\python.exe" cli.py diagnostico --enviar --detalhado
if "%OP%"=="0" exit /b 0

echo.
pause
goto menu
