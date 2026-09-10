"""
Trava de escrita: nada altera a conta de um cliente sem o Neto aprovar na hora.

Roda como hook PreToolUse do Bash. Lê a chamada, e se ela for capaz de MUDAR
alguma coisa — publicar anúncio, reativar, encerrar, aderir a campanha, ou
escrever por cima do histórico do banco — devolve "ask", que força o prompt de
permissão mesmo que o comando estivesse liberado por outra regra.

Existe porque um subagente trabalha num contexto separado: você não lê a
conversa dele, só o resultado. Sem esta trava, "analisa a margem da Decoralli"
poderia terminar com um anúncio publicado sem ninguém ter dito sim.

Nunca BLOQUEIA de vez — só obriga a passar por você. Aprovar é um Enter.
"""
from __future__ import annotations

import json
import re
import sys

# Flags que fazem o comando sair da simulação e escrever de verdade na API.
# Cada uma foi conferida em 02/09/2026 no --help do comando correspondente.
ESCRITA_API = [
    (r"--publicar\b", "cli.py publicar — cadastra o anúncio de verdade na conta"),
    (r"--confirmar\b", "cli.py reativar/encerrar — encerrar NÃO tem volta"),
    (r"--aplicar\b", "cadastrar_promos.py — faz a adesão à campanha de verdade"),
    (r"--sim\b", "confirmação de publicação em lote"),
]

# O histórico é o produto: snapshot é imutável, coleta nova é linha nova.
# UPDATE ou DELETE em snap_* reescreve passado e não dá para desfazer.
ESCRITA_BANCO = [
    (r"\b(update|delete\s+from)\s+[\"'`]?snap_", "reescreve snapshot — o histórico é imutável"),
    (r"\bdrop\s+table\b", "apaga tabela do banco"),
    (r"\bdelete\s+from\s+[\"'`]?(venda|alerta|tarifa_anuncio)\b", "apaga histórico de venda/alerta"),
]


def motivo(comando: str) -> str | None:
    baixo = comando.lower()
    for padrao, porque in ESCRITA_API:
        if re.search(padrao, baixo):
            return porque
    for padrao, porque in ESCRITA_BANCO:
        if re.search(padrao, baixo, re.IGNORECASE):
            return porque
    return None


def main() -> int:
    # O console do Windows abre em cp1252; sem isto um "não" no motivo derruba
    # o hook com UnicodeEncodeError — e hook que morre não trava nada.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    try:
        entrada = json.load(sys.stdin)
    except Exception:
        # Hook que não entende a entrada não pode travar o trabalho todo.
        return 0

    comando = ((entrada.get("tool_input") or {}).get("command")) or ""
    porque = motivo(comando)
    if not porque:
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                f"ESCRITA na conta do cliente: {porque}. "
                f"Confira o SLUG no comando antes de aprovar — operar a conta "
                f"errada é o erro mais caro deste repositório."
            ),
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
