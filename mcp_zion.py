#!/usr/bin/env python3
"""
Servidor MCP do zion-ml — deixa o Claude conversar com a operação.

O QUE É
-------
Um servidor MCP (Model Context Protocol) que roda NESTA máquina e expõe o
que o zion-ml já sabe como um conjunto de ferramentas. O Claude passa a
consultar contas, anúncios, margens, alertas e concorrência sem que ninguém
cole dado nenhum no chat.

DUAS REGRAS QUE ESTE ARQUIVO NÃO NEGOCIA
----------------------------------------
1. Nenhuma ferramenta aqui ESCREVE na API do Mercado Livre. Nada de publicar,
   alterar preço, pausar ou aceitar campanha. Leitura do banco, leitura da
   configuração e — no máximo — deixar um pedido na fila que já existe.

2. Credencial não passa por aqui. Os .env de cada conta continuam sendo lidos
   só por core.auth, e apenas na ferramenta `checar_credencial`, que fala com
   o ML para confirmar de quem é o token. O conteúdo do .env nunca é devolvido.

POR QUE SEM BIBLIOTECA
----------------------
O protocolo MCP sobre stdio é JSON-RPC 2.0 em linhas de texto. Implementar à
mão custa ~80 linhas e evita um `pip install` numa máquina que roda sozinha,
com Agendador de Tarefas, e onde uma dependência quebrada de madrugada é um
problema que ninguém vê acontecer. O zion-ml continua com requests + PyYAML.

COMO LIGAR
----------
Ver docs/MCP.md. Para conferir que está de pé sem falar protocolo:

    python mcp_zion.py --autoteste
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core import config, db                                    # noqa: E402
from core.utils import agora_iso, para_br, preco_real           # noqa: E402

SERVIDOR = {"name": "zion-ml", "title": "Zion ML", "version": "1.0.0"}

# Versões do protocolo que sabemos responder. Se o cliente pedir uma delas,
# devolvemos a mesma; senão devolvemos a nossa e deixamos ele decidir.
PROTOCOLOS = ("2025-06-18", "2025-03-26", "2024-11-05")
PROTOCOLO_PADRAO = PROTOCOLOS[0]

LIMITE_PADRAO = 40
LIMITE_MAXIMO = 200

REGISTRO: dict[str, dict] = {}          # nome -> {schema, fn}


# ---------------------------------------------------------------- utilidades

def _log(mensagem: str) -> None:
    """
    Diagnóstico vai para stderr e para data/mcp.log — NUNCA para stdout.

    stdout é o canal do protocolo: um print solto ali derruba a conexão com
    uma mensagem que o cliente não sabe interpretar.
    """
    linha = f"[{agora_iso()}] {mensagem}"
    print(linha, file=sys.stderr, flush=True)
    try:
        destino = RAIZ / "data" / "mcp.log"
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("a", encoding="utf-8") as fh:
            fh.write(linha + "\n")
    except Exception:
        pass


def _dict(linha) -> dict:
    """sqlite3.Row -> dict, tolerante a None."""
    return dict(linha) if linha is not None else {}


def _limite(valor, padrao: int = LIMITE_PADRAO) -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return padrao
    return max(1, min(n, LIMITE_MAXIMO))


def _quando(iso: str | None) -> str | None:
    """Carimbo UTC do banco convertido para o horário de operação."""
    if not iso:
        return None
    try:
        return para_br(iso)
    except Exception:
        return iso


def _conta_ou_erro(slug: str) -> config.Conta:
    if not slug:
        raise ValueError("informe o slug da conta (use listar_contas para ver quais existem)")
    return config.obter_conta(slug)


def ferramenta(nome: str, descricao: str, propriedades: dict,
               obrigatorios: list[str] | None = None) -> Callable:
    """Registra uma função como ferramenta MCP."""
    def decorador(fn: Callable) -> Callable:
        REGISTRO[nome] = {
            "fn": fn,
            "schema": {
                "name": nome,
                "description": descricao.strip(),
                "inputSchema": {
                    "type": "object",
                    "properties": propriedades,
                    "required": obrigatorios or [],
                    "additionalProperties": False,
                },
            },
        }
        return fn
    return decorador


# ------------------------------------------------------------- 1. panorama

@ferramenta(
    "listar_contas",
    """Quem são os clientes, quais contas de Mercado Livre cada um tem, se a
    credencial está configurada e quando foi a última coleta de cada uma.
    É o ponto de partida: toda outra ferramenta é endereçada por slug.""",
    {"incluir_inativos": {"type": "boolean",
                          "description": "Inclui clientes com status diferente de ativo."}},
)
def _listar_contas(incluir_inativos: bool = False) -> dict:
    con = db.conectar()
    try:
        saida = []
        for cliente in config.carregar_clientes(apenas_ativos=not incluir_inativos):
            contas = []
            for c in cliente.contas:
                ultima = db.ultima_coleta(con, "snap_anuncio", c.slug)
                ativos = con.execute(
                    "SELECT COUNT(*) FROM snap_anuncio WHERE conta_slug = ? "
                    "AND coletado_em = ? AND status = 'active'",
                    (c.slug, ultima)).fetchone()[0] if ultima else 0
                contas.append({
                    "slug": c.slug,
                    "nome_conta": c.nome_conta,
                    "papel": c.papel,
                    "credencial_configurada": c.configurada,
                    "coordenar_preco": c.coordenar_preco,
                    "ultima_coleta": _quando(ultima),
                    "anuncios_ativos": ativos,
                    "observacoes": c.observacoes.strip() or None,
                })
            saida.append({
                "cliente_id": cliente.id, "nome": cliente.nome,
                "nicho": cliente.nicho, "status": cliente.status,
                "contas": contas,
            })
        return {"clientes": saida}
    finally:
        con.close()


@ferramenta(
    "checar_credencial",
    """Pergunta AO MERCADO LIVRE de quem é o token desta conta e devolve o
    apelido da loja. Única ferramenta que fala com a API — e só lê.
    Rode antes de qualquer decisão que vá virar alteração na conta:
    é a defesa contra operar o cliente errado.""",
    {"conta": {"type": "string", "description": "Slug da conta."}},
    ["conta"],
)
def _checar_credencial(conta: str) -> dict:
    c = _conta_ou_erro(conta)
    from core.ml_api import MLClient                 # importado aqui: só esta ferramenta usa rede
    cli = MLClient(c.slug, user_id_esperado=c.user_id, verificar=True)
    perfil = cli.perfil_do_vendedor(c.user_id) or {}
    return {
        "conta": c.slug,
        "cliente": c.cliente_nome,
        "nickname": perfil.get("nickname"),
        "user_id": c.user_id,
        "confere": True,
        "aviso": "Confirme que o apelido acima é mesmo a loja que você quer mexer.",
    }


@ferramenta(
    "panorama_conta",
    """Retrato mais recente de uma conta: reputação, nível, transações,
    anúncios ativos e pausados, vendas e receita da janela.""",
    {"conta": {"type": "string", "description": "Slug da conta."}},
    ["conta"],
)
def _panorama_conta(conta: str) -> dict:
    c = _conta_ou_erro(conta)
    con = db.conectar()
    try:
        linha = con.execute(
            "SELECT * FROM snap_conta WHERE conta_slug = ? "
            "ORDER BY coletado_em DESC LIMIT 1", (c.slug,)).fetchone()
        if not linha:
            return {"conta": c.slug, "erro": "esta conta ainda não tem coleta de saúde",
                    "sugestao": "encomendar coletar para este slug"}
        d = _dict(linha)
        d.pop("id", None)
        d["coletado_em"] = _quando(d.get("coletado_em"))
        d["cliente"] = c.cliente_nome
        return d
    finally:
        con.close()


@ferramenta(
    "diagnostico_conta",
    """Leitura interpretada da conta: dinheiro parado em anúncio pausado com
    estoque, ativo sem estoque, canibalização entre anúncios do mesmo produto,
    conversão e situação no catálogo. É o mesmo motor do `cli.py diagnostico`.""",
    {"conta": {"type": "string", "description": "Slug da conta."}},
    ["conta"],
)
def _diagnostico_conta(conta: str) -> dict:
    c = _conta_ou_erro(conta)
    from core import diagnostico
    con = db.conectar()
    try:
        r = diagnostico.analisar(con, c.slug)
        if r.get("erro"):
            return {"conta": c.slug, "erro": r["erro"],
                    "sugestao": "encomendar coletar para este slug"}
        r["conta"] = c.slug
        r["cliente"] = c.cliente_nome
        r["visitas_de"] = _quando(r.get("visitas_de"))
        return r
    finally:
        con.close()


# -------------------------------------------------------------- 2. anúncios

ORDENS = {"vendidos": "vendidos DESC", "preco": "preco DESC", "estoque": "estoque DESC",
          "visitas": "visitas_7d DESC", "saude": "saude ASC", "titulo": "titulo ASC"}


@ferramenta(
    "anuncios",
    """Os anúncios da conta na coleta mais recente. Preço devolvido é o de
    VITRINE quando existe medição (o de cadastro ignora campanha promocional
    e faz comparação errada).""",
    {
        "conta": {"type": "string", "description": "Slug da conta."},
        "status": {"type": "string", "enum": ["active", "paused", "closed", "todos"],
                   "description": "Filtro de status. Padrão: todos."},
        "busca": {"type": "string", "description": "Trecho do título ou do SKU."},
        "ordenar_por": {"type": "string", "enum": list(ORDENS),
                        "description": "Padrão: vendidos."},
        "limite": {"type": "integer", "description": f"Padrão {LIMITE_PADRAO}, teto {LIMITE_MAXIMO}."},
    },
    ["conta"],
)
def _anuncios(conta: str, status: str = "todos", busca: str = "",
              ordenar_por: str = "vendidos", limite: int = LIMITE_PADRAO) -> dict:
    c = _conta_ou_erro(conta)
    con = db.conectar()
    try:
        carimbo = db.ultima_coleta(con, "snap_anuncio", c.slug)
        if not carimbo:
            return {"conta": c.slug, "erro": "sem coleta",
                    "sugestao": "encomendar coletar para este slug"}
        sql = "SELECT * FROM snap_anuncio WHERE conta_slug = ? AND coletado_em = ?"
        args: list[Any] = [c.slug, carimbo]
        if status and status != "todos":
            sql += " AND status = ?"
            args.append(status)
        if busca:
            sql += " AND (titulo LIKE ? OR IFNULL(sku,'') LIKE ?)"
            args += [f"%{busca}%", f"%{busca}%"]
        sql += f" ORDER BY {ORDENS.get(ordenar_por, ORDENS['vendidos'])} LIMIT ?"
        args.append(_limite(limite))

        vitrines = db.vitrines_recentes(con, c.slug)
        itens = []
        for l in con.execute(sql, args):
            itens.append({
                "item_id": l["item_id"], "titulo": l["titulo"],
                "preco": preco_real(l, vitrines), "preco_cadastro": l["preco"],
                "estoque": l["estoque"], "vendidos": l["vendidos"],
                "status": l["status"], "sub_status": l["sub_status"],
                "tipo_anuncio": l["tipo_anuncio"], "catalogo": bool(l["catalogo"]),
                "produto_catalogo": l["produto_catalogo"], "saude": l["saude"],
                "frete_gratis": bool(l["frete_gratis"]), "visitas_7d": l["visitas_7d"],
                "permalink": l["permalink"],
            })
        return {"conta": c.slug, "coletado_em": _quando(carimbo),
                "total": len(itens), "anuncios": itens}
    finally:
        con.close()


@ferramenta(
    "anuncio",
    """Tudo o que se sabe de UM anúncio: estado atual, tarifa realmente medida
    pelo ML (não a comissão redonda do conta.yaml), campanhas abertas, margem
    contra o piso e as últimas leituras de preço e estoque.""",
    {
        "conta": {"type": "string", "description": "Slug da conta."},
        "item_id": {"type": "string", "description": "MLB do anúncio."},
    },
    ["conta", "item_id"],
)
def _anuncio(conta: str, item_id: str) -> dict:
    c = _conta_ou_erro(conta)
    con = db.conectar()
    try:
        atual = con.execute(
            "SELECT * FROM snap_anuncio WHERE conta_slug = ? AND item_id = ? "
            "ORDER BY coletado_em DESC LIMIT 1", (c.slug, item_id)).fetchone()
        if not atual:
            return {"conta": c.slug, "item_id": item_id,
                    "erro": "este anúncio não aparece em nenhuma coleta desta conta"}

        vitrines = db.vitrines_recentes(con, c.slug)
        d = _dict(atual)
        d.pop("id", None)
        d["coletado_em"] = _quando(d["coletado_em"])
        d["preco_real"] = preco_real(atual, vitrines)

        tarifa = db.tarifas_medidas(con, c.slug).get(item_id)
        if tarifa:
            tarifa["medido_em"] = _quando(tarifa["medido_em"])

        promos = [
            {k: v for k, v in _dict(l).items() if k != "id"}
            for l in con.execute(
                "SELECT * FROM snap_promocao WHERE conta_slug = ? AND item_id = ? "
                "AND coletado_em = (SELECT MAX(coletado_em) FROM snap_promocao "
                "                   WHERE conta_slug = ? AND item_id = ?)",
                (c.slug, item_id, c.slug, item_id))
        ]

        historico = [
            {"quando": _quando(l["coletado_em"]), "preco": preco_real(l, vitrines),
             "estoque": l["estoque"], "vendidos": l["vendidos"], "status": l["status"]}
            for l in con.execute(
                "SELECT * FROM snap_anuncio WHERE conta_slug = ? AND item_id = ? "
                "ORDER BY coletado_em DESC LIMIT 12", (c.slug, item_id))
        ]

        margem = None
        for m in _margens_calculadas(con, c):
            if m["item_id"] == item_id:
                margem = m
                break

        return {"conta": c.slug, "cliente": c.cliente_nome, "atual": d,
                "tarifa_medida": tarifa, "promocoes": promos,
                "margem": margem, "historico": historico}
    finally:
        con.close()


@ferramenta(
    "mudancas",
    """O que mudou entre as duas coletas mais recentes: preço, estoque, status
    e anúncio que sumiu ou apareceu. É a pergunta "o que aconteceu desde
    ontem" respondida sem abrir relatório.""",
    {
        "conta": {"type": "string", "description": "Slug da conta."},
        "limite": {"type": "integer", "description": f"Padrão {LIMITE_PADRAO}."},
    },
    ["conta"],
)
def _mudancas(conta: str, limite: int = LIMITE_PADRAO) -> dict:
    c = _conta_ou_erro(conta)
    con = db.conectar()
    try:
        agora = db.ultima_coleta(con, "snap_anuncio", c.slug)
        antes = db.ultima_coleta(con, "snap_anuncio", c.slug, antes_de=agora) if agora else None
        if not agora or not antes:
            return {"conta": c.slug,
                    "erro": "preciso de pelo menos duas coletas para comparar"}

        vitrines = db.vitrines_recentes(con, c.slug)
        hoje = db.snapshot_por_item(con, "snap_anuncio", c.slug, agora)
        ontem = db.snapshot_por_item(con, "snap_anuncio", c.slug, antes)

        mudou = []
        for item_id, linha in hoje.items():
            velho = ontem.get(item_id)
            if not velho:
                mudou.append({"item_id": item_id, "titulo": linha["titulo"],
                              "tipo": "apareceu"})
                continue
            p_novo, p_velho = preco_real(linha, vitrines), preco_real(velho, vitrines)
            if p_novo is not None and p_velho is not None and abs(p_novo - p_velho) > 0.009:
                mudou.append({
                    "item_id": item_id, "titulo": linha["titulo"], "tipo": "preço",
                    "de": p_velho, "para": p_novo,
                    "variacao_pct": round((p_novo - p_velho) / p_velho * 100, 2) if p_velho else None,
                })
            if linha["status"] != velho["status"]:
                mudou.append({"item_id": item_id, "titulo": linha["titulo"],
                              "tipo": "status", "de": velho["status"], "para": linha["status"]})
            e_novo, e_velho = linha["estoque"], velho["estoque"]
            if e_novo is not None and e_velho is not None and e_novo != e_velho:
                mudou.append({"item_id": item_id, "titulo": linha["titulo"],
                              "tipo": "estoque", "de": e_velho, "para": e_novo})

        for item_id, velho in ontem.items():
            if item_id not in hoje:
                mudou.append({"item_id": item_id, "titulo": velho["titulo"],
                              "tipo": "sumiu",
                              "permalink": db.permalink_do_anuncio(con, c.slug, item_id)})

        return {"conta": c.slug, "de": _quando(antes), "para": _quando(agora),
                "total": len(mudou), "mudancas": mudou[:_limite(limite)]}
    finally:
        con.close()


@ferramenta(
    "historico_preco",
    "Série de preço, estoque e vendas acumuladas de um anúncio ao longo do tempo.",
    {
        "conta": {"type": "string", "description": "Slug da conta."},
        "item_id": {"type": "string", "description": "MLB do anúncio."},
        "dias": {"type": "integer", "description": "Janela em dias. Padrão 30."},
    },
    ["conta", "item_id"],
)
def _historico_preco(conta: str, item_id: str, dias: int = 30) -> dict:
    c = _conta_ou_erro(conta)
    dias = max(1, min(int(dias or 30), 365))
    con = db.conectar()
    try:
        vitrines = db.vitrines_recentes(con, c.slug)
        linhas = con.execute(
            "SELECT * FROM snap_anuncio WHERE conta_slug = ? AND item_id = ? "
            "AND coletado_em >= datetime('now', ?) ORDER BY coletado_em",
            (c.slug, item_id, f"-{dias} days")).fetchall()
        serie = [{"quando": _quando(l["coletado_em"]), "preco": preco_real(l, vitrines),
                  "estoque": l["estoque"], "vendidos": l["vendidos"],
                  "status": l["status"]} for l in linhas]
        return {"conta": c.slug, "item_id": item_id, "dias": dias,
                "leituras": len(serie), "serie": serie}
    finally:
        con.close()


# ------------------------------------------------- 3. alertas, margem, preço

@ferramenta(
    "alertas",
    """Alertas gerados pelo motor de regras numa janela de horas. Aceita um
    slug, um cliente_id (traz todas as contas dele) ou nada (todas as contas).""",
    {
        "alvo": {"type": "string", "description": "slug | cliente_id | vazio para todas."},
        "horas": {"type": "integer", "description": "Janela. Padrão 24."},
        "apenas_criticos": {"type": "boolean"},
        "limite": {"type": "integer", "description": f"Padrão {LIMITE_PADRAO}."},
    },
)
def _alertas(alvo: str = "", horas: int = 24, apenas_criticos: bool = False,
             limite: int = LIMITE_PADRAO) -> dict:
    horas = max(1, min(int(horas or 24), 24 * 90))
    contas = config.resolver_contas(alvo or None, exigir_credencial=False)
    slugs = {c.slug for c in contas}
    con = db.conectar()
    try:
        saida = []
        for l in db.alertas_recentes(con, horas=horas):
            if l["conta_slug"] not in slugs:
                continue
            if apenas_criticos and not l["critico"]:
                continue
            saida.append({
                "quando": _quando(l["criado_em"]), "conta": l["conta_slug"],
                "regra": l["regra"], "critico": bool(l["critico"]),
                "item_id": l["item_id"], "titulo": l["titulo"],
                "mensagem": l["mensagem"],
            })
        return {"alvo": alvo or "todas", "horas": horas,
                "total": len(saida), "alertas": saida[:_limite(limite)]}
    finally:
        con.close()


def _margens_calculadas(con: sqlite3.Connection, conta) -> list[dict]:
    """
    Margem por anúncio, do motor de precificação. Sem planilha de custo na
    pasta da conta, devolve lista vazia — e isso não é falha: é a diferença
    entre não dar veredito e dar veredito errado.
    """
    from core import precificacao
    try:
        return precificacao.carregar(con, conta)
    except Exception as erro:                       # planilha ilegível não derruba o servidor
        _log(f"precificacao falhou em {conta.slug}: {erro}")
        return []


@ferramenta(
    "margens",
    """Margem de cada anúncio contra o piso de preço: custo + comissão medida
    + imposto + frete absorvido. `abaixo_do_piso` é o que está vendendo abaixo
    do que deveria. Depende da planilha de custos na pasta da conta.""",
    {
        "conta": {"type": "string", "description": "Slug da conta."},
        "apenas_abaixo_do_piso": {"type": "boolean"},
        "limite": {"type": "integer", "description": f"Padrão {LIMITE_PADRAO}."},
    },
    ["conta"],
)
def _margens(conta: str, apenas_abaixo_do_piso: bool = False,
             limite: int = LIMITE_PADRAO) -> dict:
    c = _conta_ou_erro(conta)
    from core import precificacao
    con = db.conectar()
    try:
        pano = precificacao.panorama(con, c)
        linhas = _margens_calculadas(con, c)
        if apenas_abaixo_do_piso:
            linhas = [l for l in linhas if l["abaixo_do_piso"]]
        linhas.sort(key=lambda l: (l["folga_pct"] if l["folga_pct"] is not None else 9e9))
        return {
            "conta": c.slug,
            "planilha": str(pano["planilha"].name) if pano.get("planilha") else None,
            "idade_da_planilha_dias": pano.get("idade"),
            "anuncios_ativos": pano.get("ativos"),
            "com_custo": pano.get("com_custo"),
            "abaixo_do_piso": pano.get("abaixo_do_piso"),
            "linhas_sem_anuncio": pano.get("sobras"),
            "erro": pano.get("erro"),
            "itens": linhas[:_limite(limite)],
        }
    finally:
        con.close()


@ferramenta(
    "promocoes_abertas",
    """Campanhas que o Mercado Livre está oferecendo aos anúncios da conta.
    Status 'candidate' é o que interessa: liberada e ainda não aceita.
    Quando há custo cadastrado, cada uma vem com veredito — cabe no piso ou
    fura o piso — e com quem banca o desconto (ML x vendedor).""",
    {
        "conta": {"type": "string", "description": "Slug da conta."},
        "apenas_candidatas": {"type": "boolean", "description": "Padrão true."},
        "limite": {"type": "integer", "description": f"Padrão {LIMITE_PADRAO}."},
    },
    ["conta"],
)
def _promocoes_abertas(conta: str, apenas_candidatas: bool = True,
                       limite: int = LIMITE_PADRAO) -> dict:
    c = _conta_ou_erro(conta)
    from core import promocoes
    con = db.conectar()
    try:
        carimbo = db.ultima_coleta(con, "snap_promocao", c.slug)
        if not carimbo:
            return {"conta": c.slug, "erro": "nenhuma sonda de promoções ainda",
                    "sugestao": "encomendar promocoes para este slug"}

        pisos = {m["item_id"]: m["piso"] for m in _margens_calculadas(con, c)}
        vitrines = db.vitrines_recentes(con, c.slug)
        precos = {}
        ult = db.ultima_coleta(con, "snap_anuncio", c.slug)
        if ult:
            for l in con.execute("SELECT * FROM snap_anuncio WHERE conta_slug = ? "
                                 "AND coletado_em = ?", (c.slug, ult)):
                precos[l["item_id"]] = preco_real(l, vitrines)

        saida = []
        for l in con.execute(
                "SELECT * FROM snap_promocao WHERE conta_slug = ? AND coletado_em = ?",
                (c.slug, carimbo)):
            if apenas_candidatas and l["status"] != "candidate":
                continue
            v = promocoes.veredito(l, pisos.get(l["item_id"]), precos.get(l["item_id"]))
            saida.append({
                "item_id": l["item_id"], "promocao_id": l["promocao_id"],
                "tipo": l["tipo"], "nome": promocoes.nome_legivel(l),
                "status": l["status"],
                "preco_hoje": precos.get(l["item_id"]),
                "preco_na_campanha": v.get("preco"),
                "piso": pisos.get(l["item_id"]),
                "conclusao": v.get("conclusao"), "cabe": v.get("cabe"),
                "sobra": v.get("sobra"), "queda_pct": v.get("queda_pct"),
                "parte_do_ml": l["parte_do_ml"], "parte_do_vendedor": l["parte_do_vendedor"],
                "fim": l["fim"],
            })
        saida.sort(key=lambda p: (p["cabe"] is not False, p["item_id"]))
        return {"conta": c.slug, "coletado_em": _quando(carimbo),
                "total": len(saida), "promocoes": saida[:_limite(limite)],
                "aviso": "Esta ferramenta só LÊ. Aceitar campanha continua sendo no aplicativo."}
    finally:
        con.close()


@ferramenta(
    "cupons",
    """Campanhas de cupom do vendedor: quantos cupons foram usados, quanto do
    orçamento já queimou, o custo médio por cupom e quais anúncios participam.

    Diferença que muda a conta: no cupom o Mercado Livre NÃO co-participa — o
    orçamento sai inteiro do vendedor. E `cupons_usados` é da campanha inteira;
    a API não diz em qual anúncio cada cupom foi usado.""",
    {
        "conta": {"type": "string", "description": "Slug da conta."},
        "incluir_encerradas": {"type": "boolean", "description": "Padrão false."},
        "horas": {"type": "integer",
                  "description": "Janela para medir o uso desde a leitura anterior. Padrão 24."},
    },
    ["conta"],
)
def _cupons(conta: str, incluir_encerradas: bool = False, horas: int = 24) -> dict:
    c = _conta_ou_erro(conta)
    from core import cupons as mod
    con = db.conectar()
    try:
        linhas = mod.ultima(con, c.slug)
        if not linhas:
            return {"conta": c.slug, "erro": "nenhuma coleta de cupom ainda",
                    "sugestao": "encomendar cupons para este slug"}
        movimento = mod.movimento(con, c.slug, horas=horas)

        saida = []
        for l in linhas:
            if not incluir_encerradas and l["status"] not in mod.VIVAS:
                continue
            consumo = mod.consumo(l)
            participantes = mod.anuncios_da_campanha(con, c.slug, l["promocao_id"])
            saida.append({
                "promocao_id": l["promocao_id"], "nome": l["nome"],
                "status": l["status"], "sub_tipo": l["sub_tipo"],
                "codigo": l["codigo"] or "aberto a todos os compradores",
                "desconto": (f"{l['percentual']}%" if l["percentual"]
                             else l["valor_fixo"]),
                "compra_minima": l["compra_minima"],
                "reembolso_maximo": l["compra_maxima"],
                "cupons_usados": l["cupons_usados"],
                "orcamento": l["orcamento"],
                "orcamento_restante": l["orcamento_restante"],
                "gasto": consumo["gasto"], "gasto_pct": consumo["gasto_pct"],
                "custo_medio_por_cupom": consumo["custo_medio"],
                "vale_ate": l["fim"],
                "movimento_recente": movimento.get(l["promocao_id"]),
                "anuncios": [{"item_id": p["item_id"], "titulo": p["titulo"],
                              "status": p["status"],
                              "preco": p["preco_vitrine"] or p["preco"]}
                             for p in participantes],
            })
        return {
            "conta": c.slug, "coletado_em": _quando(linhas[0]["coletado_em"]),
            "total": len(saida), "campanhas": saida,
            "nota": ("cupons_usados é o total da campanha; a API não atribui o uso a "
                     "um anúncio específico. O orçamento é 100% do vendedor."),
        }
    finally:
        con.close()


@ferramenta(
    "custo_de_cupom",
    """Quanto o cupom REALMENTE custou, por anúncio, medido nos pedidos.

    Separa o que saiu do bolso do vendedor do que o Mercado Livre bancou —
    distinção que o campo `coupon_amount` do pedido não faz e que, sem ela,
    infla o custo com desconto que o ML pagou. Depende de ter rodado
    `cupons <slug> --vendas`.""",
    {
        "conta": {"type": "string", "description": "Slug da conta."},
        "dias": {"type": "integer", "description": "Janela. Padrão 30."},
        "limite": {"type": "integer", "description": f"Padrão {LIMITE_PADRAO}."},
    },
    ["conta"],
)
def _custo_de_cupom(conta: str, dias: int = 30, limite: int = LIMITE_PADRAO) -> dict:
    c = _conta_ou_erro(conta)
    from core import cupons as mod
    dias = max(1, min(int(dias or 30), 365))
    con = db.conectar()
    try:
        resumo = mod.resumo_de_custo(con, c.slug, dias=dias)
        if not resumo["pedidos_com_cupom"]:
            return {"conta": c.slug, "dias": dias,
                    "erro": "nenhuma venda com cupom registrada nesta janela",
                    "sugestao": "encomendar cupons com a flag --vendas para este slug"}
        linhas = mod.custo_por_anuncio(con, c.slug, dias=dias)
        impacto = mod.impacto_do_cupom(con, c.slug, dias=dias)
        return {
            "conta": c.slug, "dias": dias, "resumo": resumo,
            "o_que_passou_pelo_cupom": impacto,
            "por_anuncio": [{
                "item_id": l["item_id"], "titulo": l["titulo"],
                "pedidos": l["pedidos"],
                "custo_do_vendedor": l["custo_vendedor"],
                "bancado_pelo_ml": l["bancado_pelo_ml"],
                "desconto_total": l["desconto_total"],
                "preco": l["preco_vitrine"] or l["preco"],
            } for l in linhas[:_limite(limite)]],
            "nota": ("custo_do_vendedor vem de amounts.seller do /orders/$ID/discounts. "
                     "O coupon_amount do pedido soma também os cupons do próprio ML. "
                     "Em o_que_passou_pelo_cupom, share e ticket são PARTICIPAÇÃO, não "
                     "causa: parte dessas vendas aconteceria sem o cupom."),
        }
    finally:
        con.close()


@ferramenta(
    "concorrencia",
    """Quem disputa os produtos da conta, a partir das fichas de catálogo e dos
    anúncios vigiados por link. Lembrete honesto: o ML fechou a busca por
    palavra-chave (403), então concorrente fora do catálogo dá para DESCOBRIR,
    não para ACOMPANHAR.""",
    {
        "conta": {"type": "string", "description": "Slug da conta."},
        "item_id": {"type": "string", "description": "Filtra por um anúncio seu (comparar_com)."},
        "limite": {"type": "integer", "description": f"Padrão {LIMITE_PADRAO}."},
    },
    ["conta"],
)
def _concorrencia(conta: str, item_id: str = "", limite: int = LIMITE_PADRAO) -> dict:
    c = _conta_ou_erro(conta)
    con = db.conectar()
    try:
        carimbo = db.ultima_coleta(con, "snap_concorrente", c.slug)
        if not carimbo:
            return {"conta": c.slug, "erro": "sem coleta de concorrência",
                    "sugestao": "encomendar mapear para este slug"}
        sql = ("SELECT * FROM snap_concorrente WHERE conta_slug = ? AND coletado_em = ?")
        args: list[Any] = [c.slug, carimbo]
        if item_id:
            sql += " AND comparar_com = ?"
            args.append(item_id)
        sql += " ORDER BY preco ASC LIMIT ?"
        args.append(_limite(limite))

        rivais = [{
            "item_id": l["item_id"], "titulo": l["titulo"], "preco": l["preco"],
            "vendedor": l["seller_nickname"], "seller_id": l["seller_id"],
            "vendidos": l["vendidos"], "frete_gratis": bool(l["frete_gratis"]),
            "origem": l["origem"], "comparar_com": l["comparar_com"],
            "permalink": l["permalink"],
        } for l in con.execute(sql, args)]

        from core import confrontos
        return {"conta": c.slug, "coletado_em": _quando(carimbo),
                "total": len(rivais), "concorrentes": rivais,
                "resumo_semanal": confrontos.resumo_semanal(con, c.slug) or None}
    finally:
        con.close()


# ------------------------------------------------------------- 4. fila

def _fila():
    """
    Carrega scripts/fila.py como módulo para reaproveitar a MESMA lista de
    comandos permitidos e a MESMA validação de argumentos.

    Duplicar a lista aqui seria a forma mais fácil de, um dia, liberar por
    engano no MCP algo que a fila recusa. Uma lista só, num arquivo só.
    """
    import importlib.util
    caminho = RAIZ / "scripts" / "fila.py"
    spec = importlib.util.spec_from_file_location("zion_fila", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


DIR_PEDIDOS = RAIZ / "pedidos"
DIR_FEITOS = DIR_PEDIDOS / "feitos"


def _proximo_numero() -> int:
    numeros = [0]
    for pasta, padrao in ((DIR_PEDIDOS, "*.pedido"), (DIR_FEITOS, "*.log")):
        if pasta.exists():
            for arq in pasta.glob(padrao):
                m = re.match(r"^(\d+)", arq.stem)
                if m:
                    numeros.append(int(m.group(1)))
    return max(numeros) + 1


@ferramenta(
    "encomendar",
    """Deixa um pedido na fila para o vigia executar (em até ~5 minutos).
    Serve para mandar coletar, mapear concorrência, sondar promoções, medir
    tarifas — o que o cli.py já faz.

    NÃO é terminal remoto: só aceita os comandos da lista de scripts/fila.py,
    com argumentos validados por formato. Um pedido fora do padrão é recusado
    aqui mesmo, antes de virar arquivo.""",
    {
        "comando": {"type": "string",
                    "description": "coletar | mapear | diagnostico | relatorio | notificar | "
                                   "alertas | contas | precos | tarifas | promocoes | vendas | "
                                   "checar | vigiar | posicoes | maquina | compactar | "
                                   "imagem-ambientada"},
        "alvo": {"type": "string", "description": "slug da conta, cliente_id ou 'todas'."},
        "opcoes": {"type": "object", "description": "Ex.: {\"--dias\": \"7\"}."},
        "flags": {"type": "array", "items": {"type": "string"},
                  "description": "Ex.: [\"--detalhado\"]."},
        "posicionais": {"type": "array", "items": {"type": "string"},
                        "description": "Para 'vigiar': [slug, link_ou_MLB]. "
                                       "Para 'imagem-ambientada': [slug, MLB] — "
                                       "gera foto de capa ambientada via API da "
                                       "OpenAI, custa por chamada, sempre com o "
                                       "prompt padrão (sem --prompt por aqui)."},
        "apelido": {"type": "string", "description": "Nome curto do arquivo, para achar depois."},
    },
    ["comando"],
)
def _encomendar(comando: str, alvo: str = "", opcoes: dict | None = None,
                flags: list | None = None, posicionais: list | None = None,
                apelido: str = "") -> dict:
    fila = _fila()
    pedido: dict[str, Any] = {"comando": comando}
    if alvo:
        pedido["alvo"] = alvo
    if opcoes:
        pedido["opcoes"] = opcoes
    if flags:
        pedido["flags"] = list(flags)
    if posicionais:
        pedido["posicionais"] = list(posicionais)

    validado = fila.montar_argumentos(pedido)
    if isinstance(validado, str):
        return {"aceito": False, "motivo": validado,
                "permitidos": sorted(fila.PERMITIDOS)}

    nome = re.sub(r"[^a-z0-9\-]+", "-", (apelido or f"{comando}-{alvo or 'todas'}").lower()).strip("-")
    arquivo = DIR_PEDIDOS / f"{_proximo_numero()}-{nome[:40]}.pedido"
    DIR_PEDIDOS.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(pedido, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "aceito": True,
        "pedido": arquivo.name,
        "resultado_em": f"pedidos/feitos/{arquivo.stem}.log",
        "comando_que_vai_rodar": "cli.py " + " ".join(validado),
        "quando": "o vigia executa na próxima passada (até ~5 minutos)",
        "como_ver": f"resultado_do_pedido com nome='{arquivo.stem}'",
    }


@ferramenta(
    "resultado_do_pedido",
    "Lê a saída de um pedido já executado pela fila.",
    {"nome": {"type": "string", "description": "Nome do pedido sem extensão. Ex.: 97-coletar-enio."}},
    ["nome"],
)
def _resultado_do_pedido(nome: str) -> dict:
    alvo = DIR_FEITOS / f"{Path(nome).stem}.log"
    if not alvo.exists():
        pendente = list(DIR_PEDIDOS.glob(f"{Path(nome).stem}.pedido"))
        return {"nome": nome, "pronto": False,
                "situacao": "ainda na fila" if pendente else "não encontrado"}
    texto = alvo.read_text(encoding="utf-8", errors="replace")
    return {"nome": alvo.stem, "pronto": True,
            "saida": texto[:20000], "truncado": len(texto) > 20000}


@ferramenta(
    "pedidos_recentes",
    "Os últimos pedidos executados pela fila, do mais novo para o mais velho.",
    {"limite": {"type": "integer", "description": "Padrão 15."}},
)
def _pedidos_recentes(limite: int = 15) -> dict:
    if not DIR_FEITOS.exists():
        return {"feitos": [], "na_fila": []}
    logs = sorted(DIR_FEITOS.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    feitos = [{
        "nome": p.stem,
        "quando": _quando(datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()),
        "primeira_linha": p.read_text(encoding="utf-8", errors="replace").splitlines()[:1],
    } for p in logs[:_limite(limite, 15)]]
    na_fila = [p.stem for p in sorted(DIR_PEDIDOS.glob("*.pedido"))]
    return {"feitos": feitos, "na_fila": na_fila}


# ----------------------------------------------------------- protocolo MCP

def _resposta(ident: Any, resultado: dict) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "result": resultado}


def _erro(ident: Any, codigo: int, mensagem: str) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": codigo, "message": mensagem}}


def _texto(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, indent=2, default=str)


def _chamar(nome: str, argumentos: dict) -> dict:
    """
    Executa a ferramenta. Falha vira resultado com isError, não erro de
    protocolo: assim o modelo LÊ o motivo e corrige, em vez de só receber
    'deu ruim' do transporte.
    """
    entrada = REGISTRO.get(nome)
    if not entrada:
        return {"content": [{"type": "text", "text": f"ferramenta '{nome}' não existe"}],
                "isError": True}
    try:
        saida = entrada["fn"](**(argumentos or {}))
        return {"content": [{"type": "text", "text": _texto(saida)}]}
    except TypeError as erro:
        return {"content": [{"type": "text", "text": f"argumentos inválidos: {erro}"}],
                "isError": True}
    except Exception as erro:
        _log(f"falha em {nome}: {erro}\n{traceback.format_exc()}")
        return {"content": [{"type": "text", "text": f"{type(erro).__name__}: {erro}"}],
                "isError": True}


def _tratar(msg: dict) -> dict | None:
    metodo = msg.get("method")
    ident = msg.get("id")
    params = msg.get("params") or {}

    if metodo == "initialize":
        pedida = params.get("protocolVersion")
        return _resposta(ident, {
            "protocolVersion": pedida if pedida in PROTOCOLOS else PROTOCOLO_PADRAO,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVIDOR,
            "instructions": (
                "Operação multi-conta de Mercado Livre da Zion. Toda ferramenta é "
                "endereçada por slug de conta — não existe conta padrão. Comece por "
                "listar_contas. Nada aqui altera anúncio: são leituras do banco de "
                "snapshots mais a fila de pedidos do próprio projeto."
            ),
        })

    if metodo in ("notifications/initialized", "notifications/cancelled"):
        return None

    if metodo == "ping":
        return _resposta(ident, {})

    if metodo == "tools/list":
        return _resposta(ident, {"tools": [t["schema"] for t in REGISTRO.values()]})

    if metodo == "tools/call":
        return _resposta(ident, _chamar(params.get("name", ""), params.get("arguments") or {}))

    # Não anunciamos recursos nem prompts, mas há cliente que pergunta assim
    # mesmo; lista vazia é mais educado que 'método não existe'.
    if metodo in ("resources/list", "resources/templates/list"):
        return _resposta(ident, {"resources": [], "resourceTemplates": []})
    if metodo == "prompts/list":
        return _resposta(ident, {"prompts": []})

    if ident is None:
        return None
    return _erro(ident, -32601, f"método não suportado: {metodo}")


def servir() -> int:
    """Laço principal: uma mensagem JSON por linha, entra e sai."""
    entrada = sys.stdin.buffer
    saida = sys.stdout.buffer
    _log(f"servidor MCP zion-ml de pé — {len(REGISTRO)} ferramentas — raiz {RAIZ}")

    while True:
        linha = entrada.readline()
        if not linha:
            _log("cliente encerrou a conexão")
            return 0
        texto = linha.decode("utf-8", errors="replace").strip()
        if not texto:
            continue
        try:
            msg = json.loads(texto)
        except json.JSONDecodeError as erro:
            _log(f"linha ilegível descartada: {erro}")
            continue

        for unidade in (msg if isinstance(msg, list) else [msg]):
            try:
                resposta = _tratar(unidade)
            except Exception as erro:
                _log(f"falha tratando {unidade.get('method')}: {traceback.format_exc()}")
                resposta = _erro(unidade.get("id"), -32603, str(erro))
            if resposta is not None:
                saida.write((json.dumps(resposta, ensure_ascii=False, default=str) + "\n").encode("utf-8"))
                saida.flush()


def autoteste() -> int:
    """Confere que o servidor carrega e que as leituras básicas respondem."""
    print(f"raiz: {RAIZ}")
    print(f"ferramentas registradas: {len(REGISTRO)}")
    for nome in sorted(REGISTRO):
        print(f"  - {nome}")
    print("\nlistar_contas:")
    contas = _listar_contas()
    for cl in contas["clientes"]:
        for ct in cl["contas"]:
            marca = "ok " if ct["credencial_configurada"] else "sem credencial"
            print(f"  {cl['nome']:<30} {ct['slug']:<28} {marca:<15} "
                  f"ativos={ct['anuncios_ativos']:<4} coleta={ct['ultima_coleta']}")
    primeira = next((ct["slug"] for cl in contas["clientes"] for ct in cl["contas"]
                     if ct["ultima_coleta"]), None)
    if primeira:
        print(f"\namostra em '{primeira}':")
        for nome, args in (("panorama_conta", {"conta": primeira}),
                           ("anuncios", {"conta": primeira, "limite": 3}),
                           ("mudancas", {"conta": primeira, "limite": 3}),
                           ("margens", {"conta": primeira, "limite": 3}),
                           ("alertas", {"alvo": primeira, "horas": 168, "limite": 3})):
            r = _chamar(nome, args)
            estado = "ERRO" if r.get("isError") else "ok"
            print(f"  {nome:<20} {estado}")
            if r.get("isError"):
                print("    " + r["content"][0]["text"][:300])
    print("\nse chegou até aqui, o servidor está apto. Ligue no app pelo docs/MCP.md")
    return 0


if __name__ == "__main__":
    if "--autoteste" in sys.argv:
        sys.exit(autoteste())
    try:
        sys.exit(servir())
    except KeyboardInterrupt:
        sys.exit(0)
