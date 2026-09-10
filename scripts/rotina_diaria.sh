#!/usr/bin/env bash
# Rotina diária. Coloque no cron/agendador do sistema, ou dispare por
# uma tarefa agendada do Claude.
#
#   0 8 * * *  /caminho/para/zion-ml/scripts/rotina_diaria.sh
#
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -d ".venv" ]; then source .venv/bin/activate; fi

python cli.py rotina todas --sem-visitas 2>&1 | tee -a "data/rotina-$(date +%Y-%m).log"
python scripts/guardiao.py 2>&1 | tee -a "data/rotina-$(date +%Y-%m).log"
