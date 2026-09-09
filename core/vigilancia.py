"""
Vigilância de concorrentes: o que ELES mudaram desde a rodada anterior.

DESCOBERTA QUE DEFINE ESTE MÓDULO
---------------------------------
O Mercado Livre NÃO permite ler um anúncio de terceiro por ID. Tanto
`/items/{id}` quanto o multiget `/items?ids=` devolvem `access_denied` (403)
para anúncio que não é seu. Confirmado com um controle: até um anúncio que o
sistema lê normalmente pela ficha de catálogo é recusado quando pedido por ID.

O que CONTINUA liberado é `/products/{id}/items` — as ofertas de um produto de
catálogo, com preço, vendedor e frete grátis de cada uma.

Então a vigilância não observa anúncios: observa PRODUTOS DE CATÁLOGO, e lê as
ofertas de cada um a cada rodada. Consequência prática, que precisa estar clara
para quem opera: concorrente que vende fora do catálogo pode ser DESCOBERTO
(pela busca web), mas não pode ser ACOMPANHADO pela API oficial.
"""
from __future__ import annotations

import re
import sqlite3

from . import db
from .config import Conta
from .ml_api import MLClient


def _produtos_para_vigiar(con: sqlite3.Connection, conta: Conta) -> dict[str, dict]:
    """
    product_id -> {rotulo, comparar_com}

    Duas origens:
      1. as fichas que você mandou vigiar em concorrentes.yaml
      2. os produtos de catálogo dos seus próprios anúncios — onde o
         concorrente pode entrar a qualquer momento
    """
    alvos: dict[str, dict] = {}

    for entrada in conta.produtos_vigiados:
        bruto = str(entrada.get("produto") or entrada.get("link") or "").upper()
        m = re.search(r"(ML[A-Z]?\d{6,})", bruto.replace("-", ""))
        if not m:
            continue
        alvo = str(entrada.get("comparar_com") or "").upper().replace("-", "")
        ma = re.search(r"(ML[A-Z]?\d{6,})", alvo)
        alvos[m.group(1)] = {"rotulo": entrada.get("apelido") or m.group(1),
                             "comparar_com": ma.group(1) if ma else None}

    ultimo = db.ultima_coleta(con, "snap_anuncio", conta.slug)
    if ultimo:
        for l in con.execute(
            "SELECT produto_catalogo, item_id, titulo FROM snap_anuncio "
            "WHERE conta_slug = ? AND coletado_em = ? AND produto_catalogo IS NOT NULL "
            "AND status = 'active'", (conta.slug, ultimo)
        ):
            alvos.setdefault(l["produto_catalogo"],
                             {"rotulo": l["titulo"], "comparar_com": l["item_id"]})

    return alvos


def vigiar(con: sqlite3.Connection, conta: Conta, cli: MLClient, carimbo: str,
           cep: str = "01001000", max_frete: int = 40) -> dict:
    alvos = _produtos_para_vigiar(con, conta)
    if not alvos:
        return {"itens": 0, "fretes": 0,
                "aviso": "nenhum produto de catálogo para vigiar — rode uma coleta"}

    apelidos = dict(con.execute(
        "SELECT seller_id, seller_nickname FROM snap_concorrente "
        "WHERE conta_slug = ? AND seller_nickname IS NOT NULL GROUP BY seller_id",
        (conta.slug,)).fetchall())

    linhas, n_frete, produtos_lidos = [], 0, 0

    for product_id, meta in alvos.items():
        try:
            ofertas = cli.vendedores_do_produto(product_id, limite=25)
        except Exception:
            continue
        produtos_lidos += 1

        # O link é o da FICHA, perguntado à API. Ver core/ml_api.link_do_produto:
        # inventar endereço de anúncio a partir do ID gera página inexistente.
        link_ficha = None
        try:
            link_ficha = cli.link_do_produto(product_id)
        except Exception:
            link_ficha = None

        for oferta in ofertas:
            seller_id = str(oferta.get("seller_id") or "")
            if not seller_id or seller_id == cli.user_id:
                continue

            if seller_id not in apelidos:
                try:
                    apelidos[seller_id] = cli.apelido_do_vendedor(seller_id) or seller_id
                except Exception:
                    apelidos[seller_id] = seller_id

            custo = None
            if n_frete < max_frete and oferta.get("item_id"):
                try:
                    custo = (cli.frete_do_item(oferta["item_id"], cep) or {}).get("custo")
                    n_frete += 1
                except Exception:
                    custo = None

            envio = oferta.get("shipping") or {}
            linhas.append({
                "coletado_em": carimbo, "cliente_id": conta.cliente_id,
                "conta_slug": conta.slug, "origem": "vigilancia",
                "referencia": meta["rotulo"], "item_id": oferta.get("item_id"),
                "titulo": meta["rotulo"], "preco": oferta.get("price"),
                "vendidos": oferta.get("sold_quantity"), "seller_id": seller_id,
                "seller_nickname": apelidos.get(seller_id),
                "frete_gratis": int(bool(envio.get("free_shipping"))),
                "posicao": None, "catalogo": 1,
                "permalink": oferta.get("permalink") or link_ficha,
                "comparar_com": meta["comparar_com"],
                "frete_custo": custo,
                "estoque": oferta.get("available_quantity"),
                "status": "active",
            })

    db.inserir_muitos(con, "snap_concorrente", linhas)
    con.commit()
    return {"itens": len(linhas), "fretes": n_frete, "produtos": produtos_lidos}
