@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  CADASTRO DE VERDADE na conta inteira (facilita-brasil-principal).
echo  Sao ~8 minutos de varredura e depois as adesoes, uma a cada 0,4s.
echo  A saida fica gravada em relatorios\ultima-rodada-promos.txt
echo.
pause
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { .\.venv\Scripts\python.exe scripts\cadastrar_promos.py facilita-brasil-principal --aplicar 2>&1 | Tee-Object -FilePath 'relatorios\ultima-rodada-promos.txt' }"
echo.
pause
