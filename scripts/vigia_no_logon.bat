@echo off
REM ============================================================
REM  Sobe o vigia quando o Windows entra na sessao.
REM
REM  Copiado para a pasta de Inicializacao pelo instalar_automacao.bat.
REM  Existe porque criar tarefa "ao fazer logon" no Agendador costuma
REM  exigir privilegio de administrador, e a pasta de Inicializacao
REM  nao exige nada.
REM
REM  Chama o GUARDIAO, nao o vigia direto: o guardiao confere o
REM  batimento antes de subir qualquer coisa. Assim, se a tarefa do
REM  Agendador tambem existir, os dois caminhos nao criam dois vigias
REM  disputando a mesma conta.
REM ============================================================
setlocal
set "RAIZ=%~dp0.."
if not exist "%RAIZ%\.venv\Scripts\pythonw.exe" exit /b 1
start "" /min "%RAIZ%\.venv\Scripts\pythonw.exe" "%RAIZ%\scripts\guardiao.py"
exit /b 0
