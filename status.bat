@echo off
REM ============================================================
REM  Mostra se a automacao esta de pe - e conserta o que estiver caido.
REM
REM  Sem PowerShell e sem bloco entre parenteses de proposito: as duas
REM  coisas ja quebraram este arquivo antes, de um jeito silencioso.
REM ============================================================
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo.
echo   ======================================================
echo    STATUS DA AUTOMACAO
echo   ======================================================
echo.

echo   -- Tarefas agendadas --
schtasks /query /tn "ZionML-Rotina" /fo list 2>nul | findstr /i "TaskName Status Next"
schtasks /query /tn "ZionML-Vigia"  /fo list 2>nul | findstr /i "TaskName Status Next"
echo.

if not exist ".venv\Scripts\python.exe" goto SEM_AMBIENTE

echo   -- Vigia --
".venv\Scripts\python.exe" scripts\guardiao.py
echo.

echo   -- Ultimas linhas do log --
".venv\Scripts\python.exe" -c "import pathlib;p=pathlib.Path('data/vigia.log');print(''.join(p.read_text(encoding='utf-8',errors='replace').splitlines(True)[-10:]) if p.exists() else '  sem log ainda')"
echo.
pause
exit /b 0

:SEM_AMBIENTE
echo   [X] Ambiente nao instalado. Rode instalar.bat primeiro.
echo.
pause
exit /b 1
