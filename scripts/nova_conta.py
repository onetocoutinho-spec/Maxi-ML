#!/usr/bin/env python3
"""
Cria a pasta de uma nova conta a partir do template e já preenche o CLAUDE.md.

Uso:
  python scripts/nova_conta.py <slug> --cliente <cliente_id> --nome "Nome da Conta" \
      [--user-id 123456789] [--papel principal]

Depois: preencha o .env e adicione a conta em config/clientes.yaml
(o script imprime o bloco YAML pronto para colar).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Windows: quando a saída vai para arquivo (log da rotina agendada), o Python
# usa a codificação local (cp1252) e quebra em acento ou símbolo. Forçar UTF-8
# aqui evita UnicodeEncodeError derrubar a coleta no meio.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

RAIZ = Path(__file__).resolve().parent.parent
TEMPLATE = RAIZ / "contas" / "_template"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("slug")
    p.add_argument("--cliente", required=True)
    p.add_argument("--nome", required=True)
    p.add_argument("--user-id", default="SUBSTITUIR")
    p.add_argument("--papel", default="principal")
    a = p.parse_args()

    destino = RAIZ / "contas" / a.slug
    if destino.exists():
        print(f"A pasta contas/{a.slug} ja existe.")
        return 1

    shutil.copytree(TEMPLATE, destino)

    claude = destino / "CLAUDE.md"
    texto = claude.read_text(encoding="utf-8")
    for chave, valor in {
        "{{SLUG}}": a.slug,
        "{{NOME_DA_CONTA}}": a.nome,
        "{{CLIENTE}}": a.cliente,
        "{{CLIENTE_ID}}": a.cliente,
        "{{USER_ID}}": a.user_id,
        "{{PAPEL}}": a.papel,
        "{{REGRAS_DO_NEGOCIO}}": "_(preencher: modelo de anuncio, categoria, politica de preco)_",
    }.items():
        texto = texto.replace(chave, valor)
    claude.write_text(texto, encoding="utf-8")

    print(f"Criada: contas/{a.slug}/")
    print("\n1) Preencha a credencial:")
    print(f"   cp contas/{a.slug}/.env.example contas/{a.slug}/.env")
    print(f"   chmod 600 contas/{a.slug}/.env")
    print("\n2) Cole este bloco na conta certa em config/clientes.yaml:\n")
    print(f"""      - slug: {a.slug}
        nome_conta: "{a.nome}"
        site_id: MLB
        user_id: "{a.user_id}"
        papel: {a.papel}""")
    print(f"\n3) Valide:  python cli.py checar {a.slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
