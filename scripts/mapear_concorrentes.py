#!/usr/bin/env python3
"""
Invólucro para rodar o mapa de concorrentes fora da rotina.
A lógica mora em core/confrontos.py e é a mesma que a rotina executa.

  python scripts/mapear_concorrentes.py <slug> [--cep 01001000] [--procurar pergola]

No dia a dia você não precisa disto: a rotina agendada roda o mapa uma vez
por dia sozinha. Use quando quiser um mapa agora.
"""
import subprocess, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
args = sys.argv[1:]
if not args:
    print("uso: python scripts/mapear_concorrentes.py <slug> [--cep ...] [--procurar ...]")
    sys.exit(1)

sys.exit(subprocess.call(
    [sys.executable, str(RAIZ / "cli.py"), "mapear", *args, "--detalhado"],
    cwd=str(RAIZ),
))
