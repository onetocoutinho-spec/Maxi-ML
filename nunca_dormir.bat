@echo off
REM ============================================================
REM  Impede que o computador durma, para o vigia nao parar junto.
REM
REM  Hoje o vigia ficou 2 horas fora do ar sem erro nenhum no log:
REM  a maquina simplesmente suspendeu. Enquanto o sistema morar
REM  aqui, dormir e a principal causa de janela perdida.
REM
REM  O QUE MUDA:  suspensao e hibernacao desligadas na tomada.
REM  O QUE NAO MUDA:  a TELA continua apagando sozinha, que e o
REM  que economiza quase toda a energia. O gabinete fica ligado.
REM
REM  Para voltar atras:  nunca_dormir.bat /desfazer
REM ============================================================
setlocal
chcp 65001 >nul

if /i "%~1"=="/desfazer" goto DESFAZER
goto APLICAR

:APLICAR
echo.
echo   ======================================================
echo    MANTENDO O COMPUTADOR ACORDADO
echo   ======================================================
echo.

powercfg /change standby-timeout-ac 0
if errorlevel 1 goto SEM_PERMISSAO
powercfg /change hibernate-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /change monitor-timeout-ac 10

echo   [ok] Suspensao ....... desligada
echo   [ok] Hibernacao ...... desligada
echo   [ok] Disco ........... nunca desliga
echo   [ok] Tela ............ apaga em 10 min (nao afeta o vigia)
echo.
echo   Falta uma coisa que o Windows nao deixa mudar por comando:
echo.
echo     Configuracoes ^> Sistema ^> Energia
echo     e confira se "Suspensao" esta em "Nunca" quando ligado.
echo.
echo   Isso resolve a causa mais comum de janela perdida enquanto
echo   o sistema roda nesta maquina. Nao resolve queda de luz nem
echo   desligar o computador - para isso, so um servidor.
echo.
pause
exit /b 0

:DESFAZER
powercfg /change standby-timeout-ac 30
powercfg /change hibernate-timeout-ac 60
powercfg /change disk-timeout-ac 20
echo.
echo   Configuracao de energia devolvida ao padrao do Windows.
echo   O vigia volta a parar quando a maquina dormir.
echo.
pause
exit /b 0

:SEM_PERMISSAO
echo.
echo   [X] O Windows recusou a mudanca.
echo       Feche, clique com o botao direito neste arquivo e
echo       escolha "Executar como administrador".
echo.
pause
exit /b 1
