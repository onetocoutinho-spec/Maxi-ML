"""
Confrontos: quem disputa cada produto de catálogo da conta.

Separado dos demais coletores porque é caro — uma consulta de ofertas por
produto, mais uma de perfil por vendedor novo, mais uma de frete por anúncio.
Roda uma vez por dia, não a cada 3 horas.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from . import db
from .config import Conta
from .ml_api import MLClient
from .utils import pct


def mapear(con: sqlite3.Connection, conta: Conta, cli: MLClient, carimbo: str,
           cep: str = "01001000", com_frete: bool = True,
           progresso=None) -> dict:
    """
    Devolve {'confrontos': [...], 'por_vendedor': {...}, 'perfis': {...}}
    e grava as ofertas concorrentes como origem='confronto', já vinculadas
    ao anúncio seu correspondente.
    """
    ultimo = db.ultima_coleta(con, "snap_anuncio", conta.slug)
    if not ultimo:
        return {"erro": "nenhuma coleta de anúncios ainda"}

    meus = con.execute(
        "SELECT item_id, titulo, preco, produto_catalogo, frete_gratis, vendidos "
        "FROM snap_anuncio WHERE conta_slug = ? AND coletado_em = ? "
        "AND produto_catalogo IS NOT NULL AND status = 'active' ORDER BY vendidos DESC",
        (conta.slug, ultimo),
    ).fetchall()

    perfis: dict[str, dict] = {}
    por_vendedor = defaultdict(lambda: {"produtos": 0, "vitorias": 0,
                                        "diffs": [], "fretes": [], "itens": []})
    confrontos, linhas = [], []
    sozinho, disputados, sem_resposta = [], [], []

    for indice, meu in enumerate(meus, start=1):
        if progresso:
            progresso(indice, len(meus), meu["titulo"])
        try:
            ofertas = cli.vendedores_do_produto(meu["produto_catalogo"], limite=25)
        except Exception:
            sem_resposta.append(dict(meu))
            continue

        # Link da ficha, perguntado à API — nunca montado a partir do ID.
        try:
            link_ficha = cli.link_do_produto(meu["produto_catalogo"])
        except Exception:
            link_ficha = None

        rivais = []
        for oferta in ofertas:
            sid = str(oferta.get("seller_id") or "")
            if not sid or sid == cli.user_id:
                continue
            if sid not in perfis:
                try:
                    perfis[sid] = cli.perfil_do_vendedor(sid)
                except Exception:
                    perfis[sid] = {"seller_id": sid, "nickname": sid}

            frete = None
            if com_frete and oferta.get("item_id"):
                try:
                    frete = cli.frete_do_item(oferta["item_id"], cep)
                except Exception:
                    frete = None

            envio = oferta.get("shipping") or {}
            preco = oferta.get("price")
            custo = (frete or {}).get("custo")

            rival = {
                "seller_id": sid, "nickname": perfis[sid].get("nickname") or sid,
                "item_id": oferta.get("item_id"), "preco": preco,
                "frete_gratis": bool(envio.get("free_shipping")),
                "frete_custo": custo, "total": (preco or 0) + (custo or 0),
                "prazo_dias": (frete or {}).get("prazo_dias"),
                "vendidos": oferta.get("sold_quantity"),
                "estoque": oferta.get("available_quantity"),
                "nivel": perfis[sid].get("nivel"),
                "loja_oficial": perfis[sid].get("loja_oficial"),
                "cidade": perfis[sid].get("cidade"),
                "estado": perfis[sid].get("estado"),
                "permalink": oferta.get("permalink") or link_ficha,
            }
            rivais.append(rival)

            linhas.append({
                "coletado_em": carimbo, "cliente_id": conta.cliente_id,
                "conta_slug": conta.slug, "origem": "confronto",
                "referencia": meu["item_id"], "item_id": oferta.get("item_id"),
                "titulo": meu["titulo"], "preco": preco,
                "vendidos": oferta.get("sold_quantity"), "seller_id": sid,
                "seller_nickname": perfis[sid].get("nickname"),
                "frete_gratis": int(bool(envio.get("free_shipping"))),
                "posicao": None, "catalogo": 1,
                "permalink": oferta.get("permalink"),
                "comparar_com": meu["item_id"],
            })

        if not rivais:
            # Não é erro: significa que você é o ÚNICO vendedor deste produto
            # de catálogo. É informação de mercado, não ausência de dado.
            sozinho.append(dict(meu))
            continue
        disputados.append(dict(meu))
        rivais.sort(key=lambda r: r["total"] or 9e9)
        confrontos.append({"meu": dict(meu), "rivais": rivais})

        for r in rivais:
            v = por_vendedor[r["seller_id"]]
            v["produtos"] += 1
            v["itens"].append(r)
            if (r["preco"] or 9e9) < (meu["preco"] or 0):
                v["vitorias"] += 1
            d = pct(r["preco"], meu["preco"])
            if d is not None:
                v["diffs"].append(d)
            if r["frete_custo"] is not None:
                v["fretes"].append(r["frete_custo"])

    db.inserir_muitos(con, "snap_concorrente", linhas)
    con.commit()

    return {"confrontos": confrontos, "por_vendedor": dict(por_vendedor),
            "perfis": perfis, "gravados": len(linhas), "produtos": len(meus),
            "sozinho": sozinho, "disputados": disputados,
            "sem_resposta": sem_resposta}


def resumo_semanal(con: sqlite3.Connection, conta_slug: str) -> str:
    """Texto curto sobre o que mudou na concorrência nos últimos 7 dias."""
    linhas = ["*Concorrência — últimos 7 dias*", ""]

    ameacas = con.execute(
        "SELECT seller_nickname, COUNT(DISTINCT referencia) produtos, "
        "       ROUND(AVG(preco),2) preco_medio "
        "FROM snap_concorrente "
        "WHERE conta_slug = ? AND origem = 'confronto' "
        "  AND coletado_em >= datetime('now','-7 days') "
        "GROUP BY seller_id ORDER BY produtos DESC LIMIT 5",
        (conta_slug,),
    ).fetchall()

    if not ameacas:
        return ""

    linhas.append("Quem mais disputa seus produtos:")
    for a in ameacas:
        linhas.append(f"· {a['seller_nickname']} — {a['produtos']} produto(s)")

    novos = con.execute(
        "SELECT DISTINCT seller_nickname FROM snap_concorrente "
        "WHERE conta_slug = ? AND origem = 'confronto' "
        "  AND coletado_em >= datetime('now','-2 days') "
        "  AND seller_id NOT IN ("
        "     SELECT DISTINCT seller_id FROM snap_concorrente "
        "     WHERE conta_slug = ? AND origem = 'confronto' "
        "       AND coletado_em < datetime('now','-2 days'))",
        (conta_slug, conta_slug),
    ).fetchall()
    if novos:
        linhas.append("")
        linhas.append(f"Entraram agora ({len(novos)}): "
                      + ", ".join(n["seller_nickname"] or "?" for n in novos[:6]))

    return "\n".join(linhas)
