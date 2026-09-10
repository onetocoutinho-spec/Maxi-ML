"""
Painel comparativo das contas — um HTML só, lado a lado.

Diferente de core/report.py, que gera um relatório POR CLIENTE, este painel
existe para acompanhar contas de clientes diferentes na mesma tela: qual está
vendendo, qual está cara demais, qual está brigando com a irmã.

Só lê o banco. Não toca na API do ML, não escreve em snap_*.

    .venv\\Scripts\\python.exe scripts\\painel_metricas.py
    .venv\\Scripts\\python.exe scripts\\painel_metricas.py --contas enio-toldos-principal,facilita-decoralli

Sai em relatorios/painel-metricas.html.
"""
from __future__ import annotations

import argparse
import html
import sqlite3
import statistics
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core import db  # noqa: E402
from core.config import obter_conta  # noqa: E402

TZ = timezone(timedelta(hours=-3))
PADRAO = ["enio-toldos-principal", "facilita-brasil-principal", "facilita-decoralli"]

# Contas do mesmo dono. Quando duas aparecem na mesma ficha de catálogo isso é
# canibalização, não concorrência — e o painel precisa separar as duas coisas.
IRMAS = {
    "facilita-brasil-principal": "facilita-decoralli",
    "facilita-decoralli": "facilita-brasil-principal",
}


# ----------------------------------------------------------------------
# Coleta
# ----------------------------------------------------------------------
def _user_id(slug: str) -> str | None:
    try:
        uid = str(obter_conta(slug).user_id or "")
    except Exception:
        return None
    return uid if uid and uid != "SUBSTITUIR" else None


def metricas(con: sqlite3.Connection, slug: str) -> dict:
    con.row_factory = sqlite3.Row
    d: dict = {"slug": slug}

    try:
        d["nome"] = obter_conta(slug).nome_conta or slug
    except Exception:
        d["nome"] = slug

    # --- reputação e vendas (último snapshot de conta) ---
    conta = con.execute(
        "SELECT * FROM snap_conta WHERE conta_slug = ? ORDER BY coletado_em DESC LIMIT 1",
        (slug,),
    ).fetchone()
    d["conta"] = dict(conta) if conta else {}

    # --- profundidade do histórico: governa a confiança em tudo abaixo ---
    hist = con.execute(
        "SELECT COUNT(DISTINCT date(coletado_em)), MIN(date(coletado_em)), COUNT(*) "
        "FROM snap_anuncio WHERE conta_slug = ?",
        (slug,),
    ).fetchone()
    d["dias_historico"] = hist[0] or 0
    d["desde"] = hist[1]
    d["coletas"] = hist[2] or 0

    # --- composição dos anúncios (último snapshot) ---
    carimbo = db.ultima_coleta(con, "snap_anuncio", slug)
    d["carimbo"] = carimbo
    itens = list(
        con.execute(
            "SELECT * FROM snap_anuncio WHERE conta_slug = ? AND coletado_em = ?",
            (slug, carimbo),
        )
    ) if carimbo else []

    ativos = [i for i in itens if i["status"] == "active"]
    d["ativos"] = len(ativos)
    d["pausados"] = sum(1 for i in itens if i["status"] == "paused")
    d["revisao"] = sum(1 for i in itens if i["status"] == "under_review")
    d["fechados"] = sum(1 for i in itens if i["status"] == "closed")
    d["frete_gratis"] = sum(1 for i in ativos if i["frete_gratis"])
    d["catalogo"] = sum(1 for i in ativos if i["catalogo"])
    d["premium"] = sum(1 for i in ativos if i["tipo_anuncio"] == "gold_pro")
    d["classico"] = sum(1 for i in ativos if i["tipo_anuncio"] == "gold_special")
    d["sem_venda"] = sum(1 for i in ativos if not (i["vendidos"] or 0))
    d["vendidos_total"] = sum((i["vendidos"] or 0) for i in ativos)

    d["campeoes"] = [
        {"titulo": i["titulo"], "preco": i["preco"], "vendidos": i["vendidos"] or 0,
         "tipo": i["tipo_anuncio"], "link": i["permalink"]}
        for i in sorted(ativos, key=lambda x: -(x["vendidos"] or 0))[:5]
        if (i["vendidos"] or 0) > 0
    ]

    # Concentração: quanto do histórico de vendas mora nos 3 maiores anúncios.
    vend = sorted(((i["vendidos"] or 0) for i in ativos), reverse=True)
    d["concentracao"] = (sum(vend[:3]) / sum(vend) * 100) if sum(vend) else None

    # --- preço contra a concorrência da mesma ficha de catálogo ---
    # snap_concorrente guarda só os OUTROS vendedores; o nosso preço vem de
    # snap_anuncio pelo item apontado em comparar_com.
    gaps, ganhando, irma_barata, fichas_irma = [], 0, 0, 0
    irma_id = _user_id(IRMAS[slug]) if slug in IRMAS else None

    ofertas = con.execute(
        """WITH u AS (SELECT referencia, MAX(coletado_em) m FROM snap_concorrente
                      WHERE conta_slug = ? GROUP BY 1)
           SELECT s.referencia, s.comparar_com, s.seller_id, s.seller_nickname, s.preco
           FROM snap_concorrente s JOIN u ON u.referencia = s.referencia AND u.m = s.coletado_em
           WHERE s.conta_slug = ? AND s.preco > 0""",
        (slug, slug),
    ).fetchall()

    meus = {i["item_id"]: i for i in itens}
    por_ficha: dict[str, dict] = {}
    for o in ofertas:
        f = por_ficha.setdefault(o["referencia"], {"meu": o["comparar_com"], "melhor": None, "irma": None})
        if f["melhor"] is None or o["preco"] < f["melhor"]:
            f["melhor"] = o["preco"]
            f["quem"] = o["seller_nickname"]
        if irma_id and str(o["seller_id"]) == irma_id:
            f["irma"] = o["preco"] if f["irma"] is None else min(f["irma"], o["preco"])

    for f in por_ficha.values():
        meu = meus.get(f["meu"])
        if not meu or not meu["preco"] or not f["melhor"]:
            continue
        gaps.append((meu["preco"] - f["melhor"]) / f["melhor"] * 100)
        if meu["preco"] <= f["melhor"]:
            ganhando += 1
        if f["irma"] is not None:
            fichas_irma += 1
            if f["irma"] < meu["preco"]:
                irma_barata += 1

    d["fichas"] = len(por_ficha)
    d["fichas_comparaveis"] = len(gaps)
    d["gap_mediano"] = statistics.median(gaps) if gaps else None
    d["ganhando"] = ganhando
    d["fichas_irma"] = fichas_irma
    d["irma_barata"] = irma_barata
    d["irma"] = IRMAS.get(slug)

    # --- promoções: 'candidate' é campanha aberta que ninguém entrou ---
    d["promos"] = {"abertas": 0, "dentro": 0}
    carimbo_p = db.ultima_coleta(con, "snap_promocao", slug)
    if carimbo_p:
        for r in con.execute(
            "SELECT status, COUNT(*) n FROM snap_promocao "
            "WHERE conta_slug = ? AND coletado_em = ? GROUP BY 1",
            (slug, carimbo_p),
        ):
            if r["status"] == "candidate":
                d["promos"]["abertas"] += r["n"]
            elif r["status"] == "started":
                d["promos"]["dentro"] += r["n"]

    # --- alertas das últimas 24h ---
    d["alertas"] = [
        {"regra": r["regra"], "n": r["n"], "critico": bool(r["c"])}
        for r in con.execute(
            "SELECT regra, COUNT(*) n, MAX(critico) c FROM alerta "
            "WHERE conta_slug = ? AND criado_em > datetime('now', '-1 day') "
            "GROUP BY 1 ORDER BY n DESC",
            (slug,),
        )
    ]
    return d


# ----------------------------------------------------------------------
# Render
# ----------------------------------------------------------------------
def _e(t) -> str:
    return html.escape(str(t if t is not None else ""))


def _rs(v) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}".replace(",", ".")


def _data_curta(iso: str | None) -> str:
    """'2026-08-26' -> '26/08'. O ano não cabe e não muda nada na leitura."""
    if not iso:
        return "—"
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m")
    except ValueError:
        return iso


def _pct(v, casas=1) -> str:
    return "—" if v is None else f"{v:.{casas}f}%".replace(".", ",")


NIVEIS = {
    "5_green": "Verde", "4_light_green": "Verde claro", "3_yellow": "Amarelo",
    "2_orange": "Laranja", "1_red": "Vermelho",
}

REGRAS = {
    "perdeu_buy_box": "Perdeu a compra",
    "buy_box_no_fio": "Compra no fio",
    "concorrente_cruzou_preco": "Concorrente cruzou o preço",
    "concorrente_novo_no_topo": "Concorrente novo no topo",
    "concorrente_mexeu": "Concorrente mexeu",
    "promocao_liberada": "Campanha liberada",
    "meu_anuncio_mudou": "Anúncio mudou",
    "meu_preco_caiu_ou_subiu": "Preço mexeu",
    "anuncio_pausado": "Anúncio pausou",
    "estoque_baixo": "Estoque baixo",
    "venda_nova": "Venda nova",
}


def _barra_status(m: dict) -> str:
    total = m["ativos"] + m["pausados"] + m["revisao"] + m["fechados"]
    if not total:
        return ""
    partes = [
        ("ativo", m["ativos"], "Ativos"),
        ("pausado", m["pausados"], "Pausados"),
        ("revisao", m["revisao"], "Em revisão"),
        ("fechado", m["fechados"], "Encerrados"),
    ]
    segs = "".join(
        f'<span class="seg seg--{k}" style="width:{n / total * 100:.2f}%" '
        f'title="{_e(rot)}: {n}"></span>'
        for k, n, rot in partes if n
    )
    legenda = " ".join(
        f'<span class="leg"><i class="dot dot--{k}"></i>{_e(rot)} <b>{n}</b></span>'
        for k, n, rot in partes if n
    )
    return f'<div class="barra">{segs}</div><div class="legenda">{legenda}</div>'


def _cartao(m: dict, maior_receita: float) -> str:
    c = m["conta"]
    receita = c.get("receita_7d") or 0
    cancelada = c.get("receita_cancelada_7d") or 0
    unidades = c.get("vendas_7d") or 0
    bruto = receita + cancelada
    ticket = receita / unidades if unidades else None
    taxa_cancel = (cancelada / bruto * 100) if bruto else None

    largura = (receita / maior_receita * 100) if maior_receita else 0
    largura_cancel = (cancelada / maior_receita * 100) if maior_receita else 0

    sev = "critico" if (taxa_cancel or 0) >= 15 else "atencao" if (taxa_cancel or 0) >= 8 else "bom"
    hist = m["dias_historico"]
    hist_sev = "bom" if hist >= 7 else "atencao" if hist >= 3 else "critico"

    return f"""
<article class="cartao">
  <header class="cartao__topo">
    <div>
      <h2>{_e(m['nome'])}</h2>
      <p class="apelido">{_e(c.get('nickname') or '—')} · {_e(m['slug'])}</p>
    </div>
    <span class="nivel nivel--{_e((c.get('nivel') or '').split('_')[0])}">
      {_e(NIVEIS.get(c.get('nivel'), c.get('nivel') or '—'))}
    </span>
  </header>

  <div class="receita">
    <span class="rotulo">Receita entrada · {_e(c.get('janela_vendas') or '7 dias')}</span>
    <strong class="numerao">R$ {_rs(receita)}</strong>
    <div class="trilho">
      <span class="trilho__ok" style="width:{largura:.1f}%"></span>
      <span class="trilho__perdido" style="width:{largura_cancel:.1f}%"
            title="Cancelado: R$ {_rs(cancelada)}"></span>
    </div>
    <p class="sub">
      {unidades} un. vendidas · ticket R$ {_rs(ticket)}
      · <span class="chip chip--{sev}">{_pct(taxa_cancel)} cancelado</span>
    </p>
  </div>

  <dl class="grade">
    <div><dt>Hoje</dt><dd>R$ {_rs(c.get('receita_hoje'))}<small>{c.get('vendas_hoje') or 0} un.</small></dd></div>
    <div><dt>Reclamações</dt><dd>{_pct((c.get('reclamacoes_pct') or 0) * 100, 2)}</dd></div>
    <div><dt>Atrasos</dt><dd>{_pct((c.get('atrasos_pct') or 0) * 100, 1)}</dd></div>
    <div><dt>Transações</dt><dd>{_rs(c.get('transacoes'))}</dd></div>
  </dl>

  {_barra_status(m)}

  <p class="rodape">
    <span class="chip chip--{hist_sev}">{hist} {'dia' if hist == 1 else 'dias'} de histórico</span>
    <span class="mono">{_rs(m['coletas'])} coletas desde {_e(_data_curta(m['desde']))}</span>
  </p>
</article>"""


def _linha_preco(m: dict) -> str:
    gap = m["gap_mediano"]
    sev = "critico" if (gap or 0) >= 40 else "atencao" if (gap or 0) >= 15 else "bom"
    largura = min((gap or 0) / 80 * 100, 100)
    return f"""
<tr>
  <th scope="row">{_e(m['nome'])}</th>
  <td class="num">{m['fichas_comparaveis']}</td>
  <td class="num">{m['ganhando']}</td>
  <td>
    <div class="gap">
      <span class="gap__barra gap__barra--{sev}" style="width:{largura:.1f}%"></span>
      <span class="gap__valor mono">+{_pct(gap, 0)}</span>
    </div>
  </td>
</tr>"""


def _linha_irma(m: dict) -> str:
    if not m["fichas_irma"]:
        return ""
    try:
        nome_irma = obter_conta(m["irma"]).nome_conta
    except Exception:
        nome_irma = m["irma"]
    pct = m["irma_barata"] / m["fichas_irma"] * 100
    return f"""
<tr>
  <th scope="row">{_e(m['nome'])}</th>
  <td>{_e(nome_irma)}</td>
  <td class="num">{m['fichas_irma']} <small>de {m['fichas']}</small></td>
  <td>
    <div class="gap">
      <span class="gap__barra gap__barra--critico" style="width:{pct:.1f}%"></span>
      <span class="gap__valor mono">{m['irma_barata']} fichas</span>
    </div>
  </td>
</tr>"""


def _painel_alertas(ms: list[dict]) -> str:
    regras = sorted({a["regra"] for m in ms for a in m["alertas"]},
                    key=lambda r: -sum(a["n"] for m in ms for a in m["alertas"] if a["regra"] == r))
    cab = "".join(f"<th>{_e(m['nome'].split()[0])}</th>" for m in ms)
    linhas = []
    for r in regras:
        celulas = ""
        for m in ms:
            a = next((x for x in m["alertas"] if x["regra"] == r), None)
            if not a:
                celulas += '<td class="num vazio">·</td>'
            else:
                cls = "critico" if a["critico"] else "neutro"
                celulas += f'<td class="num"><span class="pastilha pastilha--{cls}">{a["n"]}</span></td>'
        linhas.append(f'<tr><th scope="row">{_e(REGRAS.get(r, r))}</th>{celulas}</tr>')
    return f"""
<table class="tabela tabela--alertas">
  <thead><tr><th scope="col">Aviso nas últimas 24 h</th>{cab}</tr></thead>
  <tbody>{''.join(linhas)}</tbody>
</table>"""


def _campeoes(m: dict) -> str:
    if not m["campeoes"]:
        return f'<p class="nada">Nenhum anúncio ativo com venda registrada.</p>'
    linhas = "".join(
        f'<li><span class="mono qtd">{c["vendidos"]}</span>'
        f'<span class="tit">{_e(c["titulo"])}</span>'
        f'<span class="mono preco">R$ {_rs(c["preco"])}</span></li>'
        for c in m["campeoes"]
    )
    return f'<ol class="campeoes">{linhas}</ol>'


def montar(ms: list[dict]) -> str:
    agora = datetime.now(TZ)
    maior = max((m["conta"].get("receita_7d") or 0) for m in ms) or 1
    cartoes = "".join(_cartao(m, maior) for m in ms)
    precos = "".join(_linha_preco(m) for m in ms if m["fichas_comparaveis"])
    irmas = "".join(_linha_irma(m) for m in ms)
    receita_total = sum((m["conta"].get("receita_7d") or 0) for m in ms)
    unidades_total = sum((m["conta"].get("vendas_7d") or 0) for m in ms)
    promos_abertas = sum(m["promos"]["abertas"] for m in ms)

    blocos_campeoes = "".join(
        f'<div class="coluna"><h3>{_e(m["nome"])}</h3>'
        f'<p class="micro">{m["sem_venda"]} dos {m["ativos"]} ativos ainda sem venda</p>'
        f'{_campeoes(m)}</div>'
        for m in ms
    )

    bloco_irmas = f"""
    <section class="secao">
      <h2>Uma conta contra a outra</h2>
      <p class="intro">Contas do mesmo dono que aparecem juntas na mesma ficha de
      catálogo. Aqui preço baixo não ganha do concorrente — ganha da própria casa.</p>
      <div class="rolagem">
      <table class="tabela">
        <thead><tr><th scope="col">Conta</th><th scope="col">Encontra</th>
        <th scope="col">Fichas dividas</th><th scope="col">Onde a irmã está mais barata</th></tr></thead>
        <tbody>{irmas}</tbody>
      </table>
      </div>
    </section>""" if irmas else ""

    return f"""<title>Vitrine das Contas</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root {{
  --papel:#f1f4f3; --superficie:#ffffff; --tinta:#121a19; --tinta-fraca:#5c6d69;
  --linha:#dde4e2; --acento:#0f6b64; --acento-fraco:#e3efed;
  --bom:#2c7a51; --atencao:#a2600f; --critico:#a83a2c;
  --bom-fundo:#e6f2ea; --atencao-fundo:#f8eddb; --critico-fundo:#f7e5e2;
  --sombra:0 1px 2px rgba(18,26,25,.05), 0 8px 24px -12px rgba(18,26,25,.14);
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --papel:#0c1211; --superficie:#141d1c; --tinta:#e2eae7; --tinta-fraca:#8ba09b;
    --linha:#243230; --acento:#4fb3a8; --acento-fraco:#17302d;
    --bom:#5cb583; --atencao:#d1943f; --critico:#dd7566;
    --bom-fundo:#162b21; --atencao-fundo:#2e2415; --critico-fundo:#301c19;
    --sombra:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
  }}
}}
:root[data-theme="dark"] {{
  --papel:#0c1211; --superficie:#141d1c; --tinta:#e2eae7; --tinta-fraca:#8ba09b;
  --linha:#243230; --acento:#4fb3a8; --acento-fraco:#17302d;
  --bom:#5cb583; --atencao:#d1943f; --critico:#dd7566;
  --bom-fundo:#162b21; --atencao-fundo:#2e2415; --critico-fundo:#301c19;
  --sombra:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
}}

* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--papel); color:var(--tinta);
  font:400 15px/1.55 "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
  -webkit-font-smoothing:antialiased;
}}
.mono {{ font-family:"IBM Plex Mono", ui-monospace, monospace; font-variant-numeric:tabular-nums; }}
.num {{ text-align:right; font-family:"IBM Plex Mono", ui-monospace, monospace; font-variant-numeric:tabular-nums; }}
h1,h2,h3 {{ font-family:"Bricolage Grotesque", "IBM Plex Sans", sans-serif; text-wrap:balance; margin:0; }}

.folha {{ max-width:1180px; margin:0 auto; padding:40px 24px 72px; }}

/* ---- cabeçalho ---- */
.cabeca {{ border-bottom:2px solid var(--tinta); padding-bottom:20px; margin-bottom:32px; }}
.eyebrow {{
  font-family:"IBM Plex Mono", monospace; font-size:11px; letter-spacing:.14em;
  text-transform:uppercase; color:var(--acento); margin:0 0 10px;
}}
.cabeca h1 {{ font-size:clamp(30px,5vw,46px); font-weight:700; letter-spacing:-.02em; line-height:1.05; }}
.cabeca .resumo {{ margin:14px 0 0; max-width:62ch; color:var(--tinta-fraca); }}
.carimbo {{
  display:flex; flex-wrap:wrap; gap:8px 20px; margin-top:16px;
  font-family:"IBM Plex Mono", monospace; font-size:12px; color:var(--tinta-fraca);
}}
.carimbo b {{ color:var(--tinta); font-weight:500; }}

/* ---- cartões ---- */
.cartoes {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(310px,1fr)); gap:18px; margin-bottom:44px; }}
.cartao {{
  background:var(--superficie); border:1px solid var(--linha); border-radius:4px;
  padding:20px; box-shadow:var(--sombra); display:flex; flex-direction:column; gap:18px;
}}
.cartao__topo {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }}
.cartao h2 {{ font-size:19px; font-weight:700; letter-spacing:-.01em; }}
.apelido {{ margin:3px 0 0; font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--tinta-fraca); }}
.nivel {{
  flex-shrink:0; font-size:11px; font-weight:500; padding:3px 9px; border-radius:2px;
  background:var(--bom-fundo); color:var(--bom); white-space:nowrap;
}}
.nivel--3, .nivel--2 {{ background:var(--atencao-fundo); color:var(--atencao); }}
.nivel--1 {{ background:var(--critico-fundo); color:var(--critico); }}

.rotulo {{
  display:block; font-family:"IBM Plex Mono",monospace; font-size:10px;
  letter-spacing:.1em; text-transform:uppercase; color:var(--tinta-fraca); margin-bottom:4px;
}}
.numerao {{
  display:block; font-family:"Bricolage Grotesque",sans-serif; font-size:34px;
  font-weight:700; letter-spacing:-.03em; line-height:1; font-variant-numeric:tabular-nums;
}}
.trilho {{ display:flex; height:6px; background:var(--linha); border-radius:3px; overflow:hidden; margin:12px 0 8px; }}
.trilho__ok {{ background:var(--acento); }}
.trilho__perdido {{ background:var(--critico); opacity:.5; }}
.sub {{ margin:0; font-size:13px; color:var(--tinta-fraca); }}

.chip {{ display:inline-block; font-size:11.5px; font-weight:500; padding:1px 7px; border-radius:2px; white-space:nowrap; }}
.chip--bom {{ background:var(--bom-fundo); color:var(--bom); }}
.chip--atencao {{ background:var(--atencao-fundo); color:var(--atencao); }}
.chip--critico {{ background:var(--critico-fundo); color:var(--critico); }}

.grade {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:0; padding:14px 0; border-block:1px solid var(--linha); }}
.grade div {{ min-width:0; }}
.grade dt {{ font-family:"IBM Plex Mono",monospace; font-size:10px; letter-spacing:.06em; text-transform:uppercase; color:var(--tinta-fraca); }}
.grade dd {{ margin:2px 0 0; font-family:"IBM Plex Mono",monospace; font-size:14px; font-weight:500; font-variant-numeric:tabular-nums; }}
.grade dd small {{ display:block; font-size:10.5px; font-weight:400; color:var(--tinta-fraca); }}

.barra {{ display:flex; height:8px; border-radius:2px; overflow:hidden; background:var(--linha); }}
.seg--ativo {{ background:var(--acento); }}
.seg--pausado {{ background:var(--tinta-fraca); opacity:.55; }}
.seg--revisao {{ background:var(--atencao); }}
.seg--fechado {{ background:var(--critico); opacity:.6; }}
.legenda {{ display:flex; flex-wrap:wrap; gap:4px 14px; margin-top:8px; font-size:11.5px; color:var(--tinta-fraca); }}
.leg b {{ color:var(--tinta); font-weight:500; }}
.dot {{ display:inline-block; width:7px; height:7px; border-radius:1px; margin-right:5px; }}
.dot--ativo {{ background:var(--acento); }}
.dot--pausado {{ background:var(--tinta-fraca); opacity:.55; }}
.dot--revisao {{ background:var(--atencao); }}
.dot--fechado {{ background:var(--critico); opacity:.6; }}

.rodape {{ margin:0; display:flex; flex-wrap:wrap; align-items:center; gap:10px; font-size:11px; color:var(--tinta-fraca); }}

/* ---- seções ---- */
.secao {{ margin-bottom:44px; }}
.secao h2 {{ font-size:22px; font-weight:700; letter-spacing:-.015em; }}
.intro {{ margin:8px 0 18px; max-width:66ch; color:var(--tinta-fraca); font-size:14px; }}
.rolagem {{ overflow-x:auto; }}

.tabela {{ width:100%; border-collapse:collapse; font-size:14px; }}
.tabela th, .tabela td {{ padding:11px 14px; text-align:left; border-bottom:1px solid var(--linha); }}
.tabela thead th {{
  font-family:"IBM Plex Mono",monospace; font-size:10px; letter-spacing:.08em;
  text-transform:uppercase; color:var(--tinta-fraca); font-weight:400;
  border-bottom:1px solid var(--tinta);
}}
.tabela tbody th {{ font-weight:600; }}
.tabela td small {{ color:var(--tinta-fraca); }}
.tabela tbody tr:last-child th, .tabela tbody tr:last-child td {{ border-bottom:none; }}

.gap {{ display:flex; align-items:center; gap:10px; min-width:200px; }}
.gap__barra {{ height:14px; border-radius:2px; min-width:2px; }}
.gap__barra--bom {{ background:var(--bom); }}
.gap__barra--atencao {{ background:var(--atencao); }}
.gap__barra--critico {{ background:var(--critico); }}
.gap__valor {{ font-size:12.5px; color:var(--tinta-fraca); white-space:nowrap; }}

.pastilha {{ display:inline-block; min-width:30px; padding:2px 7px; border-radius:2px; font-size:12.5px; font-weight:500; }}
.pastilha--critico {{ background:var(--critico-fundo); color:var(--critico); }}
.pastilha--neutro {{ background:var(--acento-fraco); color:var(--acento); }}
.vazio {{ color:var(--linha); }}
.tabela--alertas td {{ text-align:right; }}

/* ---- campeões ---- */
.colunas {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:26px; }}
.coluna h3 {{ font-size:15px; font-weight:700; }}
.micro {{ margin:3px 0 12px; font-size:12px; color:var(--tinta-fraca); font-family:"IBM Plex Mono",monospace; }}
.campeoes {{ list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:1px; }}
.campeoes li {{ display:grid; grid-template-columns:auto 1fr auto; gap:12px; align-items:baseline; padding:8px 0; border-bottom:1px solid var(--linha); }}
.qtd {{ font-size:15px; font-weight:500; color:var(--acento); min-width:2.4em; }}
.tit {{ font-size:13px; line-height:1.35; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }}
.preco {{ font-size:12.5px; color:var(--tinta-fraca); }}
.nada {{ font-size:13px; color:var(--tinta-fraca); font-style:italic; }}

/* ---- ressalvas ---- */
.ressalvas {{
  background:var(--superficie); border:1px solid var(--linha);
  border-left:3px solid var(--atencao); border-radius:3px; padding:22px 24px;
}}
.ressalvas h2 {{ font-size:17px; font-weight:700; margin-bottom:4px; }}
.ressalvas ul {{ margin:14px 0 0; padding-left:18px; display:flex; flex-direction:column; gap:10px; }}
.ressalvas li {{ font-size:13.5px; line-height:1.5; max-width:74ch; }}
.ressalvas b {{ font-weight:600; }}

.creditos {{ margin-top:40px; padding-top:16px; border-top:1px solid var(--linha);
  font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--tinta-fraca); }}

@media (max-width:640px) {{
  .folha {{ padding:28px 16px 56px; }}
  .grade {{ grid-template-columns:repeat(2,1fr); }}
}}
</style>

<div class="folha">
  <header class="cabeca">
    <p class="eyebrow">Zion · operação de marketplace</p>
    <h1>Vitrine das Contas</h1>
    <p class="resumo">
      As três contas lado a lado, do jeito que o Mercado Livre as devolveu na
      última coleta. Receita é a que entrou — cancelamento anda ao lado, nunca somado.
    </p>
    <div class="carimbo">
      <span>Coleta <b>{agora:%d/%m/%Y às %H:%M}</b></span>
      <span>Receita somada <b>R$ {_rs(receita_total)}</b></span>
      <span>Unidades <b>{unidades_total}</b></span>
      <span>Campanhas abertas <b>{promos_abertas}</b></span>
    </div>
  </header>

  <div class="cartoes">{cartoes}</div>

  <section class="secao">
    <h2>Preço contra quem divide a ficha</h2>
    <p class="intro">
      Para cada ficha de catálogo vigiada, o nosso preço comparado ao mais barato
      que aparece nela. O ML não deixa buscar por palavra-chave, então isto cobre
      só quem está na mesma ficha — quem vende fora dela não entra nesta conta.
    </p>
    <div class="rolagem">
    <table class="tabela">
      <thead><tr>
        <th scope="col">Conta</th><th scope="col">Fichas</th>
        <th scope="col">Mais barato</th><th scope="col">Quanto acima, na mediana</th>
      </tr></thead>
      <tbody>{precos}</tbody>
    </table>
    </div>
  </section>

  {bloco_irmas}

  <section class="secao">
    <h2>Avisos que o motor levantou</h2>
    <p class="intro">Contagem das últimas 24 horas. Vermelho é o que a régua marca como crítico.</p>
    <div class="rolagem">{_painel_alertas(ms)}</div>
  </section>

  <section class="secao">
    <h2>O que puxa a venda</h2>
    <p class="intro">
      Unidades acumuladas na vida do anúncio, não no período — anúncio recém-publicado
      começa em zero por definição.
    </p>
    <div class="colunas">{blocos_campeoes}</div>
  </section>

  <section class="ressalvas">
    <h2>Leituras que este painel não permite</h2>
    <ul>
      <li><b>Estoque não é dado de negócio aqui.</b> FACILITA e Decoralli declaram
      estoque inflado de propósito. Qualquer conta de "valor parado" sai errada — por isso
      estoque não aparece nesta tela.</li>
      <li><b>Não há venda por anúncio no período.</b> O ML entrega vendas por pedido
      e "vendidos" acumulado do anúncio. Ranking de campeões é histórico de vida, não do mês.</li>
      <li><b>Concorrente fora do catálogo não é acompanhado.</b> A busca por palavra-chave
      e a leitura de anúncio de terceiro estão fechadas na API. Dá para descobrir esse
      concorrente na mão; não dá para vigiar.</li>
      <li><b>Margem não está nesta tela.</b> O frete de móvel volumoso não está no banco,
      então toda margem calculada hoje seria teto, não resultado.</li>
    </ul>
  </section>

  <p class="creditos">
    Gerado por scripts/painel_metricas.py a partir de data/zion_ml.db ·
    somente leitura, nenhuma chamada à API do Mercado Livre.
  </p>
</div>"""


# ----------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(description="Painel comparativo das contas.")
    p.add_argument("--contas", help="slugs separados por vírgula", default=",".join(PADRAO))
    p.add_argument("--saida", default=str(RAIZ / "relatorios" / "painel-metricas.html"))
    args = p.parse_args()

    slugs = [s.strip() for s in args.contas.split(",") if s.strip()]
    con = db.conectar()
    ms = [metricas(con, s) for s in slugs]

    vazias = [m["slug"] for m in ms if not m["conta"]]
    if vazias:
        print(f"  aviso: sem snapshot de conta para {', '.join(vazias)} — rode uma coleta antes.")
    ms = [m for m in ms if m["conta"]]
    if not ms:
        print("  nada a mostrar.")
        return 1

    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(montar(ms), encoding="utf-8")
    print(f"  painel: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
