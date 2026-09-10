@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  SIMULACAO — nao escreve nada no Mercado Livre.
echo  A saida fica gravada em relatorios\ultima-rodada-promos.txt
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { .\.venv\Scripts\python.exe scripts\cadastrar_promos.py facilita-brasil-principal 2>&1 | Tee-Object -FilePath 'relatorios\ultima-rodada-promos.txt' }"
echo.
pause
