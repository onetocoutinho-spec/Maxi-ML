"""
Diagnóstico automático de uma conta: os achados que valem dinheiro.

É a versão executável do raio-x. Não substitui a análise escrita — nenhuma
regra pega tudo — mas encontra sozinha os padrões que se repetem em conta
desorganizada, e serve de resumo para o Telegram.
"""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict

from . import db
from .utils import brl, truncar


def _agrupador(titulo: str, produto_catalogo: str | None) -> str:
    """
    Como decidir que dois anúncios são 'o mesmo produto'.

    Medida no título é o sinal mais forte em item sob medida (toldo, lona,
    cobertura). Depois, o produto de catálogo. Por último, as primeiras
    palavras — que erra mais, então só entra quando não há nada melhor.
    """
    m = re.search(r"(\d{2,3})\s*[xX×]\s*(\d{2,3})", titulo or "")
    if m:
        return f"medida {m.group(1)}x{m.group(2)}"
    if produto_catalogo:
        return f"catálogo {produto_catalogo}"
    return " ".join((titulo or "").lower().split()[:4])


def analisar(con: sqlite3.Connection, conta_slug: str) -> dict:
    u = db.ultima_coleta(con, "snap_anuncio", conta_slug)
    if not u:
        return {"erro": "sem coleta"}

    itens = con.execute(
        "SELECT * FROM snap_anuncio WHERE conta_slug = ? AND coletado_em = ?",
        (conta_slug, u),
    ).fetchall()
    if not itens:
        return {"erro": "sem coleta"}

    conta = con.execute(
        "SELECT * FROM snap_conta WHERE conta_slug = ? ORDER BY coletado_em DESC LIMIT 1",
        (conta_slug,),
    ).fetchone()

    # Visitas são coletadas uma vez por dia; o vigia, que roda a cada poucos
    # minutos, grava NULL nesse campo. Usar a coleta mais recente sem checar
    # isso zera a conversão e faz a conta parecer sem tráfego.
    carimbo_visitas = con.execute(
        "SELECT MAX(coletado_em) t FROM snap_anuncio "
        "WHERE conta_slug = ? AND visitas_7d IS NOT NULL", (conta_slug,)
    ).fetchone()["t"]
    visitas_por_item = {}
    if carimbo_visitas:
        visitas_por_item = {
            l["item_id"]: l["visitas_7d"] for l in con.execute(
                "SELECT item_id, visitas_7d FROM snap_anuncio "
                "WHERE conta_slug = ? AND coletado_em = ?",
                (conta_slug, carimbo_visitas))
        }

    def visitas_de(item_id) -> int:
        return visitas_por_item.get(item_id) or 0

    ativos = [i for i in itens if i["status"] == "active"]
    pausados = [i for i in itens if i["status"] == "paused"]

    # --- campeão de vendas e onde ele está ---
    campeao = max(itens, key=lambda i: i["vendidos"] or 0, default=None)
    campeao_parado = (campeao and campeao["status"] != "active")

    # --- dinheiro parado ---
    parados = [p for p in pausados if (p["estoque"] or 0) > 0]
    valor_parado = sum((p["preco"] or 0) * (p["estoque"] or 0) for p in parados)
    unidades_paradas = sum(p["estoque"] or 0 for p in parados)

    # --- ativo sem estoque: gasta exposição e não vende ---
    secos = [a for a in ativos if (a["estoque"] or 0) == 0]

    # --- canibalização ---
    grupos = defaultdict(list)
    for a in ativos:
        grupos[_agrupador(a["titulo"], a["produto_catalogo"])].append(a)
    canibais = {g: lista for g, lista in grupos.items() if len(lista) > 1}

    vendas_perdidas = []
    for g, lista in canibais.items():
        lista = sorted(lista, key=lambda i: -(i["vendidos"] or 0))
        vencedor, perdedores = lista[0], lista[1:]
        visitas_desperdicadas = sum(visitas_de(p["item_id"]) for p in perdedores)
        vendas_perdedores = sum(p["vendidos"] or 0 for p in perdedores)
        vendas_perdidas.append({
            "grupo": g, "anuncios": len(lista),
            "vencedor": vencedor["titulo"], "preco_vencedor": vencedor["preco"],
            "vendas_vencedor": vencedor["vendidos"] or 0,
            "vendas_outros": vendas_perdedores,
            "visitas_desperdicadas": visitas_desperdicadas,
            "vencedor_e_mais_caro": all(
                (vencedor["preco"] or 0) >= (p["preco"] or 0) for p in perdedores),
        })
    vendas_perdidas.sort(key=lambda c: -c["visitas_desperdicadas"])

    # --- conversão ---
    visitas = sum(visitas_de(a["item_id"]) for a in ativos)
    vendas_7d = (conta["vendas_7d"] or 0) if conta else 0
    conversao = (vendas_7d / visitas * 100) if visitas else None

    # --- catálogo: sozinho ou disputado ---
    uc = db.ultima_coleta(con, "snap_concorrente", conta_slug)
    disputados = set()
    if uc:
        disputados = {
            l["comparar_com"] for l in con.execute(
                "SELECT DISTINCT comparar_com FROM snap_concorrente "
                "WHERE conta_slug = ? AND coletado_em = ? AND origem = 'confronto' "
                "AND comparar_com IS NOT NULL", (conta_slug, uc))
        }
    de_catalogo = [a for a in ativos if a["produto_catalogo"]]
    sozinho = [a for a in de_catalogo if a["item_id"] not in disputados]

    return {
        "nickname": conta["nickname"] if conta else conta_slug,
        "apelido_automatico": bool(conta and re.fullmatch(
            r"[A-Z]{2}\d{10,}", conta["nickname"] or "")),
        "total": len(itens), "ativos": len(ativos), "pausados": len(pausados),
        "vendas_7d": vendas_7d, "receita_7d": (conta["receita_7d"] if conta else 0) or 0,
        "visitas_7d": visitas, "conversao": conversao,
        "visitas_de": carimbo_visitas,
        "nivel": conta["nivel"] if conta else None,
        "campeao": dict(campeao) if campeao else None,
        "campeao_parado": campeao_parado,
        "parados": len(parados), "unidades_paradas": unidades_paradas,
        "valor_parado": valor_parado,
        "secos": [dict(s) for s in secos],
        "canibalizacao": vendas_perdidas,
        "catalogo_total": len(de_catalogo), "catalogo_sozinho": len(sozinho),
    }


def texto_para_telegram(r: dict) -> str:
    if r.get("erro"):
        return f"*Raio-X* — {r['erro']}. Rode uma coleta primeiro."

    L = [f"*Raio-X — {r['nickname']}*", ""]
    L.append(f"{r['ativos']} ativos · {r['pausados']} pausados · "
             f"{r['vendas_7d']} vendas em 7d ({brl(r['receita_7d'])})")
    if r["conversao"] is not None and r["visitas_7d"]:
        L.append(f"{r['visitas_7d']} visitas → conversão {r['conversao']:.2f}%")
    else:
        L.append("_visitas ainda não coletadas — a leitura sai uma vez por dia_")
    L.append("")

    achados = []

    if r["campeao_parado"] and r["campeao"]:
        c = r["campeao"]
        achados.append(
            f"🔴 *Campeão fora do ar* — {truncar(c['titulo'], 40)} tem "
            f"{c['vendidos']} vendas, o maior giro da conta, e está "
            f"{c['status']}" + (f" ({c['sub_status']})" if c['sub_status'] else ""))

    if r["secos"]:
        achados.append(f"🔴 *{len(r['secos'])} anúncio(s) ativos sem estoque* — "
                       f"gastam exposição e não vendem")

    if r["canibalizacao"]:
        pior = r["canibalizacao"][0]
        extra = " e o que vende é o mais caro" if pior["vencedor_e_mais_caro"] else ""
        achados.append(
            f"🔴 *Canibalização em {len(r['canibalizacao'])} grupo(s)* — no pior "
            f"({pior['grupo']}) são {pior['anuncios']} anúncios; os perdedores "
            f"somam {pior['visitas_desperdicadas']} visitas e "
            f"{pior['vendas_outros']} vendas{extra}")

    if r["parados"]:
        achados.append(f"🟡 *{r['parados']} pausados com estoque* — "
                       f"{r['unidades_paradas']} unidades, {brl(r['valor_parado'])} parados")

    if r["catalogo_total"] and r["catalogo_sozinho"] == r["catalogo_total"]:
        achados.append(f"🟡 *Sem disputa no catálogo* — único vendedor nos "
                       f"{r['catalogo_total']} produtos. O buy box não é vitória "
                       f"de preço, é ausência de concorrente")

    if r["apelido_automatico"]:
        achados.append(f"🟡 *Apelido automático* — a loja aparece como "
                       f"{r['nickname']} em toda pergunta e página de produto")

    if not achados:
        achados.append("Nenhum achado crítico. Conta em ordem.")

    L.extend(achados)
    return "\n".join(L)
