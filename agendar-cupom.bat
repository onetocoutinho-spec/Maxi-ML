@echo off
REM ============================================================
REM  Agenda o resumo de cupom para as 00:00, todo dia.
REM  Duplo clique para instalar.
REM  Para remover:  agendar-cupom.bat /remover
REM  Para outra conta:  agendar-cupom.bat slug-da-conta
REM ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set TAREFA=ZionML-Cupom
set CONTA=maxi-brasil-principal

if /i "%~1"=="/remover" (
    schtasks /delete /tn "%TAREFA%" /f
    echo Tarefa removida.
    pause
    exit /b 0
)
if not "%~1"=="" set CONTA=%~1

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   [X] Ambiente nao instalado. Rode instalar.bat primeiro.
    echo.
    pause
    exit /b 1
)

schtasks /query /tn "%TAREFA%" >nul 2>&1
if not errorlevel 1 (
    echo   Ja existe uma tarefa "%TAREFA%". Recriando...
    schtasks /delete /tn "%TAREFA%" /f >nul
)

schtasks /create ^
    /tn "%TAREFA%" ^
    /tr "\"%~dp0scripts\cupom_diario.bat\" %CONTA%" ^
    /sc daily ^
    /st 00:00 ^
    /f

if errorlevel 1 (
    echo.
    echo   [X] Falhou ao criar a tarefa.
    echo   Tente executar este arquivo como administrador.
    echo.
    pause
    exit /b 1
)

echo.
echo   ------------------------------------------------------
echo   Agendado: TODO DIA as 00:00, conta %CONTA%.
echo.
echo   O que acontece a cada meia-noite:
echo     1. atualiza os pedidos dos ultimos 5 dias
echo     2. manda o resumo do cupom no canal configurado
echo.
echo   Se nao houver venda com cupom no periodo, ele NAO envia -
echo   relatorio zerado no canal parece resultado, e nao e.
echo.
echo   Se a maquina estiver desligada a meia-noite, o Windows
echo   roda assim que ela ligar, se a tarefa estiver marcada
echo   para isso no Agendador.
echo.
echo   Log: data\cupom.log
echo   Remover: agendar-cupom.bat /remover
echo   ------------------------------------------------------
echo.
pause
