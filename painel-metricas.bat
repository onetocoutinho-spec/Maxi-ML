@echo off
REM ============================================================
REM  Gera o painel comparativo das contas e abre no navegador.
REM
REM  Diferente de painel.bat, que abre o relatorio POR CLIENTE ja
REM  gerado pela rotina, este monta na hora um HTML unico com as
REM  contas lado a lado. So le o banco - nao chama a API do ML.
REM
REM  Sem acento e com LF, igual aos outros .bat da pasta.
REM ============================================================
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto SEM_AMBIENTE

echo.
echo   ======================================================
echo    PAINEL COMPARATIVO DAS CONTAS
echo   ======================================================
echo.
echo   Enter usa as tres contas de sempre:
echo     enio-toldos-principal, facilita-brasil-principal, facilita-decoralli
echo.
echo   Para outras, escreva os slugs separados por virgula, sem espaco.
echo.

set /p CONTAS="Contas [Enter para as tres]: "

echo.
if "%CONTAS%"=="" goto PADRAO

".venv\Scripts\python.exe" scripts\painel_metricas.py --contas "%CONTAS%"
if errorlevel 1 goto FALHOU
goto ABRIR

:PADRAO
".venv\Scripts\python.exe" scripts\painel_metricas.py
if errorlevel 1 goto FALHOU

:ABRIR
if not exist "relatorios\painel-metricas.html" goto FALHOU
echo.
echo   Abrindo no navegador...
start "" "relatorios\painel-metricas.html"
echo.
pause
exit /b 0

:FALHOU
echo.
echo   [X] O painel nao foi gerado.
echo       Rode uma coleta antes:  coletar.bat
echo.
pause
exit /b 1

:SEM_AMBIENTE
echo   [X] Ambiente nao instalado. Rode instalar.bat primeiro.
echo.
pause
exit /b 1
