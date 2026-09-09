@echo off
REM ============================================================
REM  Registra a rotina no Agendador de Tarefas do Windows.
REM  Roda a cada 3 horas. Duplo clique para instalar.
REM  Para remover:  agendar.bat /remover
REM ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set TAREFA=ZionML-Rotina

if /i "%~1"=="/remover" (
    schtasks /delete /tn "%TAREFA%" /f
    echo Tarefa removida.
    pause
    exit /b 0
)

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
    /tr "\"%~dp0scripts\rotina_diaria.bat\"" ^
    /sc hourly ^
    /mo 1 ^
    /st 07:30 ^
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
echo   Agendado: DE HORA EM HORA, a partir das 07:30.
echo.
echo   O ciclo completo, sem voce clicar em nada:
echo.
echo     toda hora: coleta + vigilancia dos concorrentes
echo                (preco, frete, estoque, status)
echo                alerta critico sai na hora
echo     04h30  mapa completo: descobre concorrente novo
echo     06h00  visitas dos anuncios (1x ao dia)
echo     07h30  resumo do dia no Telegram
echo     07h30 de segunda: resumo semanal de concorrencia
echo     22h as 7h: silencio, acumula para a manha
echo.
echo   Se a maquina estiver desligada no horario, o resumo sai na
echo   proxima rodada do dia - nao se perde e nao repete.
echo.
echo   Log: data\rotina.log
echo   Remover: agendar.bat /remover
echo   ------------------------------------------------------
echo.
pause
