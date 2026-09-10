#!/usr/bin/env python3
"""
Teste de fumaça com dados simulados — NÃO toca no Mercado Livre.

Gera dois snapshots (ontem e hoje) para as contas do registro, roda o motor
de regras e gera os relatórios. Serve para validar a instalação antes de você
ter credencial, e para ver como o painel fica com dados dentro.

  python scripts/teste_simulado.py            # semeia e roda
  python scripts/teste_simulado.py --limpar   # apaga o banco de teste depois
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows: quando a saída vai para arquivo (log da rotina agendada), o Python
# usa a codificação local (cp1252) e quebra em acento ou símbolo. Forçar UTF-8
# aqui evita UnicodeEncodeError derrubar a coleta no meio.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core import db, report, rules
from core.config import carregar_clientes, obter_conta

ONTEM = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
HOJE = datetime.now(timezone.utc).isoformat(timespec="seconds")


def semear_conta(con, conta, carimbo, dia: int):
    """dia=0 é ontem, dia=1 é hoje (com as mudanças que devem virar alerta)."""
    base = [
        # (item_id, titulo, preco0, preco1, estoque0, estoque1, vendidos0, vendidos1, status1)
        ("MLB100", "Babuche Feminino Antiderrapante Preto 37", 79.90, 71.90, 12, 8, 140, 149, "active"),
        ("MLB101", "Babuche Masculino Conforto Marrom 41", 89.90, 89.90, 3, 0, 61, 61, "active"),
        ("MLB102", "Chinelo Slide Feminino Nude 38", 59.90, 59.90, 40, 39, 205, 206, "paused"),
        ("MLB103", "Babuche Profissional Branco 39", 99.90, 109.90, 25, 22, 88, 91, "active"),
        ("MLB104", "Sandália Papete Feminina Caramelo 36", 119.90, 119.90, 2, 2, 12, 12, "active"),
    ]
    linhas = []
    for (iid, titulo, p0, p1, e0, e1, v0, v1, st1) in base:
        linhas.append({
            "coletado_em": carimbo, "cliente_id": conta.cliente_id, "conta_slug": conta.slug,
            "item_id": iid, "titulo": titulo,
            "preco": p1 if dia else p0, "preco_original": None,
            "estoque": e1 if dia else e0, "vendidos": v1 if dia else v0,
            "status": st1 if dia else "active", "sub_status": "" if dia else "",
            "tipo_anuncio": "gold_special", "catalogo": 0, "produto_catalogo": None,
            "categoria": "MLB108704", "saude": 0.92,
            "frete_gratis": 1, "visitas_7d": 320 if dia else 410,
            "permalink": f"https://produto.mercadolivre.com.br/{iid}",
        })
    db.inserir_muitos(con, "snap_anuncio", linhas)

    # posição própria e concorrentes por termo
    for entrada in (conta.palavras_chave or [{"termo": "termo teste"}]):
        termo = entrada["termo"] if isinstance(entrada, dict) else str(entrada)
        minha_pos = 4 if dia else 2
        db.inserir(con, "snap_posicao", {
            "coletado_em": carimbo, "cliente_id": conta.cliente_id, "conta_slug": conta.slug,
            "termo": termo, "item_id": "MLB100", "posicao": minha_pos,
            "preco": 71.90 if dia else 79.90, "preco_topo": 64.90, "total_result": 30,
        })
        concorrentes = [
            ("MLB900", "Babuche Feminino Similar Preto", 64.90 if dia else 82.90, "lojaconcorrente1", 1, 900),
            ("MLB901", "Babuche Antiderrapante Conforto", 69.90 if dia else 84.90, "calcadosbrasil", 2, 310),
            ("MLB902", "Babuche Profissional Cozinha", 88.00, "novaloja2026" if dia else "lojaantiga", 3, 45),
        ]
        db.inserir_muitos(con, "snap_concorrente", [{
            "coletado_em": carimbo, "cliente_id": conta.cliente_id, "conta_slug": conta.slug,
            "origem": "palavra-chave", "referencia": termo, "item_id": iid, "titulo": t,
            "preco": p, "vendidos": vend, "seller_id": nick, "seller_nickname": nick,
            "frete_gratis": 1, "posicao": pos, "catalogo": 0,
            "permalink": f"https://produto.mercadolivre.com.br/{iid}",
        } for (iid, t, p, nick, pos, vend) in concorrentes])

    db.inserir(con, "snap_conta", {
        "coletado_em": carimbo, "cliente_id": conta.cliente_id, "conta_slug": conta.slug,
        "nickname": conta.nome_conta.upper().replace(" ", ""),
        "nivel": "4_light_green" if dia else "5_green",
        "power_seller": "gold", "transacoes": 1840,
        "reclamacoes_pct": 0.012, "cancelamentos_pct": 0.004, "atrasos_pct": 0.03,
        "anuncios_ativos": 4, "anuncios_pausados": 1,
        "vendas_7d": 37, "receita_7d": 3128.40,
    })


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limpar", action="store_true")
    a = p.parse_args()

    con = db.conectar()
    con.executescript(
        "DELETE FROM snap_anuncio; DELETE FROM snap_concorrente; DELETE FROM snap_posicao;"
        "DELETE FROM snap_conta; DELETE FROM alerta; DELETE FROM execucao;"
    )
    con.commit()

    clientes = carregar_clientes()
    contas = [c for cl in clientes for c in cl.contas]
    print(f"Semeando {len(contas)} conta(s)…")

    for conta in contas:
        semear_conta(con, conta, ONTEM, dia=0)
        semear_conta(con, conta, HOJE, dia=1)
    con.commit()

    total = 0
    for conta in contas:
        # Dois casos, porque o motor trata cada um por uma regra diferente:
        # vencedor de fora vira perdeu_buy_box, vencedor da casa vira
        # canibalizacao_interna. O campo é `vencedor_slug` e não seller: a API
        # do ML identifica o vencedor só pelo item_id (ver coletar_buy_box).
        buy_box = [{"item_id": "MLB103", "titulo": "Babuche Profissional Branco 39",
                    "meu_preco": 109.90, "status": "competing",
                    "preco_para_ganhar": 104.50, "preco_vencedor": 104.00,
                    "vencedor_item": "MLB999", "vencedor_slug": None,
                    "vencedor_apelido": "CONCORRENTE-TESTE", "ficha": "MLB70000001"},
                   {"item_id": "MLB104", "titulo": "Sandália Papete Feminina Caramelo 36",
                    "meu_preco": 119.90, "status": "competing",
                    "preco_para_ganhar": 111.00, "preco_vencedor": 112.00,
                    "vencedor_item": "MLB998", "vencedor_slug": "outra-conta-da-casa",
                    "vencedor_apelido": "IRMA-TESTE", "ficha": "MLB70000002"}]
        n = rules.avaliar(con, conta, HOJE, buy_box=buy_box)
        print(f"  {conta.slug:<24} {n} alertas")
        total += n

    print(f"\nTotal: {total} alertas")
    print("\n--- resumo em texto ---")
    print(report.resumo_texto(con, 24))

    caminhos = report.gerar(con)
    print("\n--- relatórios ---")
    for c in caminhos:
        print(f"  {c}")

    con.close()

    if a.limpar:
        from core.db import CAMINHO_BANCO
        CAMINHO_BANCO.unlink(missing_ok=True)
        print("\nBanco de teste removido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
