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

# Quantos recursos buscar por rodada. Cada notificação custa pelo menos uma
# chamada ao ML, e um despejo represado chega às centenas — sem teto, uma
# rodada de recuperação consumiria a cota que as outras contas precisam.
MAX_BUSCAS = 150

# Quanto pedir ao dreno. Maior que MAX_BUSCAS de propósito: as que não couberem
# no orçamento de busca continuam pendentes lá e voltam na próxima, e conhecer
# o tamanho da fila é informação (é assim que se descobre que ela cresce mais
# rápido do que se drena).
LOTE_DO_DRENO = 500


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


def _chamar(url: str, segredo: str, metodo: str = "GET", corpo: dict | None = None) -> dict:
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo)
    req.add_header("Authorization", f"Bearer {segredo}")
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


def drenar(con: sqlite3.Connection, *, max_buscas: int = MAX_BUSCAS) -> dict:
    """Busca o que chegou, lê cada recurso e confirma o que fechou.

    CONFIRMA SÓ O QUE TERMINOU. Falha de rede ou 5xx do ML deixa a notificação
    pendente de propósito: ela volta na próxima rodada. Confirmar o que não foi
    lido seria perder o aviso em silêncio, que é exatamente o que este desenho
    inteiro existe para evitar.

    Recusa DEFINITIVA — 403 de posse, 404 — também confirma, com o erro
    gravado. Insistir num recurso que o ML nunca vai devolver é represar a fila
    atrás de uma linha morta. E a recusa é informação: 403 de posse num anúncio
    nosso diz que ele mudou de dono.
    """
    url, segredo = _configuracao()
    carimbo = agora_iso()

    resposta = _chamar(f"{url}/ml-callback-zionml?limite={LOTE_DO_DRENO}", segredo)
    pendentes = resposta.get("pendentes") or []
    if not pendentes:
        return {"pendentes": 0, "lidos": 0, "confirmados": 0, "fretes": 0}

    contas = _contas_por_user_id()
    clientes: dict[str, MLClient] = {}
    linhas: list[dict] = []
    confirmar: list[int] = []
    lidos = fretes = sem_conta = 0

    for n in pendentes:
        if lidos >= max_buscas:
            break
        user_id = str(n.get("user_id_ml") or "")
        conta = contas.get(user_id)
        recurso = str(n.get("recurso") or "")

        base = {
            "notificacao_id": n.get("notificacao_id"), "topico": n.get("topico"),
            "recurso": recurso, "user_id_ml": user_id,
            "conta_slug": conta.slug if conta else None,
            "cliente_id": conta.cliente_id if conta else None,
            "enviado_em": n.get("enviado_em"), "drenado_em": carimbo,
            "http": None, "erro": None, "corpo": None,
        }

        # user_id fora do registro: grava e confirma. Não é erro nosso e não
        # adianta tentar de novo — pode ser conta de outro app apontando para a
        # mesma URL, e a linha guardada é o que permite descobrir isso.
        if not conta:
            sem_conta += 1
            base["erro"] = "user_id fora do registro de contas"
            linhas.append(base)
            confirmar.append(int(n["id"]))
            continue

        if conta.slug not in clientes:
            try:
                clientes[conta.slug] = MLClient(conta.slug, user_id_esperado=conta.user_id)
            except Exception as erro:
                # Credencial quebrada NÃO confirma: é transitório do nosso lado
                # e a notificação tem que sobreviver ao conserto.
                base["erro"] = f"credencial: {erro}"[:300]
                linhas.append(base)
                continue
        cli = clientes[conta.slug]

        try:
            corpo = cli.get(recurso)
            base["http"] = 200 if corpo is not None else 404
            base["corpo"] = json.dumps(corpo, ensure_ascii=False)[:200_000] if corpo else None
            lidos += 1
            confirmar.append(int(n["id"]))
        except Exception as erro:
            base["erro"] = str(erro)[:300]
            base["http"] = getattr(getattr(erro, "response", None), "status_code", None)
            # 403 e 404 são definitivos; o resto volta na próxima.
            if base["http"] in (403, 404):
                confirmar.append(int(n["id"]))

        if base["http"] == 200 and str(n.get("topico")) == "shipments":
            try:
                fretes += int(_frete_do_envio(con, conta, cli, recurso, carimbo))
            except Exception:
                pass

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

    confirmados = 0
    if confirmar:
        # Confirma DEPOIS de gravar. Se o processo morrer entre as duas coisas,
        # a notificação volta e o INSERT OR IGNORE a descarta — perder trabalho
        # refeito é barato, perder o aviso não é.
        resp = _chamar(f"{url}/ml-callback-zionml", segredo, "PATCH", {"ids": confirmar})
        confirmados = int(resp.get("confirmados") or 0)

    return {
        "pendentes": len(pendentes), "lidos": lidos, "confirmados": confirmados,
        "fretes": fretes, "sem_conta": sem_conta,
        "restaram": max(0, len(pendentes) - len(confirmar)),
    }
