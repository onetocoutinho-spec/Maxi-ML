@echo off
REM ============================================================
REM  Resumo diario de cupom - roda a meia-noite pelo Agendador.
REM
REM  Duas etapas, e a ordem importa: primeiro atualiza os pedidos
REM  dos ultimos dias (barato, porque pedido ja registrado nao e
REM  relido), depois manda o resumo da janela inteira. Enviar sem
REM  coletar antes mandaria o retrato de ontem com data de hoje.
REM
REM  O caminho do Python e ABSOLUTO de proposito - mesmo motivo
REM  da rotina_diaria.bat: caminho relativo cai no Python do
REM  sistema e morre com "No module named yaml" so no log.
REM ============================================================
setlocal
cd /d "%~dp0.."
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

set "RAIZ=%~dp0.."
set "PY=%RAIZ%\.venv\Scripts\python.exe"
set "CONTA=maxi-brasil-principal"
if not "%~1"=="" set "CONTA=%~1"

echo. >> "data\cupom.log"
echo ===== %DATE% %TIME% ===== >> "data\cupom.log"

if not exist "%PY%" goto SEM_AMBIENTE

REM 1) atualiza os pedidos recentes (incremental)
"%PY%" cli.py cupons %CONTA% --vendas --dias 5 --limite 99999 >> "data\cupom.log" 2>&1

REM 2) manda o resumo dos ultimos 60 dias.
REM    Se o banco estiver vazio o proprio comando se recusa a enviar.
"%PY%" cli.py cupons %CONTA% --enviar --dias 60 >> "data\cupom.log" 2>&1

exit /b 0

:SEM_AMBIENTE
echo [X] Ambiente nao encontrado em "%PY%" - rode instalar.bat >> "data\cupom.log"
exit /b 1
