"""
Quanto o Mercado Livre cobra POR ANÚNCIO, perguntado a ele.

Existe porque `conta.yaml` guarda a comissão como dois números fixos
(gold_special 12%, gold_pro 17%) e isso é uma aproximação. A comissão real
varia por CATEGORIA — a mesma conta paga percentuais diferentes em toldo e
em móvel — e ainda leva uma taxa fixa por unidade quando o preço é baixo.
Precificar em cima do número aproximado erra na direção perigosa: para menos.

/sites/MLB/listing_prices devolve o valor exato que será descontado de uma
venda daquele preço, naquela categoria, naquele tipo de anúncio. É o mesmo
número que aparece na simulação da página do vendedor.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from . import db
from .utils import agora_iso


def _percentual(taxa: float | None, preco: float | None) -> float | None:
    if not taxa or not preco:
        return None
    return taxa / preco * 100


def levantar(con: sqlite3.Connection, conta, cli) -> tuple[list[dict], str | None]:
    """
    Para cada anúncio ativo da última coleta, pergunta a tarifa ao ML.

    Devolve (linhas, carimbo). Cada linha traz o que o ML respondeu e o que
    o conta.yaml supunha, lado a lado — a diferença entre os dois é o ponto.
    """
    carimbo = db.ultima_coleta(con, "snap_anuncio", conta.slug)
    if not carimbo:
        return [], None

    anuncios = con.execute(
        "SELECT * FROM snap_anuncio WHERE conta_slug = ? AND coletado_em = ? "
        "AND status = 'active' ORDER BY vendidos DESC",
        (conta.slug, carimbo)).fetchall()

    supostas = ((conta.parametros or {}).get("comissao") or {})
    linhas: list[dict] = []

    for a in anuncios:
        preco = a["preco_vitrine"] if _tem(a, "preco_vitrine") and a["preco_vitrine"] else a["preco"]
        tipo = a["tipo_anuncio"]
        categoria = a["categoria"]
        if not preco or not tipo or not categoria:
            continue

        resposta = cli.tarifa_de_venda(preco, categoria, tipo) or {}
        detalhe = resposta.get("sale_fee_details") or {}
        taxa = resposta.get("sale_fee_amount")

        suposta = supostas.get(tipo)
        linhas.append({
            "item_id": a["item_id"],
            "titulo": a["titulo"],
            "preco": float(preco),
            "tipo": tipo,
            "categoria": categoria,
            "frete_gratis": bool(a["frete_gratis"]),
            "taxa_reais": float(taxa) if isinstance(taxa, (int, float)) else None,
            "taxa_pct": _percentual(taxa, preco),
            "percentual_ml": detalhe.get("percentage_fee"),
            "fixa_reais": detalhe.get("fixed_fee"),
            "suposta_pct": (float(suposta) * 100) if suposta is not None else None,
            "vendidos": a["vendidos"] or 0,
        })

    _guardar(con, conta.slug, linhas)
    return linhas, carimbo


def _guardar(con: sqlite3.Connection, slug: str, linhas: list[dict]) -> int:
    """
    Persiste a medição para que o cálculo de piso a use sem chamar a API.

    Medição nova = linha nova, como todo snapshot deste sistema. Assim dá
    para ver quando o Mercado Livre mexeu na tabela dele.
    """
    agora = agora_iso()
    registros = [{
        "medido_em": agora, "conta_slug": slug, "item_id": l["item_id"],
        "categoria": l["categoria"], "tipo_anuncio": l["tipo"],
        "preco_base": l["preco"],
        "taxa_pct": (l["taxa_pct"] / 100.0) if l["taxa_pct"] is not None else None,
        "taxa_fixa": l["fixa_reais"] or 0.0,
    } for l in linhas if l["taxa_reais"] is not None]
    if not registros:
        return 0
    n = db.inserir_muitos(con, "tarifa_anuncio", registros)
    con.commit()
    return n


def _tem(linha: sqlite3.Row, coluna: str) -> bool:
    try:
        return coluna in linha.keys()
    except Exception:
        return False


def media_ponderada(linhas: list[dict]) -> dict[str, Any]:
    """
    A taxa média que a conta paga, ponderada por VENDAS, não por anúncio.

    Ponderar por anúncio dá o número errado de propósito: um anúncio parado
    numa categoria barata puxaria a média para baixo sem nunca ter gerado
    uma venda. O que importa é o percentual sobre o dinheiro que entra.
    """
    peso_total = 0.0
    taxa_total = 0.0
    receita_total = 0.0
    for l in linhas:
        if l["taxa_reais"] is None:
            continue
        peso = max(l["vendidos"], 0) or 0
        if peso:
            receita_total += l["preco"] * peso
            taxa_total += l["taxa_reais"] * peso
            peso_total += peso
    simples = [l["taxa_pct"] for l in linhas if l["taxa_pct"] is not None]
    return {
        "por_venda_pct": (taxa_total / receita_total * 100) if receita_total else None,
        "vendas_consideradas": int(peso_total),
        "por_anuncio_pct": (sum(simples) / len(simples)) if simples else None,
        "menor_pct": min(simples) if simples else None,
        "maior_pct": max(simples) if simples else None,
    }
