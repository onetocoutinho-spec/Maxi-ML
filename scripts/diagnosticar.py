#!/usr/bin/env python3
"""
Descobre o que a API do Mercado Livre ainda libera para o SEU app.

O ML vem restringindo endpoints sem aviso — a busca pública (/sites/MLB/search)
foi bloqueada para aplicações em geral. Em vez de eu adivinhar o que funciona,
este script pergunta para a API, com o seu token, e mostra o que passou.

  python scripts/diagnosticar.py <slug>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests

from core.config import obter_conta
from core.ml_api import BASE, MLClient
from core.utils import cor

VERDE, VERM, AMAR, CINZA, FIM = (
    cor("\033[32m"), cor("\033[31m"), cor("\033[33m"), cor("\033[90m"), cor("\033[0m")
)


def testar(cli: MLClient, rotulo: str, caminho: str, params: dict | None = None,
           serve_para: str = "") -> tuple[str, int, str]:
    url = f"{BASE}{caminho}"
    try:
        r = cli.sessao.get(url, headers=cli._headers(), params=params, timeout=30)
        codigo = r.status_code
        amostra = ""
        if codigo == 200:
            try:
                dados = r.json()
                if isinstance(dados, dict):
                    n = len(dados.get("results", dados.get("content", [])) or [])
                    amostra = f"{n} resultados" if n else "ok"
                elif isinstance(dados, list):
                    amostra = f"{len(dados)} itens"
                else:
                    amostra = "ok"
            except Exception:
                amostra = "ok"
        else:
            amostra = r.text[:90].replace("\n", " ")
    except Exception as erro:
        codigo, amostra = 0, str(erro)[:90]

    if codigo == 200:
        marca, cor_ = "OK  ", VERDE
    elif codigo in (401, 403):
        marca, cor_ = "BLOQ", VERM
    elif codigo == 404:
        marca, cor_ = "404 ", AMAR
    else:
        marca, cor_ = f"{codigo:<4}", AMAR

    print(f"  {cor_}[{marca}]{FIM} {rotulo}")
    if serve_para:
        print(f"         {CINZA}{serve_para}{FIM}")
    if codigo != 200:
        print(f"         {CINZA}{amostra}{FIM}")
    return rotulo, codigo, amostra


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("slug")
    a = p.parse_args()

    conta = obter_conta(a.slug)
    cli = MLClient(conta.slug, user_id_esperado=conta.user_id)

    print(f"\n{CINZA}Conta {conta} · user_id {cli.user_id}{FIM}")
    print(f"{CINZA}{'─' * 66}{FIM}\n")

    resultados = []

    # o que já sabemos que funciona
    resultados.append(testar(cli, "Meus anúncios", f"/users/{cli.user_id}/items/search",
                             {"search_type": "scan", "limit": 1},
                             "preço, estoque, vendas e status dos anúncios próprios"))
    resultados.append(testar(cli, "Dados da conta", f"/users/{cli.user_id}",
                             None, "reputação, nível, métricas"))

    # pega um item e uma categoria reais para os testes seguintes
    item_id = categoria = produto_catalogo = None
    dados = cli.get(f"/users/{cli.user_id}/items/search", search_type="scan", limit=5) or {}
    ids = dados.get("results", [])
    if ids:
        for it in cli.detalhes_dos_itens(ids[:5]):
            item_id = item_id or it.get("id")
            categoria = categoria or it.get("category_id")
            if it.get("catalog_product_id"):
                produto_catalogo = it["catalog_product_id"]

    if item_id:
        resultados.append(testar(cli, "Visitas do anúncio", f"/items/{item_id}/visits/time_window",
                                 {"last": 7, "unit": "day"}, "conversão: visitas x vendas"))
        resultados.append(testar(cli, "Buy box (price_to_win)", f"/items/{item_id}/price_to_win",
                                 None, "ganhar/perder catálogo — só vale para item de catálogo"))

    resultados.append(testar(cli, "Pedidos", "/orders/search",
                             {"seller": cli.user_id, "limit": 1}, "receita e velocidade de venda"))

    print(f"\n{CINZA}── concorrência ──{FIM}\n")

    resultados.append(testar(cli, "Busca pública por termo", "/sites/MLB/search",
                             {"q": "toldo", "limit": 1},
                             "era a base do rastreio por palavra-chave"))
    resultados.append(testar(cli, "Busca por vendedor", "/sites/MLB/search",
                             {"seller_id": cli.user_id, "limit": 1},
                             "rastrear o catálogo inteiro de um concorrente"))
    resultados.append(testar(cli, "Busca no catálogo", "/products/search",
                             {"site_id": "MLB", "status": "active", "q": "toldo retrátil"},
                             "achar produtos de catálogo por termo"))

    if produto_catalogo:
        resultados.append(testar(cli, "Vendedores de um produto de catálogo",
                                 f"/products/{produto_catalogo}/items", None,
                                 "todos os concorrentes e preços de um produto"))
    else:
        print(f"  {CINZA}[----] Vendedores de produto de catálogo — "
              f"nenhum anúncio de catálogo nesta conta para testar{FIM}")

    if categoria:
        resultados.append(testar(cli, "Mais vendidos da categoria",
                                 f"/highlights/MLB/category/{categoria}", None,
                                 "descobrir quem vende mais na sua categoria"))
        resultados.append(testar(cli, "Tendências de busca", f"/trends/MLB/{categoria}",
                                 None, "termos em alta na categoria"))

    liberados = [r for r in resultados if r[1] == 200]
    bloqueados = [r for r in resultados if r[1] in (401, 403)]

    print(f"\n{CINZA}{'─' * 66}{FIM}")
    print(f"  {VERDE}liberados: {len(liberados)}{FIM}   "
          f"{VERM}bloqueados: {len(bloqueados)}{FIM}   "
          f"de {len(resultados)} testados")
    if bloqueados:
        print(f"\n{AMAR}Bloqueados:{FIM} " + ", ".join(r[0] for r in bloqueados))
    print(f"\n{CINZA}Mande este resultado para o Claude ajustar a coleta ao que existe.{FIM}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ncancelado")
        sys.exit(130)
