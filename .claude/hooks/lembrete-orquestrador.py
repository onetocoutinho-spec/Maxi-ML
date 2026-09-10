"""
Lembrete de orquestrador: faz a sessão iniciar a conversa em vez de esperar
o Neto perguntar "como estão as contas".

Roda como hook SessionStart (matcher "startup", só sessão genuinamente nova).
Não chama o orquestrador ele mesmo — um hook é só um script, não tem acesso a
Workflow/subagente. O que ele faz é devolver additionalContext instruindo o
modelo a rodar por conta própria, antes de atender o pedido do Neto.

Por que isto existe: nem rotina de nuvem (sem acesso a .env/banco local) nem
CronCreate (morre com a sessão, expira em 7 dias) sozinhos garantem que o
resumo chegue sem o Neto pedir. Este hook é a metade que funciona sempre,
não importa a que horas o app é aberto: SessionStart dispara toda vez.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
MARCADOR = RAIZ / "data" / "orquestrador.ultima_execucao"
HORA_MINIMA = 6  # antes disso, não teria dado de coleta fresco pra valer a pena


def _ultima_execucao_e_de_hoje() -> bool:
    if not MARCADOR.exists():
        return False
    try:
        carimbo = datetime.fromisoformat(MARCADOR.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return False
    return carimbo.date() == datetime.now().date()


def main() -> int:
    # Console do Windows abre em cp1252; sem isto um "não" no texto derruba
    # o hook com UnicodeEncodeError — mesma lição do travar-escrita-ml.py.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        json.load(sys.stdin)  # entrada não é usada, mas precisa ser consumida
    except Exception:
        pass

    partes = [
        "Rearme o lembrete diário: chame CronCreate com cron \"30 6 * * *\", "
        "recurring=true, pedindo pra rodar o orquestrador-ml e entregar o "
        "resumo (Telegram curto + link do Artifact) — o job da sessão anterior "
        "morreu junto com ela, isto é o que faz o horário fixo sobreviver "
        "enquanto o app ficar aberto.",
    ]

    if not _ultima_execucao_e_de_hoje() and datetime.now().hour >= HORA_MINIMA:
        partes.insert(0, (
            "O orquestrador ainda não rodou hoje (ou nunca rodou). Antes de "
            "atender o que o Neto pedir nesta conversa: rode "
            "Workflow({scriptPath: '.claude/workflows/orquestrador-ml.js'}), "
            "publique/atualize o Artifact com o relatório completo (leia a URL "
            "salva em data/orquestrador.artifact_url se existir, e reuse — não "
            "crie um novo a cada dia), mande um Telegram curto (3-5 linhas: "
            "data, quantos achados de prioridade alta, e o link do Artifact) "
            "via core.notify.enviar(texto), e por fim grave o timestamp de "
            "agora em data/orquestrador.ultima_execucao. Só depois disso, "
            "responda o Neto com o resumo já pronto."
        ))

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": " ".join(partes),
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
