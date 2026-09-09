"""
Campanhas de cupom do vendedor (SELLER_COUPON_CAMPAIGN).

O QUE MUDA EM RELAÇÃO ÀS OUTRAS CAMPANHAS
-----------------------------------------
Nas campanhas de co-participação o Mercado Livre entra com uma parte do
desconto — nas do Ênio, de 1% a 4%. No cupom do vendedor não entra com nada:
a documentação diz, com todas as letras, que o orçamento é "totalmente
responsabilidade do vendedor".

Isso muda o que a leitura precisa mostrar. Numa campanha co-participada a
pergunta é "cabe no piso?". No cupom a pergunta é "quanto disso já saiu do meu
bolso, e a que ritmo?" — porque o cupom não aparece no preço do anúncio, some
do preço só no checkout, e queima orçamento sem que ninguém veja acontecer.

O QUE A API ENTREGA E O QUE NÃO ENTREGA
---------------------------------------
Entrega, por campanha: used_coupons (quantos foram usados), budget e
remaining_budget, o código, as datas, o status, e a lista de anúncios que
participam.

NÃO entrega em qual anúncio cada cupom foi usado. used_coupons é um número da
campanha inteira. Para atribuir por produto é preciso ir pelo lado da venda:
/orders/$ID/discounts (desconto por item) e o pagamento (fee_details com
type=coupon_fee). A função `sondar_vendas` existe justamente para descobrir,
numa conta real, onde esses campos aparecem antes de escrevermos a coleta.

Referência:
https://developers.mercadolivre.com.br/pt_br/cupons-do-vendedor
"""
from __future__ import annotations

import sqlite3
from typing import Any

from . import db
from .utils import agora_iso

TIPO = "SELLER_COUPON_CAMPAIGN"
VERSAO = "v2"

# Estados que a campanha pode ter, na ordem do ciclo de vida.
ESTADOS = ("pending", "started", "finished", "deleted")
VIVAS = ("pending", "started")


# --------------------------------------------------------------- leitura API

def _erro_legivel(erro: Exception) -> str:
    resposta = getattr(erro, "response", None)
    codigo = getattr(resposta, "status_code", None)
    if codigo == 403:
        return ("403 — o aplicativo não tem permissão de promoções nesta conta, "
                "ou a conta não é elegível a cupom (exige reputação verde)")
    if codigo == 401:
        return "401 — credencial recusada; rode 'checar' nesta conta"
    return f"{type(erro).__name__}: {erro}"


def listar(cli) -> tuple[list[dict], str | None]:
    """
    As campanhas de cupom da conta.

    O endpoint devolve TODAS as promoções do vendedor; filtramos por tipo aqui
    em vez de confiar num parâmetro de consulta que a documentação não promete.
    """
    try:
        dados = cli.get(f"/seller-promotions/users/{cli.user_id}", app_version=VERSAO)
    except Exception as erro:
        return [], _erro_legivel(erro)

    if isinstance(dados, dict):
        promocoes = dados.get("results") or dados.get("promotions") or []
    elif isinstance(dados, list):
        promocoes = dados
    else:
        promocoes = []

    return [p for p in promocoes if (p.get("type") or p.get("promotion_type")) == TIPO], None


def detalhe(cli, promocao_id: str) -> dict | None:
    """
    O retrato completo de uma campanha — é aqui que vive used_coupons.

    A listagem geral não traz orçamento nem uso; sem esta segunda chamada por
    campanha não existe a resposta de 'quantos foram usados'.
    """
    try:
        return cli.get(f"/seller-promotions/promotions/{promocao_id}",
                       promotion_type=TIPO, app_version=VERSAO)
    except Exception:
        return None


def itens(cli, promocao_id: str, status_item: str | None = None) -> list[dict]:
    """Os anúncios que participam da campanha, paginados de 50 em 50."""
    saida: list[dict] = []
    offset = 0
    while True:
        params: dict[str, Any] = {"promotion_type": TIPO, "app_version": VERSAO,
                                  "limit": 50, "offset": offset}
        if status_item:
            params["status_item"] = status_item
        try:
            dados = cli.get(f"/seller-promotions/promotions/{promocao_id}/items", **params)
        except Exception:
            break
        lote = (dados or {}).get("results", [])
        saida.extend(lote)
        offset += 50
        total = ((dados or {}).get("paging") or {}).get("total", 0)
        if not lote or offset >= total or offset >= 1000:
            break
    return saida


# ------------------------------------------------------------------ gravação

def _num(valor) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def coletar(con: sqlite3.Connection, conta, cli,
            carimbo: str | None = None) -> tuple[int, int, str, str | None]:
    """
    Lê as campanhas de cupom e grava um snapshot novo.

    Devolve (campanhas, itens, carimbo, aviso). Como todo o resto do zion-ml,
    coleta nova é linha nova: é a diferença entre duas leituras que responde
    "quantos cupons foram usados desde ontem".
    """
    carimbo = carimbo or agora_iso()
    campanhas, aviso = listar(cli)
    if aviso:
        return 0, 0, carimbo, aviso

    gravadas = 0
    gravados_itens = 0
    for resumo in campanhas:
        pid = resumo.get("id")
        if not pid:
            continue
        cheio = detalhe(cli, pid) or resumo

        db.inserir(con, "snap_cupom", {
            "coletado_em": carimbo,
            "cliente_id": conta.cliente_id,
            "conta_slug": conta.slug,
            "promocao_id": pid,
            "nome": cheio.get("name"),
            "sub_tipo": cheio.get("sub_type"),
            "status": cheio.get("status"),
            "codigo": cheio.get("coupon_code"),
            "valor_fixo": _num(cheio.get("fixed_amount")),
            "percentual": _num(cheio.get("fixed_percentage")),
            "compra_minima": _num(cheio.get("min_purchase_amount")),
            "compra_maxima": _num(cheio.get("max_purchase_amount")),
            "orcamento": _num(cheio.get("budget")),
            "orcamento_restante": _num(cheio.get("remaining_budget")),
            "cupons_usados": cheio.get("used_coupons"),
            "usos_por_comprador": cheio.get("redeems_per_user"),
            "inicio": cheio.get("start_date"),
            "fim": cheio.get("finish_date"),
        })
        gravadas += 1

        if cheio.get("status") in VIVAS:
            for item in itens(cli, pid):
                db.inserir(con, "snap_cupom_item", {
                    "coletado_em": carimbo,
                    "conta_slug": conta.slug,
                    "promocao_id": pid,
                    "item_id": item.get("id"),
                    "status": item.get("status"),
                    "valor_fixo": _num(item.get("fixed_amount")),
                    "percentual": _num(item.get("fixed_percentage")),
                    "preco_original": _num(item.get("original_price")),
                    "inicio": item.get("start_date"),
                    "fim": item.get("end_date"),
                })
                gravados_itens += 1

    con.commit()
    return gravadas, gravados_itens, carimbo, None


# ----------------------------------------------------------------- leitura DB

def consumo(linha) -> dict:
    """
    Traduz uma linha de campanha em dinheiro: quanto do orçamento já queimou,
    quanto custou cada cupom em média e quantos ainda caberiam.
    """
    orcamento = linha["orcamento"] or 0.0
    restante = linha["orcamento_restante"]
    usados = linha["cupons_usados"] or 0
    gasto = (orcamento - restante) if (orcamento and restante is not None) else None
    return {
        "gasto": gasto,
        "gasto_pct": (gasto / orcamento * 100) if (gasto is not None and orcamento) else None,
        "custo_medio": (gasto / usados) if (gasto and usados) else None,
        "cupons_usados": usados,
    }


def ultima(con: sqlite3.Connection, conta_slug: str) -> list[sqlite3.Row]:
    """As campanhas na coleta mais recente desta conta."""
    carimbo = db.ultima_coleta(con, "snap_cupom", conta_slug)
    if not carimbo:
        return []
    return con.execute(
        "SELECT * FROM snap_cupom WHERE conta_slug = ? AND coletado_em = ? "
        "ORDER BY status, nome", (conta_slug, carimbo)).fetchall()


def movimento(con: sqlite3.Connection, conta_slug: str,
              horas: int = 24) -> dict[str, dict]:
    """
    Quantos cupons foram usados por campanha desde a leitura mais próxima de
    N horas atrás, e quanto de orçamento isso consumiu.

    Compara cada campanha consigo mesma — nunca uma coleta inteira com a
    anterior. Campanha vista pela primeira vez não gera movimento: sem leitura
    anterior existe 'existe', não 'aumentou'.
    """
    carimbo = db.ultima_coleta(con, "snap_cupom", conta_slug)
    if not carimbo:
        return {}

    saida: dict[str, dict] = {}
    for atual in con.execute(
            "SELECT * FROM snap_cupom WHERE conta_slug = ? AND coletado_em = ?",
            (conta_slug, carimbo)):
        antes = con.execute(
            "SELECT * FROM snap_cupom WHERE conta_slug = ? AND promocao_id = ? "
            "AND coletado_em < ? AND coletado_em >= datetime(?, ?) "
            "ORDER BY coletado_em LIMIT 1",
            (conta_slug, atual["promocao_id"], carimbo, carimbo, f"-{horas} hours")
        ).fetchone()
        if not antes:
            continue
        novos = (atual["cupons_usados"] or 0) - (antes["cupons_usados"] or 0)
        queimado = None
        if atual["orcamento_restante"] is not None and antes["orcamento_restante"] is not None:
            queimado = antes["orcamento_restante"] - atual["orcamento_restante"]
        if novos or queimado:
            saida[atual["promocao_id"]] = {
                "nome": atual["nome"], "novos_usos": novos,
                "orcamento_queimado": queimado, "desde": antes["coletado_em"],
            }
    return saida


def anuncios_da_campanha(con: sqlite3.Connection, conta_slug: str,
                         promocao_id: str) -> list[sqlite3.Row]:
    """
    Os anúncios da campanha na leitura mais recente DELA.

    O carimbo é buscado por campanha, e não o mais recente da tabela: campanha
    encerrada deixa de ter itens coletados, e usar o carimbo global devolveria
    lista vazia para ela só porque outra campanha foi lida depois.
    """
    carimbo = con.execute(
        "SELECT MAX(coletado_em) t FROM snap_cupom_item "
        "WHERE conta_slug = ? AND promocao_id = ?",
        (conta_slug, promocao_id)).fetchone()["t"]
    if not carimbo:
        return []
    return con.execute(
        "SELECT i.*, a.titulo, a.preco, a.preco_vitrine FROM snap_cupom_item i "
        "LEFT JOIN snap_anuncio a ON a.item_id = i.item_id AND a.conta_slug = i.conta_slug "
        "  AND a.coletado_em = (SELECT MAX(coletado_em) FROM snap_anuncio "
        "                       WHERE conta_slug = ?) "
        "WHERE i.conta_slug = ? AND i.coletado_em = ? AND i.promocao_id = ?",
        (conta_slug, conta_slug, carimbo, promocao_id)).fetchall()


# -------------------------------------------------------------------- sonda

CHAVES_DE_CUPOM = ("coupon", "cupom")


def _caminhos_com_cupom(no: Any, prefixo: str = "", achados: dict | None = None) -> dict:
    """Varre o payload atrás de qualquer campo cujo nome fale em cupom."""
    achados = {} if achados is None else achados
    if isinstance(no, dict):
        for chave, valor in no.items():
            caminho = f"{prefixo}.{chave}" if prefixo else chave
            if any(p in str(chave).lower() for p in CHAVES_DE_CUPOM):
                achados[caminho] = valor
            _caminhos_com_cupom(valor, caminho, achados)
    elif isinstance(no, list):
        for i, valor in enumerate(no[:3]):        # três é bastante para ver o formato
            _caminhos_com_cupom(valor, f"{prefixo}[{i}]", achados)
    return achados


def _tem_valor(valor: Any) -> bool:
    """
    Campo de cupom que veio zerado não conta como cupom.

    O payload traz o campo mesmo quando não houve cupom nenhum — às vezes como
    0, às vezes como {"id": null, "amount": 0}. Sem esta peneira a sonda
    concluiria que toda venda teve cupom, que é exatamente a resposta errada
    para a pergunta que ela existe para responder.
    """
    if valor in (None, 0, 0.0, "", [], {}):
        return False
    if isinstance(valor, dict):
        return any(_tem_valor(v) for v in valor.values())
    if isinstance(valor, list):
        return any(_tem_valor(v) for v in valor)
    return True


def sondar_vendas(cli, dias: int = 30, limite_pedidos: int = 40) -> dict:
    """
    Descobre ONDE o cupom aparece nos pedidos desta conta, sem gravar nada.

    Existe para responder empiricamente a pergunta que a documentação deixa em
    aberto: o valor do cupom já vem no payload de /orders/search, ou só no
    pagamento e em /orders/$ID/discounts? A resposta muda quantas chamadas por
    pedido a coleta vai custar — e é diferente por conta, então chutar sairia
    caro.
    """
    pedidos = cli.vendas_recentes(dias=dias)[:limite_pedidos]
    achados: dict[str, Any] = {}
    com_cupom: list[dict] = []

    for pedido in pedidos:
        campos = _caminhos_com_cupom(pedido)
        com_valor = {c: v for c, v in campos.items() if _tem_valor(v)}
        for caminho in campos:
            achados.setdefault(caminho, 0)
            achados[caminho] += 1
        if com_valor:
            com_cupom.append({
                "order_id": pedido.get("id"),
                "data": pedido.get("date_created"),
                "total": pedido.get("total_amount"),
                "itens": [i.get("item", {}).get("id") for i in pedido.get("order_items", [])],
                "campos": com_valor,
            })

    exemplo_desconto = None
    if pedidos:
        alvo = (com_cupom[0]["order_id"] if com_cupom else pedidos[0].get("id"))
        try:
            exemplo_desconto = cli.get(f"/orders/{alvo}/discounts")
        except Exception as erro:
            exemplo_desconto = {"erro": _erro_legivel(erro)}

    return {
        "pedidos_examinados": len(pedidos),
        "dias": dias,
        "campos_com_cupom_no_payload": achados or "nenhum campo com 'coupon' no /orders/search",
        "pedidos_com_valor_de_cupom": com_cupom,
        "exemplo_orders_discounts": exemplo_desconto,
        "conclusao": ("o valor do cupom já vem no /orders/search — dá para atribuir por "
                      "anúncio sem chamada extra"
                      if com_cupom else
                      "nenhum cupom encontrado nesta janela; ou a conta não teve venda com "
                      "cupom, ou o valor só existe no pagamento (fee_details/coupon_fee)"),
    }


# ------------------------------------------------- atribuição por anúncio

def _quem_paga(vendedor: float | None, total: float | None) -> str:
    """
    Quem bancou o desconto daquele item.

    A pergunta não é retórica: na sonda da conta da Maxi, TODOS os cupons
    encontrados nos pedidos tinham seller 0.0 — eram campanhas do próprio
    Mercado Livre viajando no mesmo campo. Sem esta separação, o custo de
    cupom do vendedor sairia inflado por descontos que não foram dele.
    """
    v = vendedor or 0.0
    t = total or 0.0
    if v <= 0:
        return "mercado livre"
    if t and v < t - 0.009:
        return "dividido"
    return "vendedor"


def _cupons_do_pedido(detalhe: dict) -> list[dict]:
    """
    Achata o /orders/$ID/discounts em uma linha por (cupom, anúncio).

    O payload traz o desconto por ITEM, com 'seller' e 'total' separados, e o
    fornecedor ao lado. É o único lugar em que o custo real do vendedor
    aparece discriminado por anúncio.
    """
    linhas: list[dict] = []
    for bloco in (detalhe or {}).get("details", []):
        if bloco.get("type") not in ("coupon", "discount"):
            continue
        cupom = bloco.get("coupon") or {}
        fornecedor = bloco.get("supplier") or {}
        for item in bloco.get("items") or []:
            valores = item.get("amounts") or {}
            total = _num(valores.get("total"))
            vendedor = _num(valores.get("seller"))
            if not total and not vendedor:
                continue
            linhas.append({
                "item_id": item.get("id"),
                # 'coupon' e 'discount' chegam no mesmo endpoint e ambos podem
                # ser bancados pelo vendedor. Guardar o tipo é o que permite
                # responder "isto foi cupom mesmo, ou foi campanha de preço?"
                "tipo": bloco.get("type"),
                "cupom_id": str(cupom.get("id") or bloco.get("id") or ""),
                "campanha_id": str(fornecedor.get("campaign_id")
                                   or fornecedor.get("offer_id") or ""),
                "campanha_do_ml": str(fornecedor.get("meli_campaign") or "") or None,
                "quantidade": item.get("quantity"),
                "valor_total": total,
                "valor_vendedor": vendedor if vendedor is not None else 0.0,
                "quem_paga": _quem_paga(vendedor, total),
            })
    return linhas


def _tem_sinal_de_cupom(pedido: dict) -> bool:
    """
    Vale a pena gastar uma chamada de /discounts neste pedido?

    /discounts custa uma chamada POR PEDIDO. Pedir para todos os 40 quando só
    alguns tiveram cupom é desperdício que aparece no rate limit. O payload da
    busca já denuncia quem teve.
    """
    return bool(_tem_valor(_caminhos_com_cupom(pedido)))


def _pedidos_da_janela(cli, dias: int, fatia_inicial: float = 7.0
                       ) -> tuple[list[dict], bool]:
    """
    Busca a janela inteira, subdividindo o intervalo que estourar o teto.

    O /orders/search para no offset 1000 e devolve o corte calado. A conta da
    Maxi faz centenas de pedidos por dia, e há DIAS que sozinhos passam de mil
    — fatiar em blocos fixos não resolve. Aqui cada intervalo que volta
    truncado é partido ao meio e devolvido à fila, até caber ou até chegar a
    cinco minutos, quando desistir é mais honesto que fingir.

    Só o pedaço problemático é refeito: subdividir a janela toda cobraria
    dezenas de buscas boas para consertar uma ruim.
    """
    from datetime import datetime, timedelta, timezone as _tz
    agora = datetime.now(_tz.utc)
    limite = agora - timedelta(days=dias)

    fila: list[tuple] = []
    fim_ = agora
    while fim_ > limite:
        comeco = max(limite, fim_ - timedelta(days=fatia_inicial))
        fila.append((comeco, fim_))
        fim_ = comeco

    MINIMO = timedelta(minutes=5)
    todos: list[dict] = []
    vistos: set = set()
    truncou = False

    while fila:
        comeco, fim_ = fila.pop()
        lote = cli.vendas_recentes(desde=comeco, ate=fim_)

        if getattr(cli, "ultima_busca_truncou", False):
            meio = comeco + (fim_ - comeco) / 2
            if (fim_ - comeco) > MINIMO and meio > comeco:
                fila.append((meio, fim_))
                fila.append((comeco, meio))
                continue
            truncou = True                  # cinco minutos com mais de mil pedidos

        for p in lote:
            chave = str(p.get("id"))
            if chave not in vistos:
                vistos.add(chave)
                todos.append(p)

    return todos, truncou


def coletar_vendas(con: sqlite3.Connection, conta, cli, dias: int = 30,
                   limite_pedidos: int = 500, refazer: bool = False) -> dict:
    """
    Guarda quanto cada cupom custou, por anúncio.

    Pedido já registrado não é relido: a chave única cobre (conta, pedido,
    anúncio, cupom), e o pedido conhecido nem chega a gastar a chamada de
    /discounts. Rodar de novo a mesma janela é barato e não duplica.
    """
    # O corte é do mais RECENTE para o mais antigo (a busca vem ordenada por
    # data desc). Numa conta com muito pedido, um limite baixo mede só a ponta
    # da janela e faz o total parecer menor do que é — foi o que aconteceu na
    # primeira medição da Maxi, com 200: apareceram 15 usos de cupom onde a
    # campanha registrava 107.
    todos, truncou = _pedidos_da_janela(cli, dias)
    pedidos = todos[:limite_pedidos]

    # Apagar ANTES de ler é como o refazer nasceu, e estava errado: a busca de
    # pedidos falhou no meio e a conta ficou sem os dados antigos e sem os
    # novos. Agora a lista já está em mãos quando o histórico some.
    if refazer:
        esquecer_vendas(con, conta.slug)

    ja_vistos = {l["order_id"] for l in con.execute(
        "SELECT DISTINCT order_id FROM venda_cupom WHERE conta_slug = ?",
        (conta.slug,))}

    novos = consultados = 0
    sem_cupom = 0
    for pedido in pedidos:
        order_id = str(pedido.get("id") or "")
        if not order_id:
            continue

        # A venda é registrada SEMPRE, inclusive a que não teve desconto: é
        # ela que forma o denominador de "quantas vendas vieram pelo cupom".
        itens = [i.get("item", {}).get("id") for i in pedido.get("order_items") or []]
        unidades = sum((i.get("quantity") or 1)
                       for i in pedido.get("order_items") or []) or None
        con.execute(
            "INSERT OR IGNORE INTO venda (registrado_em, cliente_id, conta_slug, "
            " order_id, data_pedido, status, total, unidades, itens, comprador) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (agora_iso(), conta.cliente_id, conta.slug, order_id,
             pedido.get("date_created"), pedido.get("status"),
             _num(pedido.get("total_amount")), unidades,
             ",".join(str(i) for i in itens if i),
             str((pedido.get("buyer") or {}).get("id") or "") or None))

        if order_id in ja_vistos:
            continue
        if not _tem_sinal_de_cupom(pedido):
            sem_cupom += 1
            continue

        try:
            detalhe = cli.get(f"/orders/{order_id}/discounts")
        except Exception as erro:
            _log_cupom(f"discounts falhou em {order_id}: {erro}")
            continue
        consultados += 1

        for linha in _cupons_do_pedido(detalhe):
            cur = con.execute(
                "INSERT OR IGNORE INTO venda_cupom "
                "(registrado_em, cliente_id, conta_slug, order_id, data_pedido, "
                " item_id, tipo, cupom_id, campanha_id, campanha_do_ml, quem_paga, "
                " valor_total, valor_vendedor, quantidade, total_pedido) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (agora_iso(), conta.cliente_id, conta.slug, order_id,
                 pedido.get("date_created"), linha["item_id"], linha["tipo"],
                 linha["cupom_id"],
                 linha["campanha_id"], linha["campanha_do_ml"], linha["quem_paga"],
                 linha["valor_total"], linha["valor_vendedor"], linha["quantidade"],
                 _num(pedido.get("total_amount"))))
            # rowcount, e não total_changes: total_changes é acumulado da
            # conexão inteira e contaria como novidade linha que o OR IGNORE
            # descartou.
            novos += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    con.commit()
    return {"pedidos_lidos": len(pedidos), "pedidos_na_janela": len(todos),
            "cortou": len(todos) > len(pedidos), "truncou_na_api": truncou,
            "pedidos_consultados": consultados,
            "pedidos_sem_cupom": sem_cupom, "linhas_novas": novos, "dias": dias}


def _log_cupom(mensagem: str) -> None:
    """Falha de um pedido não derruba a coleta dos outros; fica registrada."""
    try:
        from .utils import DIR_DADOS
        (DIR_DADOS / "cupons.log").open("a", encoding="utf-8").write(
            f"[{agora_iso()}] {mensagem}\n")
    except Exception:
        pass


def custo_por_anuncio(con: sqlite3.Connection, conta_slug: str,
                      dias: int = 30) -> list[dict]:
    """
    Quanto o cupom custou em cada anúncio na janela — separando o que saiu do
    vendedor do que o Mercado Livre bancou.
    """
    linhas = con.execute(
        "SELECT v.item_id, "
        "       COUNT(DISTINCT v.order_id) AS pedidos, "
        "       SUM(IFNULL(v.quantidade,1)) AS unidades, "
        "       SUM(v.valor_vendedor)      AS custo_vendedor, "
        "       SUM(v.valor_total)         AS desconto_total, "
        "       MAX(v.data_pedido)         AS ultimo, "
        "       a.titulo, a.preco, a.preco_vitrine "
        "FROM venda_cupom v "
        "LEFT JOIN snap_anuncio a ON a.item_id = v.item_id "
        "     AND a.conta_slug = v.conta_slug "
        "     AND a.coletado_em = (SELECT MAX(coletado_em) FROM snap_anuncio "
        "                          WHERE conta_slug = ?) "
        "WHERE v.conta_slug = ? AND v.data_pedido >= datetime('now', ?) "
        "GROUP BY v.item_id "
        "ORDER BY custo_vendedor DESC, desconto_total DESC",
        (conta_slug, conta_slug, f"-{dias} days")).fetchall()

    saida = []
    for l in linhas:
        d = dict(l)
        d["bancado_pelo_ml"] = (d["desconto_total"] or 0) - (d["custo_vendedor"] or 0)

        # O desconto do pedido cobre TODAS as unidades daquela linha. Dividir
        # por pedido e comparar com o preço unitário foi o que produziu
        # "183% de desconto" — número impossível, que só existia porque o
        # numerador era de 3 unidades e o denominador de 1.
        unidades = d.get("unidades") or d["pedidos"] or 1
        d["por_unidade"] = (d["custo_vendedor"] or 0) / unidades

        # E o preço que temos é o de HOJE, já com a campanha aplicada. O preço
        # cheio estimado é ele mais o desconto por unidade — estimativa, não
        # medição: se a campanha mudou desde a venda, o número desloca.
        preco = d["preco_vitrine"] or d["preco"]
        cheio = (preco + d["por_unidade"]) if preco else None
        d["preco_cheio_estimado"] = cheio
        d["pct_do_cheio"] = (d["por_unidade"] / cheio * 100) if cheio else None
        saida.append(d)
    return saida


def resumo_de_custo(con: sqlite3.Connection, conta_slug: str,
                    dias: int = 30) -> dict:
    linha = con.execute(
        "SELECT COUNT(DISTINCT order_id) pedidos, "
        "       SUM(valor_vendedor) do_vendedor, SUM(valor_total) total "
        "FROM venda_cupom WHERE conta_slug = ? AND data_pedido >= datetime('now', ?)",
        (conta_slug, f"-{dias} days")).fetchone()
    do_vendedor = linha["do_vendedor"] or 0.0
    total = linha["total"] or 0.0
    # O que o ML bancou é o RESTO, não a soma das linhas marcadas 'mercado
    # livre': o desconto dividido tem uma parte de cada lado, e somar só as
    # linhas puras fazia as três cifras não fecharem — quem lesse via um erro
    # de conta de R$ 181 mil e, com razão, desconfiava do resto.
    return {"dias": dias, "pedidos_com_cupom": linha["pedidos"] or 0,
            "custo_do_vendedor": do_vendedor,
            "desconto_total": total,
            "bancado_pelo_ml": total - do_vendedor}


def por_campanha(con: sqlite3.Connection, conta_slug: str,
                 dias: int = 30) -> list[dict]:
    """
    O custo separado por campanha e por tipo.

    Serve para responder a pergunta que o total sozinho não responde: desse
    dinheiro todo, quanto é a campanha de cupom e quanto é outro desconto do
    vendedor viajando pelo mesmo endpoint. Somar tudo sob o rótulo "cupom"
    seria batizar de cupom o que pode ser campanha de preço.
    """
    linhas = con.execute(
        "SELECT IFNULL(tipo,'?') tipo, IFNULL(campanha_id,'') campanha_id, "
        "       IFNULL(campanha_do_ml,'') campanha_do_ml, "
        "       COUNT(DISTINCT order_id) pedidos, COUNT(*) linhas, "
        "       SUM(valor_vendedor) do_vendedor, SUM(valor_total) total, "
        "       MIN(valor_vendedor) menor, MAX(valor_vendedor) maior "
        "FROM venda_cupom WHERE conta_slug = ? AND data_pedido >= datetime('now', ?) "
        "GROUP BY tipo, campanha_id, campanha_do_ml "
        "ORDER BY do_vendedor DESC",
        (conta_slug, f"-{dias} days")).fetchall()
    return [dict(l) for l in linhas]


def esquecer_vendas(con: sqlite3.Connection, conta_slug: str) -> int:
    """
    Apaga o registrado desta conta para uma releitura completa.

    Existe porque a chave única impede que uma coluna acrescentada depois seja
    preenchida numa segunda passada: o pedido já conhecido é ignorado, e a
    coluna nova ficaria nula para sempre.
    """
    cur = con.execute("DELETE FROM venda_cupom WHERE conta_slug = ?", (conta_slug,))
    con.execute("DELETE FROM venda WHERE conta_slug = ?", (conta_slug,))
    con.commit()
    return cur.rowcount or 0


def por_tipo(con: sqlite3.Connection, conta_slug: str, dias: int = 30) -> list[dict]:
    """
    O total separado em cupom x desconto de campanha de preço.

    É a linha que responde de uma vez "o cupom é o problema?". Na conta da
    Maxi a resposta foi não: o cupom era 2% do que a conta dava de desconto.
    """
    linhas = con.execute(
        "SELECT IFNULL(tipo,'?') tipo, "
        "       COUNT(DISTINCT order_id) pedidos, "
        "       COUNT(DISTINCT IFNULL(campanha_id, cupom_id)) campanhas, "
        "       SUM(valor_vendedor) do_vendedor, SUM(valor_total) total "
        "FROM venda_cupom WHERE conta_slug = ? AND data_pedido >= datetime('now', ?) "
        "GROUP BY tipo ORDER BY do_vendedor DESC",
        (conta_slug, f"-{dias} days")).fetchall()
    return [dict(l) for l in linhas]


CANCELADOS = ("cancelled", "invalid")


def impacto_do_cupom(con: sqlite3.Connection, conta_slug: str,
                     dias: int = 30) -> dict:
    """
    Quantas vendas saíram COM cupom, e o que elas representam na conta.

    O nome não é "vendas geradas pelo cupom", e a diferença não é preciosismo:
    ninguém sabe quantas dessas pessoas comprariam de qualquer jeito. O que os
    dados sustentam é participação — quanto do que a conta vendeu passou pelo
    cupom, e quanto isso custou. Atribuir causa a esse número seria inventar
    um dado que não existe em lugar nenhum da API.
    """
    corte = f"-{dias} days"
    vivos = "status IS NULL OR status NOT IN ('cancelled','invalid')"

    total = con.execute(
        f"SELECT COUNT(*) pedidos, SUM(total) receita FROM venda "
        f"WHERE conta_slug = ? AND data_pedido >= datetime('now', ?) AND ({vivos})",
        (conta_slug, corte)).fetchone()

    com = con.execute(
        f"SELECT COUNT(DISTINCT v.order_id) pedidos, SUM(v.total) receita "
        f"FROM venda v WHERE v.conta_slug = ? AND v.data_pedido >= datetime('now', ?) "
        f"AND ({vivos}) AND v.order_id IN ("
        f"  SELECT order_id FROM venda_cupom WHERE conta_slug = ? "
        f"    AND tipo = 'coupon' AND valor_vendedor > 0)",
        (conta_slug, corte, conta_slug)).fetchone()

    custo = con.execute(
        "SELECT SUM(valor_vendedor) c FROM venda_cupom WHERE conta_slug = ? "
        "AND tipo = 'coupon' AND valor_vendedor > 0 AND data_pedido >= datetime('now', ?)",
        (conta_slug, corte)).fetchone()["c"] or 0.0

    pedidos_tot = total["pedidos"] or 0
    receita_tot = total["receita"] or 0.0
    pedidos_com = com["pedidos"] or 0
    receita_com = com["receita"] or 0.0
    pedidos_sem = pedidos_tot - pedidos_com
    receita_sem = receita_tot - receita_com

    return {
        "dias": dias,
        "pedidos_total": pedidos_tot, "receita_total": receita_tot,
        "pedidos_com_cupom": pedidos_com, "receita_com_cupom": receita_com,
        "share_pedidos": (pedidos_com / pedidos_tot * 100) if pedidos_tot else None,
        "share_receita": (receita_com / receita_tot * 100) if receita_tot else None,
        "ticket_com": (receita_com / pedidos_com) if pedidos_com else None,
        "ticket_sem": (receita_sem / pedidos_sem) if pedidos_sem else None,
        "custo_do_cupom": custo,
        "custo_sobre_receita_com": (custo / receita_com * 100) if receita_com else None,
    }


def antes_e_depois(con: sqlite3.Connection, conta_slug: str,
                   inicio: str, dias_antes: int = 30) -> dict | None:
    """
    Média diária de venda antes e depois do começo da campanha.

    É o mais perto de "o cupom trouxe venda" que estes dados chegam, e ainda
    assim não é prova: mês diferente tem sazonalidade, estoque e preço
    diferentes. Serve para levantar suspeita, não para fechar conclusão.
    """
    if not inicio:
        return None
    vivos = "(status IS NULL OR status NOT IN ('cancelled','invalid'))"

    def janela(de: str, ate: str, dias_corridos: float) -> dict:
        l = con.execute(
            f"SELECT COUNT(*) pedidos, SUM(total) receita, "
            f"       COUNT(DISTINCT date(data_pedido)) dias, "
            f"       MIN(data_pedido) primeiro "
            f"FROM venda WHERE conta_slug = ? AND {vivos} "
            f"AND data_pedido >= ? AND data_pedido < ?",
            (conta_slug, de, ate)).fetchone()
        # Divide pelos dias CORRIDOS da janela, não pelos dias em que houve
        # venda. Dividir por "dias com venda" transforma três dias de dados
        # numa média diária que parece o faturamento de um mês.
        return {"pedidos": l["pedidos"] or 0, "receita": l["receita"] or 0.0,
                "dias_com_venda": l["dias"] or 0, "dias_corridos": dias_corridos,
                "primeiro_pedido": l["primeiro"],
                "por_dia": ((l["receita"] or 0.0) / dias_corridos) if dias_corridos else None}

    from datetime import datetime, timedelta, timezone
    try:
        marco = datetime.fromisoformat(str(inicio).replace("Z", "+00:00"))
    except ValueError:
        return None
    antes_de = (marco - timedelta(days=dias_antes)).isoformat()
    agora = datetime.now(timezone.utc).isoformat()

    antes = janela(antes_de, marco.isoformat(), dias_antes)
    depois = janela(marco.isoformat(), agora,
                    max((datetime.now(timezone.utc) - marco).total_seconds() / 86400, 0.01))

    # Comparar com uma janela "antes" que a coleta nem cobriu é pior que não
    # comparar: dá uma variação enorme que só reflete o buraco nos dados.
    mais_antigo = con.execute(
        "SELECT MIN(data_pedido) d FROM venda WHERE conta_slug = ?",
        (conta_slug,)).fetchone()["d"]
    incompleto = bool(mais_antigo and str(mais_antigo)[:19] > antes_de[:19])

    return {"inicio": inicio, "antes": antes, "depois": depois,
            "incompleto": incompleto, "pedido_mais_antigo": mais_antigo}


def periodo_coberto(con: sqlite3.Connection, conta_slug: str) -> dict:
    """De quando a quando vão os pedidos que a conta tem guardados."""
    l = con.execute(
        "SELECT MIN(data_pedido) de, MAX(data_pedido) ate, COUNT(*) pedidos "
        "FROM venda WHERE conta_slug = ?", (conta_slug,)).fetchone()
    dias = None
    if l["de"] and l["ate"]:
        from datetime import datetime
        try:
            a = datetime.fromisoformat(str(l["de"]))
            b = datetime.fromisoformat(str(l["ate"]))
            dias = max((b - a).total_seconds() / 86400, 0)
        except ValueError:
            dias = None
    return {"de": l["de"], "ate": l["ate"], "pedidos": l["pedidos"] or 0, "dias": dias}


def _medir_janela(con: sqlite3.Connection, conta_slug: str,
                  desde: str) -> dict:
    """Vendas com cupom do vendedor a partir de uma data — a da campanha."""
    vivos = "(v.status IS NULL OR v.status NOT IN ('cancelled','invalid'))"
    l = con.execute(
        f"SELECT COUNT(DISTINCT v.order_id) pedidos, SUM(v.total) faturamento "
        f"FROM venda v WHERE v.conta_slug = ? AND v.data_pedido >= ? AND {vivos} "
        f"AND v.order_id IN (SELECT order_id FROM venda_cupom WHERE conta_slug = ? "
        f"  AND tipo = 'coupon' AND valor_vendedor > 0)",
        (conta_slug, desde, conta_slug)).fetchone()
    custo = con.execute(
        "SELECT SUM(valor_vendedor) c FROM venda_cupom WHERE conta_slug = ? "
        "AND tipo = 'coupon' AND valor_vendedor > 0 AND data_pedido >= ?",
        (conta_slug, desde)).fetchone()["c"] or 0.0
    pedidos = l["pedidos"] or 0
    fat = l["faturamento"] or 0.0
    return {"desde": desde, "pedidos": pedidos, "faturamento": fat, "custo": custo,
            "ticket": (fat / pedidos) if pedidos else None,
            "custo_pct": (custo / fat * 100) if fat else None}


def resumo_da_campanha(con: sqlite3.Connection, conta_slug: str,
                       dias: int = 60, desde: str | None = None) -> dict:
    """
    A resposta para "quanto vendeu nos cupons que a gente liberou".

    Junta as duas fontes que existem e que NÃO batem entre si de propósito:
      - o que o Mercado Livre diz da campanha (used_coupons), que é o total
        desde que ela começou;
      - o que foi medido pedido a pedido na janela coletada, que é o único
        lugar onde existe faturamento.
    Mostrar as duas lado a lado evita a pergunta inevitável de "por que aqui
    diz 107 e ali 64" virar desconfiança do relatório inteiro.

    `desde` (AAAA-MM-DD) recorta pela data de início da campanha em vez de
    contar dias para trás. É o que responde "a partir do dia 29" sem arrastar
    junto a campanha de cupom anterior — que foi exatamente o que fez o medido
    passar o que o ML registra. Com ele, os produtos listados também são só
    os do período, e não os dos últimos N dias.
    """
    corte = f"-{dias} days"
    vivos = "(v.status IS NULL OR v.status NOT IN ('cancelled','invalid'))"

    # data_pedido guarda o date_created do ML, que já vem no fuso do vendedor
    # ("2026-08-29T14:23:45.000-03:00"). Comparar com a string "2026-08-29"
    # pega o dia 29 inteiro, que é o que "a partir do dia 29" quer dizer.
    if desde:
        onde_v, onde_c, arg = "v.data_pedido >= ?", "data_pedido >= ?", desde
    else:
        onde_v = "v.data_pedido >= datetime('now', ?)"
        onde_c = "data_pedido >= datetime('now', ?)"
        arg = corte

    medido = con.execute(
        f"SELECT COUNT(DISTINCT v.order_id) pedidos, SUM(v.total) faturamento "
        f"FROM venda v WHERE v.conta_slug = ? AND {onde_v} "
        f"AND {vivos} AND v.order_id IN ("
        f"  SELECT order_id FROM venda_cupom WHERE conta_slug = ? "
        f"    AND tipo = 'coupon' AND valor_vendedor > 0)",
        (conta_slug, arg, conta_slug)).fetchone()

    custo = con.execute(
        f"SELECT SUM(valor_vendedor) c, COUNT(*) linhas FROM venda_cupom "
        f"WHERE conta_slug = ? AND tipo = 'coupon' AND valor_vendedor > 0 "
        f"AND {onde_c}", (conta_slug, arg)).fetchone()

    produtos = con.execute(
        "SELECT c.item_id, COUNT(DISTINCT c.order_id) pedidos, "
        "       SUM(c.valor_vendedor) custo, a.titulo "
        "FROM venda_cupom c "
        # O título vem da última coleta em que ESTE anúncio apareceu, e não da
        # última coleta da conta: anúncio pausado ou encerrado sai do snapshot
        # atual e ficaria na lista como um MLB cru, sem nome.
        "LEFT JOIN snap_anuncio a ON a.item_id = c.item_id "
        "     AND a.conta_slug = c.conta_slug "
        "     AND a.coletado_em = (SELECT MAX(coletado_em) FROM snap_anuncio "
        "                          WHERE conta_slug = ? AND item_id = c.item_id "
        "                            AND titulo IS NOT NULL) "
        f"WHERE c.conta_slug = ? AND c.tipo = 'coupon' AND c.valor_vendedor > 0 "
        f"AND c.{onde_c} "
        f"GROUP BY c.item_id ORDER BY pedidos DESC, custo DESC",
        (conta_slug, conta_slug, arg)).fetchall()

    pedidos = medido["pedidos"] or 0
    faturamento = medido["faturamento"] or 0.0
    gasto = custo["c"] or 0.0

    # Medir só a janela pedida mistura campanhas: a conta pode ter tido cupom
    # antes desta. Foi o que fez o medido (126) passar o que o ML registra
    # para a campanha atual (107) — não era erro, eram duas campanhas somadas.
    campanhas = []
    for c in ultima(con, conta_slug):
        if c["status"] not in VIVAS:
            continue
        d = dict(c)
        if c["inicio"]:
            d["desde_o_inicio"] = _medir_janela(con, conta_slug, c["inicio"])
        campanhas.append(d)

    return {
        "dias": dias,
        "desde": desde,
        "campanhas": campanhas,
        # Cada linha de venda_cupom é UM cupom aplicado. Não é o mesmo que
        # "pedidos": um pedido pode carregar mais de um cupom, e é essa
        # contagem — não a de pedidos — que se compara com o used_coupons
        # que o Mercado Livre informa.
        "cupons": custo["linhas"] or 0,
        "pedidos": pedidos,
        "faturamento": faturamento,
        "custo": gasto,
        "custo_sobre_faturamento": (gasto / faturamento * 100) if faturamento else None,
        "ticket": (faturamento / pedidos) if pedidos else None,
        "produtos": [dict(p) for p in produtos],
        "periodo": periodo_coberto(con, conta_slug),
    }


def dependencia_por_produto(con: sqlite3.Connection, conta_slug: str,
                            dias: int = 60, desde: str | None = None) -> list[dict]:
    """
    De cada produto, quanto das vendas passou pelo cupom.

    É a leitura que a lista de "itens vendidos com cupom" não dá. Quinze
    vendas com cupom num produto que vendeu duzentas é desconto dado a quem
    já ia comprar; quinze num que vendeu dezoito é um produto que só gira
    com cupom. Mesma lista, decisão oposta.

    O denominador sai da tabela `venda`, que guarda os itens de TODO pedido —
    é para isso que ela existe.
    """
    vivos = "(status IS NULL OR status NOT IN ('cancelled','invalid'))"

    if desde:
        onde_data, args_data = "data_pedido >= ?", [desde]
    else:
        onde_data, args_data = f"data_pedido >= datetime('now', '-{dias} days')", []

    # vendas totais por item: a coluna 'itens' guarda os MLB separados por vírgula
    totais: dict[str, int] = {}
    for l in con.execute(
            f"SELECT itens FROM venda WHERE conta_slug = ? AND {onde_data} AND {vivos}",
            (conta_slug, *args_data)):
        for item in (l["itens"] or "").split(","):
            item = item.strip()
            if item:
                totais[item] = totais.get(item, 0) + 1

    com_cupom = con.execute(
        f"SELECT c.item_id, COUNT(DISTINCT c.order_id) pedidos, "
        f"       SUM(c.valor_vendedor) custo, a.titulo "
        f"FROM venda_cupom c "
        f"LEFT JOIN snap_anuncio a ON a.item_id = c.item_id "
        f"     AND a.conta_slug = c.conta_slug "
        f"     AND a.coletado_em = (SELECT MAX(coletado_em) FROM snap_anuncio "
        f"                          WHERE conta_slug = ? AND item_id = c.item_id "
        f"                            AND titulo IS NOT NULL) "
        f"WHERE c.conta_slug = ? AND c.tipo = 'coupon' AND c.valor_vendedor > 0 "
        f"AND c.{onde_data} "
        f"GROUP BY c.item_id",
        (conta_slug, conta_slug, *args_data)).fetchall()

    saida = []
    for l in com_cupom:
        total = totais.get(l["item_id"], 0)
        pedidos = l["pedidos"] or 0
        saida.append({
            "item_id": l["item_id"], "titulo": l["titulo"],
            "com_cupom": pedidos, "vendas_totais": total,
            "sem_cupom": max(total - pedidos, 0),
            "dependencia": (pedidos / total * 100) if total else None,
            "custo": l["custo"] or 0.0,
        })
    # Um produto que vendeu duas vezes, as duas com cupom, dá 100% de
    # dependência e lideraria a tabela — sem significar nada. Quem tem volume
    # ordena primeiro; os de duas vendas ou menos ficam no fim, visíveis mas
    # sem roubar a leitura.
    MINIMO = 3
    saida.sort(key=lambda x: ((x["vendas_totais"] or 0) >= MINIMO,
                              x["dependencia"] or 0, x["com_cupom"]), reverse=True)
    return saida


def compradores(con: sqlite3.Connection, conta_slug: str,
                desde: str, dias_historico: int = 60) -> dict:
    """
    Quantos dos que usaram cupom nunca tinham comprado antes na conta.

    "Antes" é dentro do que a coleta enxerga. Um comprador de dois anos atrás
    aparece como novo, e por isso a janela de comparação vai declarada no
    resultado — sem ela o número vira uma promessa que os dados não cobrem.
    """
    vivos = "(status IS NULL OR status NOT IN ('cancelled','invalid'))"

    com_cupom = {l["comprador"] for l in con.execute(
        f"SELECT DISTINCT v.comprador FROM venda v WHERE v.conta_slug = ? "
        f"AND v.data_pedido >= ? AND {vivos} AND v.comprador IS NOT NULL "
        f"AND v.order_id IN (SELECT order_id FROM venda_cupom WHERE conta_slug = ? "
        f"  AND tipo = 'coupon' AND valor_vendedor > 0)",
        (conta_slug, desde, conta_slug))}

    antes = {l["comprador"] for l in con.execute(
        f"SELECT DISTINCT comprador FROM venda WHERE conta_slug = ? "
        f"AND data_pedido < ? AND {vivos} AND comprador IS NOT NULL",
        (conta_slug, desde))}

    novos = com_cupom - antes
    inicio_historico = con.execute(
        "SELECT MIN(data_pedido) d FROM venda WHERE conta_slug = ?",
        (conta_slug,)).fetchone()["d"]

    return {
        "com_cupom": len(com_cupom),
        "novos": len(novos),
        "recorrentes": len(com_cupom) - len(novos),
        "pct_novos": (len(novos) / len(com_cupom) * 100) if com_cupom else None,
        "historico_desde": inicio_historico,
        "sem_id": not com_cupom,
    }


def contraste_com_desconto(con: sqlite3.Connection, conta_slug: str,
                           dias: int = 60) -> dict:
    """Cupom contra o resto do desconto que sai do vendedor, no mesmo período."""
    l = con.execute(
        "SELECT IFNULL(tipo,'?') tipo, SUM(valor_vendedor) v, "
        "       COUNT(DISTINCT order_id) pedidos "
        "FROM venda_cupom WHERE conta_slug = ? AND valor_vendedor > 0 "
        "AND data_pedido >= datetime('now', ?) GROUP BY tipo",
        (conta_slug, f"-{dias} days")).fetchall()
    por = {x["tipo"]: {"valor": x["v"] or 0.0, "pedidos": x["pedidos"] or 0} for x in l}
    cupom = por.get("coupon", {"valor": 0.0, "pedidos": 0})
    outro = por.get("discount", {"valor": 0.0, "pedidos": 0})
    total = cupom["valor"] + outro["valor"]
    return {"cupom": cupom, "campanha_de_preco": outro, "total": total,
            "cupom_pct": (cupom["valor"] / total * 100) if total else None}
