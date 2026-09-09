"""
Relatório diário: um HTML por cliente + um consolidado de todas as contas.

Filosofia do relatório: a primeira tela responde "preciso agir agora?".
Alertas críticos primeiro, depois o que mudou, e só então os números de apoio.
"""
from __future__ import annotations

import html
import sqlite3
from datetime import datetime

from . import db
from .config import Cliente, carregar_clientes
from .utils import DIR_RELATORIOS, agora_utc, brl, garantir_dir, para_br, pct, truncar

CSS = """
:root{--bg:#faf9f7;--card:#fff;--linha:#e6e2dc;--txt:#1c1b19;--fraco:#6d6862;
--critico:#b3261e;--critico-bg:#fdecea;--aviso:#8a5a00;--aviso-bg:#fff6e5;
--ok:#1e6f3f;--ok-bg:#e9f5ee;--destaque:#2c5aa0}
@media (prefers-color-scheme:dark){:root{--bg:#14140f;--card:#1e1e18;--linha:#33322b;
--txt:#f0eee9;--fraco:#a09a92;--critico:#ff8a80;--critico-bg:#3a1a17;--aviso:#ffc46b;
--aviso-bg:#3a2c11;--ok:#7ddba4;--ok-bg:#14301f;--destaque:#8ab4f8}}
*{box-sizing:border-box}
body{margin:0;padding:32px 20px;background:var(--bg);color:var(--txt);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:17px;margin:34px 0 12px;letter-spacing:-.01em}
h3{font-size:14px;margin:20px 0 8px;color:var(--fraco);text-transform:uppercase;letter-spacing:.06em}
.sub{color:var(--fraco);font-size:13px;margin-bottom:24px}
.card{background:var(--card);border:1px solid var(--linha);border-radius:10px;padding:16px 18px;margin-bottom:12px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:8px}
.kpi{background:var(--card);border:1px solid var(--linha);border-radius:10px;padding:14px 16px}
.kpi .n{font-size:24px;font-weight:600;letter-spacing:-.02em}
.kpi .r{font-size:12px;color:var(--fraco);margin-top:2px}
.alerta{border-left:3px solid var(--linha);padding:10px 14px;margin-bottom:8px;border-radius:0 8px 8px 0;background:var(--card)}
.alerta.crit{border-left-color:var(--critico);background:var(--critico-bg)}
.alerta.av{border-left-color:var(--aviso);background:var(--aviso-bg)}
.alerta .tag{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--fraco);display:block;margin-bottom:2px}
.tabela-wrap{overflow-x:auto;border:1px solid var(--linha);border-radius:10px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{text-align:left;padding:10px 12px;border-bottom:1px solid var(--linha);color:var(--fraco);
font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.05em;white-space:nowrap}
td{padding:9px 12px;border-bottom:1px solid var(--linha)}
tr:last-child td{border-bottom:none}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pos{color:var(--ok)}.neg{color:var(--critico)}
.vazio{color:var(--fraco);font-style:italic;padding:14px 0}
a{color:var(--destaque)}
.rodape{margin-top:40px;padding-top:16px;border-top:1px solid var(--linha);color:var(--fraco);font-size:12px}
"""


def _e(t) -> str:
    return html.escape(str(t if t is not None else ""))


def _kpi(n, rotulo) -> str:
    return f'<div class="kpi"><div class="n">{_e(n)}</div><div class="r">{_e(rotulo)}</div></div>'


def _bloco_alertas(alertas) -> str:
    if not alertas:
        return '<p class="vazio">Nada exigindo ação nas últimas 24h.</p>'
    partes = []
    for a in alertas:
        classe = "crit" if a["critico"] else "av"
        partes.append(
            f'<div class="alerta {classe}"><span class="tag">'
            f'{_e(a["regra"].replace("_", " "))} · {_e(a["conta_slug"])}</span>{_e(a["mensagem"])}</div>'
        )
    return "".join(partes)


def _tabela(cabecalhos, linhas) -> str:
    if not linhas:
        return '<p class="vazio">Sem dados no período.</p>'
    th = "".join(f"<th>{_e(c)}</th>" for c in cabecalhos)
    trs = []
    for l in linhas:
        # cada célula é uma string já formatada, ou ("num", valor) para alinhar à direita
        tds = "".join(
            (f'<td class="num">{x[1]}</td>' if isinstance(x, tuple) else f"<td>{x}</td>") for x in l
        )
        trs.append(f"<tr>{tds}</tr>")
    return f'<div class="tabela-wrap"><table><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'


# ----------------------------------------------------------------------
def _dados_da_conta(con: sqlite3.Connection, slug: str) -> dict:
    ultimo = db.ultima_coleta(con, "snap_anuncio", slug)
    anterior = db.ultima_coleta(con, "snap_anuncio", slug, antes_de=ultimo) if ultimo else None
    novos = db.snapshot_por_item(con, "snap_anuncio", slug, ultimo) if ultimo else {}
    velhos = db.snapshot_por_item(con, "snap_anuncio", slug, anterior) if anterior else {}

    conta_row = con.execute(
        "SELECT * FROM snap_conta WHERE conta_slug = ? ORDER BY coletado_em DESC LIMIT 1", (slug,)
    ).fetchone()

    ativos = sum(1 for n in novos.values() if n["status"] == "active")
    sem_estoque = sum(1 for n in novos.values() if n["status"] == "active" and (n["estoque"] or 0) == 0)

    mudancas = []
    for item_id, n in novos.items():
        v = velhos.get(item_id)
        if not v:
            continue
        dp = pct(n["preco"], v["preco"])
        dv = (n["vendidos"] or 0) - (v["vendidos"] or 0)
        de = (n["estoque"] or 0) - (v["estoque"] or 0)
        if (dp and abs(dp) >= 0.5) or dv or (de and abs(de) >= 1):
            mudancas.append({"n": n, "dp": dp, "dv": dv, "de": de})
    mudancas.sort(key=lambda m: (-(m["dv"] or 0), -abs(m["dp"] or 0)))

    posicoes = con.execute(
        "SELECT termo, item_id, posicao, preco, preco_topo FROM snap_posicao "
        "WHERE conta_slug = ? AND coletado_em = (SELECT MAX(coletado_em) FROM snap_posicao WHERE conta_slug = ?) "
        "ORDER BY posicao",
        (slug, slug),
    ).fetchall()

    return {
        "ultimo": ultimo,
        "itens": novos,
        "ativos": ativos,
        "sem_estoque": sem_estoque,
        "conta": conta_row,
        "mudancas": mudancas,
        "posicoes": posicoes,
    }


def gerar_html_cliente(con: sqlite3.Connection, cliente: Cliente) -> str:
    slugs = [c.slug for c in cliente.contas]
    alertas = [a for s in slugs for a in db.alertas_recentes(con, 24, s)]
    alertas.sort(key=lambda a: (-a["critico"], a["criado_em"]), reverse=False)
    criticos = [a for a in alertas if a["critico"]]

    total_ativos = total_sem_estoque = total_vendas = 0
    total_receita = 0.0
    secoes = []

    for conta in cliente.contas:
        d = _dados_da_conta(con, conta.slug)
        if not d["ultimo"]:
            continue
        total_ativos += d["ativos"]
        total_sem_estoque += d["sem_estoque"]
        if d["conta"]:
            total_vendas += d["conta"]["vendas_7d"] or 0
            total_receita += d["conta"]["receita_7d"] or 0.0

        linhas_mud = []
        for m in d["mudancas"][:15]:
            n = m["n"]
            dp = ""
            if m["dp"]:
                cls = "neg" if m["dp"] > 0 else "pos"
                dp = f'<span class="{cls}">{m["dp"]:+.1f}%</span>'
            linhas_mud.append([
                f'<a href="{_e(n["permalink"])}" target="_blank" rel="noopener">{_e(truncar(n["titulo"], 55))}</a>',
                ("num", brl(n["preco"])),
                ("num", dp or "—"),
                ("num", f'{m["dv"]:+d}' if m["dv"] else "—"),
                ("num", str(n["estoque"] or 0)),
                _e(n["status"]),
            ])

        linhas_pos = [
            [_e(p["termo"]),
             ("num", f'#{p["posicao"]}'),
             ("num", brl(p["preco"])),
             ("num", brl(p["preco_topo"])),
             ("num", f'{pct(p["preco"], p["preco_topo"]):+.0f}%' if p["preco_topo"] else "—")]
            for p in d["posicoes"][:20]
        ]

        rep = d["conta"]
        cab_rep = ""
        if rep:
            cab_rep = (
                f'<div class="card"><strong>{_e(rep["nickname"] or conta.nome_conta)}</strong> · '
                f'nível {_e(rep["nivel"] or "—")} · {_e(rep["transacoes"] or 0)} transações · '
                f'{d["ativos"]} ativos, {rep["anuncios_pausados"] or 0} pausados · '
                f'7 dias: {rep["vendas_7d"] or 0} vendas / {brl(rep["receita_7d"])}</div>'
            )

        secoes.append(f"""
<h2>{_e(conta.nome_conta)} <span style="color:var(--fraco);font-weight:400">· {_e(conta.papel)}</span></h2>
{cab_rep}
<h3>Movimentações desde a última coleta</h3>
{_tabela(["Anúncio", "Preço", "Δ preço", "Δ vendas", "Estoque", "Status"], linhas_mud)}
<h3>Posição nas palavras-chave monitoradas</h3>
{_tabela(["Termo", "Posição", "Seu preço", "Preço do 1º", "Diferença"], linhas_pos)}
""")

    agora = para_br(agora_utc().isoformat())
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(cliente.nome)} — Painel Mercado Livre</title><style>{CSS}</style></head><body><div class="wrap">
<h1>{_e(cliente.nome)}</h1>
<p class="sub">{_e(cliente.nicho)} · {len(cliente.contas)} conta(s) · relatório de {agora}</p>
<div class="kpis">
{_kpi(len(criticos), "alertas críticos (24h)")}
{_kpi(total_ativos, "anúncios ativos")}
{_kpi(total_sem_estoque, "ativos sem estoque")}
{_kpi(total_vendas, "vendas (7 dias)")}
{_kpi(brl(total_receita), "receita (7 dias)")}
</div>
<h2>Precisa de ação</h2>
{_bloco_alertas(alertas[:40])}
{"".join(secoes)}
<p class="rodape">Gerado por zion-ml · dados coletados via API oficial do Mercado Livre.</p>
</div></body></html>"""


def gerar(con: sqlite3.Connection, apenas_cliente: str | None = None) -> list[str]:
    garantir_dir(DIR_RELATORIOS)
    dia = datetime.now().strftime("%Y-%m-%d")
    caminhos = []

    for cliente in carregar_clientes():
        if apenas_cliente and cliente.id != apenas_cliente:
            continue
        destino = garantir_dir(DIR_RELATORIOS / cliente.id) / f"{dia}.html"
        destino.write_text(gerar_html_cliente(con, cliente), encoding="utf-8")
        # cópia estável para abrir sempre no mesmo lugar
        (DIR_RELATORIOS / cliente.id / "ultimo.html").write_text(
            destino.read_text(encoding="utf-8"), encoding="utf-8"
        )
        caminhos.append(str(destino))

    return caminhos


def resumo_texto(con: sqlite3.Connection, horas: int = 24) -> str:
    """Resumo curto em texto — serve para mensagem, e-mail ou notificação."""
    alertas = db.alertas_recentes(con, horas)
    if not alertas:
        return "Sem alertas nas últimas %dh. Todas as contas estáveis." % horas
    criticos = [a for a in alertas if a["critico"]]
    linhas = [f"{len(alertas)} alertas em {horas}h ({len(criticos)} críticos)", ""]
    for a in alertas[:15]:
        marca = "!" if a["critico"] else "·"
        linhas.append(f" {marca} [{a['conta_slug']}] {a['mensagem']}")
    if len(alertas) > 15:
        linhas.append(f"   … e mais {len(alertas) - 15}.")
    return "\n".join(linhas)
