@echo off
REM ============================================================
REM  Rotina - Windows. Roda de hora em hora pelo Agendador.
REM
REM  O caminho do Python e ABSOLUTO de proposito. Com caminho
REM  relativo, qualquer execucao a partir de outra pasta cai no
REM  Python do sistema, que nao tem as bibliotecas do projeto -
REM  e a rotina morre com "No module named yaml" sem que ninguem
REM  perceba, porque o erro fica so no log.
REM ============================================================
setlocal
cd /d "%~dp0.."
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

set "RAIZ=%~dp0.."
set "PY=%RAIZ%\.venv\Scripts\python.exe"

echo. >> "data\rotina.log"
echo ===== %DATE% %TIME% ===== >> "data\rotina.log"

if not exist "%PY%" goto SEM_AMBIENTE

echo [python] %PY% >> "data\rotina.log"

REM Pedidos deixados na pasta pedidos/ - executados antes da rotina.
"%PY%" scripts\fila.py >> "data\rotina.log" 2>&1

REM SEM --sem-visitas de proposito. A flag estava fixa aqui e anulava a logica
REM de cli.py cmd_rotina, que so' liga as visitas se a flag NAO vier: o bloco
REM `if not args.sem_visitas` nunca entrava e o marcador visitas_diarias nunca
REM chegou a existir no banco. Resultado: a passada larga do dia nunca rodava,
REM e com ela ficavam de fora TRES dados, nao so' as visitas: o preco de
REM vitrine (sem ele toda comparacao com concorrente usa preco de cadastro) e
REM o custo do frete por anuncio (sem ele a margem sai como teto). A FACILITA
REM ficou desde sempre com zero visitas por causa disto.
REM O proprio cmd_rotina ja limita a uma vez por dia, na primeira rodada apos
REM as 6h, entao a rodada de hora em hora continua leve.
"%PY%" cli.py rotina todas >> "data\rotina.log" 2>&1

REM Confere se o vigia continua vivo e, se nao, sobe de novo.
"%PY%" scripts\guardiao.py >> "data\rotina.log" 2>&1

exit /b 0

:SEM_AMBIENTE
echo [X] Ambiente nao encontrado em "%PY%" - rode instalar.bat >> "data\rotina.log"
exit /b 1
