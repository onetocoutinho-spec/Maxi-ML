@echo off
REM ============================================================
REM  Liga tudo: rotina agendada + vigia continuo sem janela.
REM  Duplo clique. Rode de novo sempre que o codigo for atualizado.
REM
REM  Para desligar:  instalar_automacao.bat /remover
REM
REM  Sem PowerShell e sem bloco entre parenteses. Os dois ja
REM  quebraram este arquivo antes, de um jeito ruim: o cmd
REM  engoliu o inicio de comandos ("'et' nao reconhecido") e a
REM  execucao caiu no ramo de REMOVER sem ninguem pedir. Aqui
REM  todo desvio e feito com goto, que nao tem essa armadilha.
REM ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set T_ROTINA=ZionML-Rotina
set T_VIGIA=ZionML-Vigia
set PY=%~dp0.venv\Scripts\python.exe
set PYW=%~dp0.venv\Scripts\pythonw.exe

if /i "%~1"=="/remover" goto REMOVER
goto INSTALAR

:REMOVER
schtasks /delete /tn "%T_ROTINA%" /f >nul 2>&1
schtasks /delete /tn "%T_VIGIA%" /f >nul 2>&1
del /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\zion-ml-vigia.bat" >nul 2>&1
if not exist "%PY%" goto REMOVIDO
"%PY%" scripts\guardiao.py --so-derrubar
:REMOVIDO
echo.
echo   Automacao removida. Nada mais roda sozinho.
echo.
pause
exit /b 0

:INSTALAR
if not exist "%PY%" goto SEM_AMBIENTE

echo.
echo   ======================================================
echo    LIGANDO A AUTOMACAO
echo   ======================================================
echo.

REM ---------- tarefa 1: rotina de hora em hora ----------
schtasks /delete /tn "%T_ROTINA%" /f >nul 2>&1
schtasks /create /tn "%T_ROTINA%" /tr "\"%~dp0scripts\rotina_diaria.bat\"" /sc hourly /mo 1 /st 07:30 /f >nul
if errorlevel 1 goto ERRO_ROTINA
echo   [ok] Rotina: de hora em hora, a partir das 07:30
goto TAREFA_VIGIA

:ERRO_ROTINA
echo   [X] Nao consegui criar a tarefa da rotina.
echo       Feche, clique com o botao direito neste arquivo
echo       e escolha "Executar como administrador".
echo.
pause
exit /b 1

REM ---------- tarefa 2: vigia sobe ao ligar o computador ----------
REM  Chama o guardiao, nao o vigia direto: ele confere o batimento
REM  antes de subir, entao este caminho e a pasta de Inicializacao
REM  podem coexistir sem criar dois vigias.
:TAREFA_VIGIA
schtasks /delete /tn "%T_VIGIA%" /f >nul 2>&1
schtasks /create /tn "%T_VIGIA%" /tr "\"%PYW%\" \"%~dp0scripts\guardiao.py\"" /sc onlogon /f >nul 2>&1
if errorlevel 1 goto SEM_TAREFA_VIGIA
echo   [ok] Vigia: tarefa de logon criada no Agendador
goto ATALHO_INICIALIZAR

:SEM_TAREFA_VIGIA
echo   [!] O Agendador recusou a tarefa de logon (falta administrador).
echo       Sem problema: vai pela pasta de Inicializacao, que nao exige.

REM ---------- rede de seguranca: pasta de Inicializacao do Windows ----------
REM  Nao exige privilegio nenhum. E o caminho que funciona quando o
REM  Agendador recusa - e foi exatamente o que aconteceu aqui.
:ATALHO_INICIALIZAR
set "INICIAR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if not exist "%INICIAR%" goto SEM_INICIALIZAR
copy /y "%~dp0scripts\vigia_no_logon.bat" "%INICIAR%\zion-ml-vigia.bat" >nul 2>&1
if errorlevel 1 goto SEM_INICIALIZAR
echo   [ok] Vigia: atalho na pasta de Inicializacao do Windows
goto REINICIAR

:SEM_INICIALIZAR
echo   [!] Nao consegui gravar na pasta de Inicializacao.
echo       O vigia ainda volta sozinho, mas so na hora cheia
echo       seguinte, pela rotina de hora em hora.

:REINICIAR
echo.
echo   Reiniciando o vigia com o codigo atual...
"%PY%" scripts\guardiao.py --reiniciar

echo.
echo   Conferindo como a maquina ficou...
echo.
"%PY%" cli.py maquina

echo.
echo   ------------------------------------------------------
echo   PRONTO. Daqui pra frente, sem clicar em nada:
echo.
echo     a cada 5 min   vigia: seus anuncios e os concorrentes,
echo                    executa o que estiver em pedidos\ e se
echo                    reinicia sozinho quando o codigo muda
echo     a cada 1 hora  rotina completa + conserta o vigia
echo     04h30          mapa: descobre concorrente novo
echo     06h00          visitas dos anuncios
echo     07h30          resumo do dia
echo     07h30 segunda  resumo semanal de concorrencia
echo.
echo   Ver se esta tudo de pe:  status.bat
echo   Desligar tudo:           instalar_automacao.bat /remover
echo   ------------------------------------------------------
echo.
pause
exit /b 0

:SEM_AMBIENTE
echo.
echo   [X] Ambiente nao instalado. Rode instalar.bat primeiro.
echo.
pause
exit /b 1
