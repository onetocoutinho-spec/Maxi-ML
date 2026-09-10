@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  TESTE DE ESCRITA — cadastra de verdade, mas so nos 10 primeiros anuncios.
echo  A saida fica gravada em relatorios\ultima-rodada-promos.txt
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { .\.venv\Scripts\python.exe scripts\cadastrar_promos.py facilita-brasil-principal --limite 10 --aplicar 2>&1 | Tee-Object -FilePath 'relatorios\ultima-rodada-promos.txt' }"
echo.
pause
