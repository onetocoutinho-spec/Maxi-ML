@echo off
REM Confere se o servidor MCP do zion-ml esta apto, sem falar protocolo.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)
%PY% mcp_zion.py --autoteste
echo.
pause
