"""
Consome a caixa de correio do Mercado Livre.

O DESENHO, EM UMA FRASE
-----------------------
O ML avisa o Zion-OS, que só guarda o PONTEIRO; esta máquina vem buscar o que
o ponteiro aponta, com o token da conta certa.

A divisão não é arbitrária. O ML só avisa quem responde 200 em 500 ms, sempre,
e esta máquina desliga — por isso a caixa de correio mora num servidor. Mas o
token de cada conta de cliente mora AQUI e não deve sair: por isso o servidor
guarda `topic` e `resource` e mais nada. O que vaza de lá, se vazar, é o aviso
de que algo mudou. O que se lê com credencial é lido deste lado.

O QUE ISSO SUBSTITUI
--------------------
Varredura. O vigia pergunta de 5 em 5 minutos "mudou alguma coisa?" nas 8
contas, e o rate limit do ML é de 18.000 requisições por hora POR APLICAÇÃO —
não por conta. Perguntar custa cota que poderia estar sendo usada para ler o
que de fato mudou.

E chega tarde: em 12/09/2026, na primeira vez que a rota respondeu, entraram
246 notificações represadas de 7 contas — inclusive `public_candidates`, que é
convite de campanha COM PRAZO. Esses avisos vinham batendo num 404.

O QUE NÃO SUBSTITUI
-------------------
Visitas, conversão, reputação e `/performance` não têm tópico. Continuam
varredura, e continuarão.
"""
from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request

from . import db
from .config import Conta, carregar_clientes
from .ml_api import MLClient
from .notify import _carregar_env_raiz
from .utils import agora_iso

# Quantos RECURSOS DISTINTOS buscar por rodada — não quantas notificações.
#
# A diferença é o que faz a fila descer. Medido em 12/09/2026 sobre 5.273
# pendentes: o ML avisa 2,7 vezes o mesmo envio e 3,5 vezes o mesmo pedido, uma
# por mudança de status. Buscar por notificação é refazer o mesmo GET três
# vezes; buscar por recurso e confirmar todas as notificações que apontam para
# ele corta o trabalho em quase três.
#
# A primeira versão deste módulo tinha teto de 80 POR NOTIFICAÇÃO contra uma
# chegada de 85 por ciclo: a fila crescia para sempre, e o erro só apareceu
# quando alguém contou a fila em vez de olhar o lote.
MAX_RECURSOS = 200

# Quanto pedir ao dreno. Alto de propósito: é assim que se enxerga o tamanho
# real da fila. Com o lote em 500 o comando dizia "420 na fila" enquanto havia
# 5.273 — o número era do LOTE, não da fila, e escondia exatamente o problema
# que precisava ser visto.
LOTE_DO_DRENO = 1000   # o teto do proprio dreno no Zion-OS; pedir mais e ilusao


def _configuracao() -> tuple[str, str]:
    """URL da caixa de correio e o segredo, do .env da raiz.

    Reusa o leitor do `notify` em vez de reimplementar o parse: o formato do
    .env é o mesmo e duas cópias divergem.
    """
    env = _carregar_env_raiz()
    url = (env.get("ZION_OS_URL") or "").rstrip("/")
    segredo = env.get("CRON_SECRET") or ""
    if not url or not segredo:
        raise RuntimeError(
            "faltam ZION_OS_URL e/ou CRON_SECRET no .env da raiz. "
            "São o endereço da caixa de correio e o mesmo segredo que o worker "
            "do Zion-OS usa — sem eles não há o que drenar."
        )
    return url, segredo


# O Zion-OS está atrás do Cloudflare, e o Cloudflare recusa `Python-urllib/*`
# com 403 ANTES de a requisição chegar na rota. Medido em 12/09/2026: o mesmo
# GET com este User-Agent devolve 401 (a rota respondendo que o segredo não
# bate) e com o padrão do urllib devolve 403 — e 403 aqui não é "segredo
# errado", é "nem chegou".
#
# É identificação honesta, não navegador falso: quem lê o log do Cloudflare
# precisa saber que é a drenagem do zion-ml, não fingir que é gente.
AGENTE = "zion-ml/1.0 (drenagem de notificacoes do Mercado Livre)"


def _chamar(url: str, segredo: str, metodo: str = "GET", corpo: dict | None = None) -> dict:
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo)
    req.add_header("Authorization", f"Bearer {segredo}")
    req.add_header("User-Agent", AGENTE)
    if dados:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")


def _contas_por_user_id() -> dict[str, Conta]:
    return {
        str(c.user_id): c
        for cliente in carregar_clientes(apenas_ativos=False)
        for c in cliente.contas
        if c.user_id
    }


def _frete_do_envio(con: sqlite3.Connection, conta: Conta, cli: MLClient,
                    recurso: str, carimbo: str) -> bool:
    """Notificação de envio vira frete COBRADO, se ainda não estiver no banco.

    É o único tratamento especializado aqui, e existe porque o ganho é direto:
    `frete_venda` guarda o que o ML de fato cobrou do vendedor, que é o número
    que fecha a margem realizada. Antes ele só entrava na coleta, por varredura
    dos pedidos recentes; agora entra quando o envio acontece.

    Devolve True quando gravou algo. Não é erro não gravar: a maior parte das
    notificações de `shipments` é mudança de status de um envio cujo custo já
    está aqui, e reler custo que não mudou é gastar cota à toa.
    """
    envio_id = recurso.rstrip("/").split("/")[-1]
    if not envio_id.isdigit():
        return False

    ja = con.execute(
        "SELECT 1 FROM frete_venda WHERE shipment_id = ? AND custo_vendedor IS NOT NULL",
        (envio_id,),
    ).fetchone()
    if ja:
        return False

    try:
        custos = cli.custo_do_envio(envio_id)
    except Exception:
        return False
    if not custos or custos.get("custo_vendedor") is None:
        return False

    db.gravar_fretes_de_venda(con, [{
        "lido_em": carimbo, "cliente_id": conta.cliente_id, "conta_slug": conta.slug,
        "shipment_id": envio_id, "order_id": None, "data_pedido": None,
        "item_id": None, "titulo": None, "unidades": None, "receita": None,
        "custo_comprador": custos.get("custo_comprador"),
        "custo_vendedor": custos.get("custo_vendedor"),
        "promovido": custos.get("promovido"),
        "logistic_type": None, "status_envio": None,
    }])
    return True


def _ja_sabemos(con: sqlite3.Connection, topico: str, recurso: str) -> bool:
    """Este aviso ainda tem o que ensinar?

    Notificação de envio cujo custo já está em `frete_venda` não rende nada: o
    frete de um envio não muda depois de cobrado, e cada releitura gasta cota
    que a fila precisa. Como o ML avisa 2,7 vezes o mesmo envio, isso sozinho
    derruba a maior fatia do trabalho.

    Vale só para `shipments`, de propósito. Nos outros tópicos o recurso MUDA
    entre um aviso e outro — é esse o ponto deles.
    """
    if topico != "shipments":
        return False
    envio = recurso.rstrip("/").split("/")[-1]
    if not envio.isdigit():
        return False
    return bool(con.execute(
        "SELECT 1 FROM frete_venda WHERE shipment_id = ? AND custo_vendedor IS NOT NULL",
        (envio,)).fetchone())


def _item_do_convite(recurso: str, corpo) -> str | None:
    """O anúncio que o ML acabou de convidar para uma campanha.

    O `resource` já traz o item embutido — `CANDIDATE-MLB123-456` —, mas quem
    manda é o corpo: o id é formato, o corpo é dado. Só interessa quem está em
    `candidate`, que é o momento em que existe decisão a tomar. `started` e
    `finished` são história, e a coleta normal já os vê.
    """
    if not isinstance(corpo, dict):
        return None
    if str((corpo.get("status") or {}).get("id")) != "candidate":
        return None
    item = corpo.get("item_id")
    return str(item) if item else None


def drenar(con: sqlite3.Connection, *, max_recursos: int = MAX_RECURSOS) -> dict:
    """Busca o que chegou, le cada RECURSO uma vez e confirma o que fechou.

    Agrupa por recurso antes de buscar: o ML avisa a mesma coisa varias vezes,
    e todas as notificacoes que apontam para o mesmo caminho sao respondidas
    por um GET so. Confirmar as irmas junto e' o que impede a fila de crescer.

    CONFIRMA SO O QUE TERMINOU. Falha de rede ou 5xx deixa pendente de
    proposito: volta na proxima. Confirmar o que nao foi lido seria perder o
    aviso em silencio, que e' o que este desenho existe para evitar.

    Recusa DEFINITIVA — 403 de posse, 404, 400 — tambem confirma, com o erro
    gravado. Insistir num recurso que o ML nunca vai devolver represa a fila
    atras de uma linha morta, e o 400 do /seller-promotions/candidates provou
    que isso acontece.
    """
    url, segredo = _configuracao()
    carimbo = agora_iso()

    resposta = _chamar(f"{url}/ml-callback-zionml?limite={LOTE_DO_DRENO}", segredo)
    pendentes = resposta.get("pendentes") or []
    if not pendentes:
        return {"pendentes": 0, "recursos": 0, "lidos": 0, "pulados": 0,
                "confirmados": 0, "fretes": 0, "restaram": 0}

    contas = _contas_por_user_id()
    clientes: dict[str, MLClient] = {}

    # (topico, recurso) -> as notificacoes que apontam para ele
    por_recurso: dict[tuple, list[dict]] = {}
    for n in pendentes:
        por_recurso.setdefault((str(n.get("topico")), str(n.get("recurso"))), []).append(n)

    linhas: list[dict] = []
    confirmar: list[int] = []
    # Convite de campanha, por conta. Não vira alerta aqui: a régua de quando
    # uma campanha compensa mora em core/promocoes.py e core/rules.py, e
    # decidir de novo neste módulo criaria um segundo veredito que um dia
    # discorda do primeiro. Aqui só se junta QUEM precisa ser avaliado.
    convites: dict[str, list[str]] = {}
    lidos = pulados = fretes = sem_conta = 0

    for (topico, recurso), avisos in por_recurso.items():
        if lidos >= max_recursos:
            break
        n = avisos[0]
        user_id = str(n.get("user_id_ml") or "")
        conta = contas.get(user_id)
        ids = [int(a["id"]) for a in avisos]

        base = {
            "notificacao_id": n.get("notificacao_id"), "topico": topico,
            "recurso": recurso, "user_id_ml": user_id,
            "conta_slug": conta.slug if conta else None,
            "cliente_id": conta.cliente_id if conta else None,
            "enviado_em": n.get("enviado_em"), "drenado_em": carimbo,
            "http": None, "erro": None, "corpo": None,
        }

        if not conta:
            sem_conta += len(ids)
            base["erro"] = "user_id fora do registro de contas"
            linhas.append(base); confirmar.extend(ids)
            continue

        # Ja sabido: confirma sem gastar chamada. Nao grava linha — nao ha o
        # que registrar sobre um aviso que nao ensinou nada.
        if _ja_sabemos(con, topico, recurso):
            pulados += len(ids)
            confirmar.extend(ids)
            continue

        if conta.slug not in clientes:
            try:
                clientes[conta.slug] = MLClient(conta.slug, user_id_esperado=conta.user_id)
            except Exception as erro:
                base["erro"] = f"credencial: {erro}"[:300]
                linhas.append(base)
                continue
        cli = clientes[conta.slug]

        try:
            corpo = cli.get(recurso)
            base["http"] = 200 if corpo is not None else 404
            base["corpo"] = json.dumps(corpo, ensure_ascii=False)[:200_000] if corpo else None
            lidos += 1
            confirmar.extend(ids)
        except Exception as erro:
            base["erro"] = str(erro)[:300]
            base["http"] = getattr(getattr(erro, "response", None), "status_code", None)
            lidos += 1
            if base["http"] in (400, 403, 404):
                confirmar.extend(ids)

        if base["http"] == 200 and topico == "shipments":
            try:
                fretes += int(_frete_do_envio(con, conta, cli, recurso, carimbo))
            except Exception:
                pass

        if base["http"] == 200 and topico == "public_candidates":
            item = _item_do_convite(recurso, corpo)
            if item:
                convites.setdefault(conta.slug, []).append(item)

        linhas.append(base)

    if linhas:
        con.executemany(
            "INSERT OR IGNORE INTO notificacao_ml "
            "(notificacao_id, topico, recurso, user_id_ml, conta_slug, cliente_id, "
            " enviado_em, drenado_em, http, erro, corpo) "
            "VALUES (:notificacao_id, :topico, :recurso, :user_id_ml, :conta_slug, "
            " :cliente_id, :enviado_em, :drenado_em, :http, :erro, :corpo)",
            linhas,
        )
        con.commit()

    # Os convites viram alerta pelo caminho de sempre: coletar as campanhas
    # do anúncio e deixar `rules.avaliar_promocoes` cruzar com o piso. É a
    # mesma régua que a coleta usa — o que muda é a HORA de rodá-la. Convite
    # tem prazo, e saber dele no dia seguinte é saber tarde.
    alertas = 0
    if convites:
        from . import promocoes, rules
        for slug, itens in convites.items():
            conta = next((c for c in contas.values() if c.slug == slug), None)
            if not conta or slug not in clientes:
                continue
            try:
                n, carimbo_promo = promocoes.coletar(con, conta, clientes[slug],
                                                     sorted(set(itens)))
                if n:
                    alertas += rules.avaliar_promocoes(con, conta, carimbo_promo)
            except Exception:
                # Campanha indisponível não pode derrubar a drenagem: o resto
                # já foi lido e precisa ser confirmado.
                continue

    confirmados = 0
    if confirmar:
        # Confirma DEPOIS de gravar. Morrendo entre as duas coisas, a
        # notificacao volta e o INSERT OR IGNORE a descarta — trabalho refeito
        # e' barato, aviso perdido nao e'.
        for i in range(0, len(confirmar), 1000):
            resp = _chamar(f"{url}/ml-callback-zionml", segredo, "PATCH",
                           {"ids": confirmar[i:i + 1000]})
            confirmados += int(resp.get("confirmados") or 0)

    return {
        "pendentes": len(pendentes), "recursos": len(por_recurso),
        "lidos": lidos, "pulados": pulados, "confirmados": confirmados,
        "fretes": fretes, "sem_conta": sem_conta,
        "convites": sum(len(v) for v in convites.values()), "alertas": alertas,
        "restaram": len(pendentes) - len(confirmar),
    }
