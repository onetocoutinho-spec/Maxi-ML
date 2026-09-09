@echo off
REM ============================================================
REM  Gera a pagina de acompanhamento de UMA loja e abre no navegador.
REM
REM  Responde "o que fazer nesta conta hoje": o que sobra em cada
REM  anuncio, o que as campanhas fazem com isso, e o frete.
REM  Para comparar as contas entre si, use painel-metricas.bat.
REM
REM  So le o banco e a planilha de custo. Nao chama a API do ML.
REM  Sem acento e com LF, igual aos outros .bat da pasta.
REM ============================================================
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto SEM_AMBIENTE

echo.
echo   ======================================================
echo    PAGINA DA LOJA
echo   ======================================================
echo.
echo   Enter gera as tres:
echo     enio-toldos-principal, facilita-brasil-principal, facilita-decoralli
echo.
echo   Ou escreva UM slug para gerar so o dele.
echo.

set /p SLUG="Conta [Enter para as tres]: "

echo.
if "%SLUG%"=="" goto TODAS

".venv\Scripts\python.exe" scripts\painel_loja.py %SLUG%
if errorlevel 1 goto FALHOU
if not exist "relatorios\loja-%SLUG%.html" goto FALHOU
echo.
echo   Abrindo no navegador...
start "" "relatorios\loja-%SLUG%.html"
goto FIM

:TODAS
".venv\Scripts\python.exe" scripts\painel_loja.py
if errorlevel 1 goto FALHOU
echo.
REM Sem bloco entre parenteses de proposito - ver o aviso no status.bat.
echo   Abrindo no navegador...
if exist "relatorios\loja-enio-toldos-principal.html" start "" "relatorios\loja-enio-toldos-principal.html"
if exist "relatorios\loja-facilita-brasil-principal.html" start "" "relatorios\loja-facilita-brasil-principal.html"
if exist "relatorios\loja-facilita-decoralli.html" start "" "relatorios\loja-facilita-decoralli.html"

:FIM
echo.
pause
exit /b 0

:FALHOU
echo.
echo   [X] A pagina nao foi gerada.
echo       Confira o slug e rode uma coleta antes:  coletar.bat
echo.
pause
exit /b 1

:SEM_AMBIENTE
echo   [X] Ambiente nao instalado. Rode instalar.bat primeiro.
echo.
pause
exit /b 1
