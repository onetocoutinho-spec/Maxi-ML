"""
Campanhas do Mercado Livre: o que está liberado para cada anúncio.

O Mercado Livre abre campanhas o tempo todo e oferece cada uma anúncio por
anúncio, com um preço já calculado. No aplicativo isso aparece como um botão
de aceitar, sem nenhuma menção a custo — e é assim que um anúncio saudável
vira um anúncio no prejuízo em dois toques.

Este módulo lê o que está liberado e cruza com o piso de preço. O objetivo não
é impedir promoção: é que a decisão seja tomada sabendo quanto sobra.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from . import db
from .utils import agora_iso

# 'candidate' = liberada e ainda não aceita. É a que gera decisão.
# 'started'   = já rodando; serve para explicar o preço de vitrine de hoje.
INTERESSANTES = ("candidate", "started", "pending")

# Nome que o vendedor reconhece. A API devolve o rótulo interno, e "LIGHTNING"
# numa mensagem de Telegram não diz nada a quem opera a loja.
NOMES = {
    "LIGHTNING": "oferta relâmpago",
    "DEAL": "oferta do dia",
    "PRICE_DISCOUNT": "desconto no preço",
    "MARKETPLACE_CAMPAIGN": "campanha do Mercado Livre",
    "SELLER_CAMPAIGN": "campanha sua",
    "SMART": "campanha do Mercado Livre",
    "PRICE_MATCHING": "igualar preço",
}

# Campanhas que NÃO mexem no preço da vitrine. Cupom é desconto de CARRINHO:
# o anúncio segue no mesmo preço e a API devolve `price: 0` nessas linhas.
# Quem cuida de cupom é `core/cupons.py`, com tabela própria.
NAO_MEXEM_NO_PRECO = ("SELLER_COUPON_CAMPAIGN",)

# Como se ALTERA o preço de uma campanha em que o anúncio JÁ está.
#
# Não é igual para todos os tipos, e tratar como se fosse custa vaga em
# campanha. Literal da doc (central-de-promociones, 09/06/2026):
#
#   "Para editar los descuentos individuales (PRICE_DISCOUNT), las ofertas
#    del día (DOD) y las ofertas relámpago (LIGHTNING) debes eliminar la
#    promoción y aplicarla nuevamente."
#
# São só esses três. DEAL, MARKETPLACE_CAMPAIGN e VOLUME têm
# `PUT /seller-promotions/items/{id}` e mudam no lugar.
#
# A diferença é dinheiro: sair de um DEAL para reentrar devolve a vaga ao ML
# sem garantia de recuperá-la, e depois de sair o ML ancora no preço
# praticado para recusar aumento (medido nesta casa em 02/09/2026).
SAIR_E_READERIR = ("PRICE_DISCOUNT", "DOD", "LIGHTNING")
ALTERA_NO_LUGAR = ("DEAL", "MARKETPLACE_CAMPAIGN", "VOLUME")


def como_alterar(tipo: str | None) -> str:
    """
    'put', 'sair_e_readerir' ou 'confira_a_doc' — como mexer no preço desta
    campanha sem perder a vaga.

    Mora aqui, e não em quem escreve, pela regra da casa: régua em `core/`,
    versão única. Hoje o caminho de escrita generaliza:
    `core/publicacao.py::sair_de_promocao` faz DELETE em qualquer tipo e
    `core/ml_api.py` não tem sequer um método de PUT para promoção. Quem for
    consertar aquele caminho pergunta a esta função em vez de repetir a
    tabela num terceiro lugar.

    'confira_a_doc' não é sinônimo de 'pode PUT'. A lista dos que aceitam
    edição no lugar é fechada; tipo fora das duas listas é motivo para parar
    e ler, não para arriscar um DELETE.
    """
    t = (tipo or "").upper()
    if t in SAIR_E_READERIR:
        return "sair_e_readerir"
    if t in ALTERA_NO_LUGAR:
        return "put"
    return "confira_a_doc"


def nome_legivel(promocao) -> str:
    """O nome da campanha, ou o tipo traduzido quando ela não tem nome."""
    nome = (promocao["nome"] or "").strip()
    if nome:
        return nome
    return NOMES.get(promocao["tipo"], promocao["tipo"] or "campanha")


def _num(valor: Any) -> float | None:
    return float(valor) if isinstance(valor, (int, float)) else None


def _preco_de_vitrine(p: dict) -> float | None:
    """
    O preço que o COMPRADOR vê — que nem sempre é o preço da campanha.

    O ML pode turbinar uma oferta: põe desconto por cima do preço da campanha
    e a vitrine passa a mostrar um valor MENOR que o `price` da promoção. A
    doc (central-de-promociones, 09/06/2026) descreve os campos
    `boosted_offer`, `discount_meli_boosted_percentage`,
    `discount_meli_boost_amount` e `total_price_for_boosted_offer` — este
    último com todas as letras: o preço que o comprador de fato vê. Eles só
    existem quando `boosted_offer` é verdadeiro, e só em DEAL,
    PRICE_DISCOUNT, PRE_NEGOTIATED, SMART, PRICE_MATCHING e LIGHTNING.

    A coluna `preco` desta tabela sempre significou preço de vitrine: é com
    ela que `consolidar` diz "esta é a que manda no preço hoje" e que o
    alerta escreve "o preço iria para X". Numa oferta turbinada, gravar o
    `price` cru não muda o sentido da coluna — só a preenche com o número
    errado, e o veredito passa a decidir por um preço que ninguém pratica.

    Na dúvida fica o MENOR dos dois, e a dúvida é real. Os campos do boost se
    chamam `discount_meli_*`, o que sugere que o ML banca a diferença e o
    vendedor segue recebendo pelo `price` — mas isso é leitura de nome de
    campo, não medição. Sonda de 11/09/2026 (somente leitura) em 46 anúncios
    de 5 contas (Facilita ×2, Ênio, Maxi, JB), 164 promoções lidas, não achou
    UMA linha com `boosted_offer` — o campo nem aparece na resposta. Ou seja:
    o problema é real e ainda está dormindo, e não há venda turbinada para
    conferir quem banca. Enquanto não
    houver, errar para baixo faz recusar campanha boa; errar para cima faz
    aceitar campanha que fura o piso — que é o erro que este módulo existe
    para impedir. Quem responde de vez é `/orders/{id}/discounts` →
    `amounts.seller` de uma venda turbinada, que separa o que o ML pagou do
    que a loja pagou.
    """
    base = _num(p.get("price"))
    if not p.get("boosted_offer"):
        return base
    turbinado = _num(p.get("total_price_for_boosted_offer"))
    if turbinado is None:
        return base                   # boost anunciado sem o total: fica o base
    return turbinado if base is None else min(base, turbinado)


def normalizar(item_id: str, bruto: Any) -> list[dict]:
    """Achata a resposta da API no formato que a tabela guarda."""
    if isinstance(bruto, dict):
        bruto = bruto.get("results") or []
    if not isinstance(bruto, list):
        return []

    saida = []
    for p in bruto:
        if not isinstance(p, dict):
            continue
        status = (p.get("status") or "").lower()
        if status not in INTERESSANTES:
            continue
        saida.append({
            "item_id": item_id,
            "promocao_id": p.get("id") or p.get("type"),
            "tipo": p.get("type"),
            "nome": p.get("name") or "",
            "status": status,
            "preco": _preco_de_vitrine(p),
            "preco_original": _num(p.get("original_price")),
            "preco_sugerido": _num(p.get("suggested_discounted_price")),
            "preco_minimo": _num(p.get("min_discounted_price")),
            "parte_do_ml": _num(p.get("meli_percentage")),
            "parte_do_vendedor": _num(p.get("seller_percentage")),
            "fim": p.get("finish_date"),
        })
    return saida


def fila(con: sqlite3.Connection, conta, itens: list[str],
         quantos: int) -> list[str]:
    """
    Quais anúncios têm as campanhas conferidas nesta rodada.

    Mesmo raciocínio do rodízio de frete: uma chamada por anúncio a cada cinco
    minutos seria caro sem melhorar decisão nenhuma, porque campanha não nasce
    de minuto em minuto. Com 6 por rodada, os 28 do Ênio passam em meia hora —
    e o cursor no banco sobrevive a reinício, senão os últimos da lista nunca
    seriam olhados.
    """
    if quantos <= 0 or not itens:
        return []
    if quantos >= len(itens):
        return list(itens)
    chave = f"promo_cursor_{conta.slug}"
    ultimo = db.ler_marcador(con, chave)
    inicio = (itens.index(ultimo) + 1) if ultimo in itens else 0
    escolhidos = [itens[(inicio + i) % len(itens)] for i in range(quantos)]
    db.gravar_marcador(con, chave, escolhidos[-1])
    return escolhidos


def coletar(con: sqlite3.Connection, conta, cli, itens: list[str]) -> tuple[int, str]:
    """Pergunta ao ML as campanhas de cada anúncio e grava um snapshot."""
    carimbo = agora_iso()
    linhas: list[dict] = []
    for item_id in itens:
        try:
            linhas += normalizar(item_id, cli.promocoes_do_item(item_id))
        except Exception:
            # Um anúncio sem resposta não pode derrubar a coleta dos outros.
            continue
    if not linhas:
        return 0, carimbo
    db.inserir_muitos(con, "snap_promocao",
                      [{"coletado_em": carimbo, "conta_slug": conta.slug, **l}
                       for l in linhas])
    con.commit()
    return len(linhas), carimbo


def _chave(l) -> str:
    return f"{l['item_id']}|{l['promocao_id']}|{l['status']}"


def novidades(con: sqlite3.Connection, conta_slug: str,
              carimbo: str) -> list[sqlite3.Row]:
    """
    As campanhas que apareceram agora e não existiam na leitura anterior
    DAQUELE anúncio.

    A comparação é por anúncio, não por coleta — e isso não é detalhe. A coleta
    é um rodízio: cada rodada olha uma fatia diferente. Comparar a fatia de
    agora com a fatia anterior faria toda campanha de um anúncio que não estava
    na fatia passada parecer novidade, e o canal receberia as 47 campanhas
    abertas a cada meia hora, para sempre.

    É o mesmo erro que já produziu 41 alertas de "sumiu da conta" numa
    importação de posições: comparar contra um retrato que nunca teve aquele
    item. Aqui a defesa é a mesma — cada anúncio só se compara consigo mesmo.

    Anúncio visto pela primeira vez não gera nada: sem leitura anterior não há
    'apareceu', só 'existe'.
    """
    atuais = con.execute(
        "SELECT * FROM snap_promocao WHERE conta_slug = ? AND coletado_em = ?",
        (conta_slug, carimbo)).fetchall()
    if not atuais:
        return []

    novas = []
    for item_id in {l["item_id"] for l in atuais}:
        anterior = con.execute(
            "SELECT MAX(coletado_em) AS t FROM snap_promocao "
            "WHERE conta_slug = ? AND item_id = ? AND coletado_em < ?",
            (conta_slug, item_id, carimbo)).fetchone()["t"]
        if not anterior:
            continue                      # primeira leitura deste anúncio
        vistas = {(l["promocao_id"], l["status"]) for l in con.execute(
            "SELECT promocao_id, status FROM snap_promocao "
            "WHERE conta_slug = ? AND item_id = ? AND coletado_em = ?",
            (conta_slug, item_id, anterior))}
        novas += [l for l in atuais
                  if l["item_id"] == item_id
                  and (l["promocao_id"], l["status"]) not in vistas]
    return novas


def ultimas_por_item(con: sqlite3.Connection, conta_slug: str) -> dict[str, list]:
    """
    As campanhas de cada anúncio na ÚLTIMA leitura DAQUELE anúncio.

    Existe pelo mesmo motivo que `db.fretes_recentes` e `db.vitrines_recentes`:
    a leitura de campanha é por RODÍZIO, alguns anúncios por rodada. Então o
    carimbo mais recente da tabela é uma passada PARCIAL — quem filtra por
    `MAX(coletado_em)` global vê só os poucos anúncios daquela rodada e conclui
    que a conta quase não tem campanha.

    Foi exatamente o que aconteceu na página da FACILITA em 03/09/2026: ela
    anunciava "3 abertas, 11 rodando" quando a conta tinha 260 e 354. Não era
    dado faltando, era o recorte errado.
    """
    ultimos = {r["item_id"]: r["q"] for r in con.execute(
        "SELECT item_id, MAX(coletado_em) q FROM snap_promocao "
        " WHERE conta_slug = ? GROUP BY item_id", (conta_slug,))}
    saida: dict[str, list] = {}
    for item_id, carimbo in ultimos.items():
        saida[item_id] = list(con.execute(
            "SELECT * FROM snap_promocao WHERE conta_slug = ? AND item_id = ? "
            "  AND coletado_em = ?", (conta_slug, item_id, carimbo)))
    return saida


def consolidar(campanhas: list, piso: float | None) -> dict | None:
    """
    Qual campanha FICA, quando se quer uma só por anúncio.

    Dois ramos, e a diferença entre eles é o que faz a decisão ser segura:

    - Se a campanha mais barata **já respeita o piso**, ela fica. Ela é a que
      manda no preço hoje, então sair das outras não muda um centavo para o
      comprador — é remoção de ruído, não mudança de preço. Entre empatadas no
      menor preço, fica a de maior rebate do ML.
    - Se a mais barata **fura o piso**, fica a mais barata que NÃO fura. Aí o
      preço sobe, e é esse o conserto.

    Devolve None quando não há campanha ativa, e marca `ramo` como
    'nenhuma cabe no piso' quando nem a mais cara salva — nesse caso o
    problema é o preço de cadastro, e campanha nenhuma resolve.

    Aviso para quem EXECUTA o ramo 'sobe para o piso': o conserto é SAIR das
    campanhas que furam, não subir o preço do anúncio. Subir o preço apaga
    desconto sozinho — literal da doc, sobre PRICE_DISCOUNT: "Si se realiza
    una suba del precio del ítem, los descuentos serán quitados
    automáticamente". Não vem erro, não vem HTTP diferente: o desconto
    simplesmente some, e quem só olhou o status acha que não fez nada. Somem
    inclusive os descontos que não estavam no plano.
    """
    # Só entra quem realmente manda no preço da vitrine. Cupom não manda: a
    # API devolve `price: 0` nessas linhas, então ele seria SEMPRE a "mais
    # barata" e o plano sairia com "hoje R$ 0,00 → sobe para o piso" em todo
    # anúncio da campanha. Não é hipótese: entre 02 e 05/09/2026 a
    # maxi-brasil-principal teve 167 linhas assim, todas
    # SELLER_COUPON_CAMPAIGN. Reprocessado com o filtro, os 22 anúncios
    # atingidos trocam "hoje R$ 0,00" pelo preço que de fato valia — a SMART
    # ou o DEAL do item. O `> 0` acompanha o filtro por tipo de propósito:
    # preço zero nunca é preço de vitrine, venha de que tipo vier.
    ativas = [p for p in campanhas
              if p["status"] == "started"
              and p["tipo"] not in NAO_MEXEM_NO_PRECO
              and p["preco"] is not None and float(p["preco"]) > 0]
    if not ativas:
        return None
    ativas.sort(key=lambda p: (float(p["preco"]), -float(p["parte_do_ml"] or 0)))
    barata = ativas[0]
    hoje = float(barata["preco"])

    if piso and hoje < piso:
        cabem = [p for p in ativas if float(p["preco"]) >= piso]
        if cabem:
            fica, ramo = cabem[0], "sobe para o piso"
        else:
            fica = max(ativas, key=lambda p: (float(p["preco"]), float(p["parte_do_ml"] or 0)))
            ramo = "nenhuma cabe no piso"
    else:
        empatadas = [p for p in ativas if abs(float(p["preco"]) - hoje) < 0.02]
        fica = max(empatadas, key=lambda p: float(p["parte_do_ml"] or 0))
        ramo = "mantem o preco"

    return {
        "ramo": ramo, "hoje": hoje, "depois": float(fica["preco"]),
        "fica": fica, "saem": [p for p in ativas if p is not fica],
        "quantas": len(ativas),
    }


def veredito(promocao: sqlite3.Row, piso: float | None,
             preco_hoje: float | None) -> dict:
    """
    O que acontece com a margem se esta campanha for aceita.

    Sem piso não há veredito — e dizer 'talvez' é pior que não dizer nada.
    """
    preco = promocao["preco"] or promocao["preco_sugerido"]
    if preco is None:
        return {"conclusao": "sem preço", "cabe": None, "sobra": None, "preco": None}
    if not piso:
        # O preço vai junto mesmo sem veredito: é a informação que a pessoa
        # precisa para decidir na mão enquanto o custo não está cadastrado.
        return {"conclusao": "sem custo cadastrado", "cabe": None,
                "sobra": None, "preco": preco}
    sobra = preco - piso
    return {
        "conclusao": "cabe no piso" if sobra >= 0 else "fura o piso",
        "cabe": sobra >= 0,
        "sobra": sobra,
        "preco": preco,
        "queda_pct": ((preco_hoje - preco) / preco_hoje * 100)
                     if preco_hoje else None,
    }
