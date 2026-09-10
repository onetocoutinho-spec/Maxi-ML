"""
Cobertura de modalidade: para cada produto, quais anúncios existem.

No ML um anúncio tem UMA modalidade — gold_special (clássico) ou gold_pro
(premium) — e pode ou não estar competindo numa ficha de catálogo. Vender o
mesmo produto em clássico, premium e catálogo exige anúncios SEPARADOS.

Este módulo responde "de tudo que a conta vende, o que já tem cada modalidade
e o que falta", olhando só o último snapshot do banco. Não fala com a API e
não escreve nada.

Um achado que aparece sozinho aqui e vale dinheiro: anúncio COM ficha de
catálogo vinculada (produto_catalogo preenchido) mas com catalogo=0 — tem
ficha e não está disputando a ficha. Isso não precisa de anúncio novo, é
opt-in no anúncio que já existe.
"""
from __future__ import annotations

import re
import sqlite3

from . import db
from .utils import truncar

# Modalidades como o ML as chama.
CLASSICO = "gold_special"
PREMIUM = "gold_pro"

ROTULO_MODALIDADE = {CLASSICO: "clássico", PREMIUM: "premium"}

# SKU curto ou de preenchimento ("-", "0", "sku") não identifica produto.
_SKU_LIXO = {"", "-", "--", "0", "00", "NA", "SKU", "SEM", "SEMSKU", "NONE"}


def _sku_chave(sku: str | None) -> str | None:
    limpo = re.sub(r"[^A-Za-z0-9]+", "", (sku or "")).upper()
    if len(limpo) < 4 or limpo in _SKU_LIXO:
        return None
    return limpo


def _titulo_chave(titulo: str) -> str:
    return " ".join((titulo or "sem título").lower().split()[:4])


class _Uniao:
    """Union-find: junta anúncios que compartilham QUALQUER sinal forte.

    Necessário porque o clássico e o premium do mesmo produto costumam ter
    SKU diferente (sufixo -P, -PREMIUM) e só se encontram pela ficha de
    catálogo — e vice-versa. Agrupar por um sinal só perde metade dos pares.
    """

    def __init__(self) -> None:
        self.pai: dict[str, str] = {}

    def achar(self, x: str) -> str:
        self.pai.setdefault(x, x)
        while self.pai[x] != x:
            self.pai[x] = self.pai[self.pai[x]]
            x = self.pai[x]
        return x

    def juntar(self, a: str, b: str) -> None:
        ra, rb = self.achar(a), self.achar(b)
        if ra != rb:
            self.pai[rb] = ra


def _agrupar(itens: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    """Agrupa anúncios que são o MESMO produto.

    Sinais fortes (fundem grupos): SKU normalizado e produto de catálogo.
    Título só entra quando o anúncio não tem nenhum dos dois — erra mais,
    então nunca funde grupos que já têm sinal forte.
    """
    u = _Uniao()
    for i in itens:
        no = f"item:{i['item_id']}"
        u.achar(no)
        sinais = []
        sku = _sku_chave(i["sku"])
        if sku:
            sinais.append(f"sku:{sku}")
        if i["produto_catalogo"]:
            sinais.append(f"cat:{i['produto_catalogo']}")
        if not sinais:
            sinais.append(f"tit:{_titulo_chave(i['titulo'])}")
        for s in sinais:
            u.juntar(s, no)

    grupos: dict[str, list[sqlite3.Row]] = {}
    for i in itens:
        grupos.setdefault(u.achar(f"item:{i['item_id']}"), []).append(i)
    return grupos


# Do melhor para o pior. Só 'ativo' conta como cobertura — anúncio pausado
# ou em revisão existe no painel e não vende, e a ação para cada um é
# diferente (despausar, resolver a revisão, criar do zero).
_ORDEM_STATUS = ["active", "under_review", "paused", "closed"]
_ROTULO_STATUS = {
    "active": "ativo",
    "under_review": "em revisão",
    "paused": "pausado",
    "closed": "encerrado",
}


def _estado(anuncios: list[sqlite3.Row]) -> str:
    """O melhor estado entre os anúncios da cela. Vazio = não existe nenhum."""
    if not anuncios:
        return ""
    situacoes = {a["status"] for a in anuncios}
    for s in _ORDEM_STATUS:
        if s in situacoes:
            return _ROTULO_STATUS[s]
    return "inativo"


def analisar(con: sqlite3.Connection, conta_slug: str) -> dict:
    carimbo = db.ultima_coleta(con, "snap_anuncio", conta_slug)
    if not carimbo:
        return {"erro": "sem coleta", "conta": conta_slug}

    itens = con.execute(
        "SELECT * FROM snap_anuncio WHERE conta_slug = ? AND coletado_em = ?",
        (conta_slug, carimbo),
    ).fetchall()
    if not itens:
        return {"erro": "sem coleta", "conta": conta_slug}

    produtos = []
    for chave, anuncios in _agrupar(itens).items():
        celas = {
            "classico_tradicional": [a for a in anuncios
                                     if a["tipo_anuncio"] == CLASSICO and not a["catalogo"]],
            "premium_tradicional": [a for a in anuncios
                                    if a["tipo_anuncio"] == PREMIUM and not a["catalogo"]],
            "classico_catalogo": [a for a in anuncios
                                  if a["tipo_anuncio"] == CLASSICO and a["catalogo"]],
            "premium_catalogo": [a for a in anuncios
                                 if a["tipo_anuncio"] == PREMIUM and a["catalogo"]],
        }
        estados = {nome: _estado(lista) for nome, lista in celas.items()}

        # Os três eixos que a operação cobra, cada um valendo em qualquer cela.
        eixos = {
            "classico": _estado([a for a in anuncios if a["tipo_anuncio"] == CLASSICO]),
            "premium": _estado([a for a in anuncios if a["tipo_anuncio"] == PREMIUM]),
            "catalogo": _estado([a for a in anuncios if a["catalogo"]]),
        }
        falta = [nome for nome, e in eixos.items() if e != "ativo"]

        # Tem ficha vinculada e NENHUM anúncio de catálogo: é opt-in no
        # anúncio que já existe. Se o anúncio de catálogo existe mas está
        # parado, a ação é outra — despausar —, então não entra aqui.
        fichas = {a["produto_catalogo"] for a in anuncios if a["produto_catalogo"]}
        opt_in = bool(fichas) and eixos["catalogo"] == ""

        principal = max(anuncios, key=lambda a: (a["status"] == "active",
                                                 a["vendidos"] or 0))
        produtos.append({
            "chave": chave,
            "titulo": truncar(principal["titulo"], 58),
            "sku": principal["sku"] or "",
            "anuncios": len(anuncios),
            "item_ids": [a["item_id"] for a in anuncios],
            "vendidos": sum(a["vendidos"] or 0 for a in anuncios),
            "celas": estados,
            "eixos": eixos,
            "falta": falta,
            "fichas": sorted(fichas),
            "opt_in_catalogo": opt_in,
        })

    produtos.sort(key=lambda p: (len(p["falta"]), p["vendidos"]), reverse=True)

    return {
        "conta": conta_slug,
        "carimbo": carimbo,
        "total_anuncios": len(itens),
        "produtos": produtos,
        "completos": len([p for p in produtos if not p["falta"]]),
        "sem_classico": [p for p in produtos if "classico" in p["falta"]],
        "sem_premium": [p for p in produtos if "premium" in p["falta"]],
        "sem_catalogo": [p for p in produtos if "catalogo" in p["falta"]],
        "opt_in_catalogo": [p for p in produtos if p["opt_in_catalogo"]],
        # Falta o eixo, mas o anúncio existe parado: despausar, não cadastrar.
        "so_despausar": [p for p in produtos
                         if any(p["eixos"][eixo] for eixo in p["falta"])],
    }


def _marca(estado: str) -> str:
    """'—' é o buraco de verdade (não existe). Qualquer outra coisa existe,
    e o rótulo diz o que fazer com ela."""
    if not estado:
        return "—"
    return "sim" if estado == "ativo" else estado.upper()


def texto(r: dict, detalhado: bool = False, limite: int = 25) -> str:
    if r.get("erro"):
        return (f"Cobertura {r['conta']}: {r['erro']}. "
                f"Rode `python cli.py coletar {r['conta']}` primeiro.")

    n = len(r["produtos"])
    linhas = [
        f"*Cobertura de modalidade — {r['conta']}*",
        f"{r['total_anuncios']} anúncios agrupados em {n} produtos "
        f"(coleta {r['carimbo'][:16].replace('T', ' ')})",
        "",
        f"Com clássico + premium + catálogo ativos: {r['completos']} de {n}",
        f"Sem clássico ativo: {len(r['sem_classico'])}",
        f"Sem premium ativo: {len(r['sem_premium'])}",
        f"Fora do catálogo: {len(r['sem_catalogo'])}",
    ]
    if r["opt_in_catalogo"] or r["so_despausar"]:
        linhas.append("")
        linhas.append("Nem todo buraco é anúncio novo:")
        if r["so_despausar"]:
            linhas.append(
                f"  {len(r['so_despausar'])} produto(s) já têm a modalidade que "
                "falta, só que pausada ou em revisão — despausar é mais barato "
                "que cadastrar.")
        if r["opt_in_catalogo"]:
            linhas.append(
                f"  {len(r['opt_in_catalogo'])} produto(s) já têm ficha de "
                "catálogo vinculada e nenhum anúncio disputando a ficha — "
                "é opt-in no anúncio que já existe.")

    if detalhado:
        linhas += ["", "Produto a produto (mais buracos primeiro):"]
        for p in r["produtos"][:limite]:
            e = p["eixos"]
            bloco = (f"  · {p['titulo']}"
                     f"\n      clássico {_marca(e['classico'])} | "
                     f"premium {_marca(e['premium'])} | catálogo {_marca(e['catalogo'])}"
                     f" | {p['anuncios']} anúncio(s), {p['vendidos']} vendas")
            if p["falta"]:
                bloco += f"\n      falta: {', '.join(p['falta'])}"
            parados = [eixo for eixo in p["falta"] if p["eixos"][eixo]]
            if parados:
                bloco += ("\n      já existe, só parado: "
                          + ", ".join(f"{eixo} ({p['eixos'][eixo]})" for eixo in parados))
            if p["opt_in_catalogo"]:
                bloco += "\n      tem ficha vinculada — falta entrar no catálogo (opt-in)"
            linhas.append(bloco)
        if n > limite:
            linhas.append(f"  … e mais {n - limite} produto(s).")

    return "\n".join(linhas)
