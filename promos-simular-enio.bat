@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  SIMULACAO de promocoes — ENIO TOLDOS (ShoppLima).
echo  Piso de margem 12%%, conforme contas\enio-toldos-principal\conta.yaml.
echo.
echo  NAO escreve nada no Mercado Livre. Só calcula e grava o relatorio em
echo  relatorios\ultima-rodada-promos-enio.txt
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { .\.venv\Scripts\python.exe scripts\cadastrar_promos.py enio-toldos-principal --piso 12 2>&1 | Tee-Object -FilePath 'relatorios\ultima-rodada-promos-enio.txt' }"
echo.
pause
