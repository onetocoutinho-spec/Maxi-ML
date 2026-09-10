"""
Relatório de campanha de cupom — a página que vai para o gestor da conta.

Por que uma página e não só o terminal: quem decide sobre a campanha
raramente é quem roda o comando. A página abre no celular, sobrevive ao
print de tela e carrega junto as ressalvas — que é o que impede o número de
virar uma conclusão maior do que ele sustenta.

A ordem das seções é a ordem das perguntas de quem lê:
  1. quanto vendeu e quanto custou
  2. em quais produtos, e quanto deles depende do cupom
  3. trouxe gente nova?
  4. e onde isso se encaixa no desconto total da conta
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from . import cupons
from .report import CSS, _e, _kpi, _tabela
from .utils import DIR_RELATORIOS, agora_utc, brl, garantir_dir, para_br, truncar


def _pct(v) -> str:
    return f"{v:.1f}%" if v is not None else "—"


def _dia(iso) -> str:
    try:
        return para_br(iso)[:10]
    except Exception:
        return str(iso or "")[:10]


def montar(con: sqlite3.Connection, conta, dias: int = 60) -> tuple[str, dict]:
    """Devolve (html, dados) — os dados servem também para o resumo em texto."""
    resumo = cupons.resumo_da_campanha(con, conta.slug, dias=dias)
    campanha = resumo["campanhas"][0] if resumo["campanhas"] else None
    desde = campanha["inicio"] if campanha and campanha.get("inicio") else None

    janela = campanha.get("desde_o_inicio") if campanha else None
    if not janela or not janela.get("pedidos"):
        janela = {"pedidos": resumo["pedidos"], "faturamento": resumo["faturamento"],
                  "custo": resumo["custo"], "ticket": resumo["ticket"],
                  "custo_pct": resumo["custo_sobre_faturamento"], "desde": None}

    dependencia = cupons.dependencia_por_produto(con, conta.slug, dias=dias, desde=desde)
    quem = cupons.compradores(con, conta.slug, desde) if desde else None
    contraste = cupons.contraste_com_desconto(con, conta.slug, dias=dias)
    periodo = resumo["periodo"]

    # Relatório zerado quase nunca quer dizer "não houve venda com cupom":
    # quer dizer que a coleta de pedidos não está no banco. Distinguir as duas
    # coisas é o que impede um "R$ 0,00" de sair no canal do cliente como se
    # fosse resultado.
    tem_pedidos = con.execute(
        "SELECT COUNT(*) n FROM venda WHERE conta_slug = ?",
        (conta.slug,)).fetchone()["n"]
    vazio = None
    if not janela["pedidos"]:
        vazio = ("sem coleta de pedidos para esta conta" if not tem_pedidos
                 else "há pedidos coletados, mas nenhum com cupom do vendedor "
                      "na janela")

    dados = {"campanha": campanha, "janela": janela, "dependencia": dependencia,
             "compradores": quem, "contraste": contraste, "periodo": periodo,
             "conta": conta, "vazio": vazio, "pedidos_no_banco": tem_pedidos}

    kpis = "".join([
        _kpi(janela["pedidos"], "vendas com cupom"),
        _kpi(brl(janela["faturamento"]), "faturamento dessas vendas"),
        _kpi(brl(janela["custo"]), "custo dos cupons"),
        _kpi(_pct(janela.get("custo_pct")), "custo sobre o faturamento"),
    ])

    cabecalho_campanha = ""
    if campanha:
        beneficio = (f"{campanha['percentual']:.0f}%" if campanha["percentual"]
                     else brl(campanha["valor_fixo"]))
        minimo = (f" em compras a partir de {brl(campanha['compra_minima'])}"
                  if campanha["compra_minima"] else "")
        cabecalho_campanha = (
            f'<div class="card"><strong>{_e(campanha["nome"])}</strong> '
            f'<span style="color:var(--fraco)">· {_e(campanha["promocao_id"])}</span><br>'
            f'Desconto de {_e(beneficio)} por venda{_e(minimo)}. '
            f'{"Aberto a todos os compradores" if not campanha["codigo"] else "Código " + _e(campanha["codigo"])}. '
            f'Vale até {_e(_dia(campanha["fim"]))}.<br>'
            f'<span style="color:var(--fraco)">Orçamento {brl(campanha["orcamento"])}, '
            f'restam {brl(campanha["orcamento_restante"])}. '
            f'O Mercado Livre registra {campanha["cupons_usados"] or 0} cupom(ns) usado(s).</span></div>')

    # ---- produtos, ordenados por dependência
    linhas = []
    for d in dependencia[:30]:
        dep = d["dependencia"]
        cor = "neg" if (dep or 0) >= 50 else ("pos" if (dep or 0) < 15 else "")
        linhas.append([
            _e(truncar(d["titulo"] or d["item_id"], 60)),
            ("num", str(d["com_cupom"])),
            ("num", str(d["vendas_totais"] or "—")),
            ("num", f'<span class="{cor}">{_pct(dep)}</span>'),
            ("num", brl(d["custo"])),
        ])
    tabela = _tabela(["Produto", "Com cupom", "Vendas totais",
                      "Dependência", "Custo"], linhas)

    bloco_quem = ""
    if quem and quem["com_cupom"]:
        bloco_quem = f"""
        <h2>Quem usou</h2>
        <div class="kpis">
          {_kpi(quem["com_cupom"], "compradores com cupom")}
          {_kpi(quem["novos"], "sem compra anterior")}
          {_kpi(quem["recorrentes"], "já haviam comprado")}
          {_kpi(_pct(quem["pct_novos"]), "eram novos")}
        </div>
        <p class="sub">“Novo” é quem não aparece em nenhuma compra desde
        {_e(_dia(quem["historico_desde"]))}, que é até onde a coleta enxerga.
        Cliente antigo que não comprava há mais tempo que isso entra como novo.</p>"""

    c = contraste
    # O bloco acima mede a campanha; este mede a janela inteira. Sem dizer
    # isso, o leitor vê R$ 1.260 em cima e R$ 1.831 embaixo para "cupom" e
    # conclui que um dos dois está errado.
    bloco_contraste = f"""
    <h2>Onde isso se encaixa</h2>
    <div class="card">
      Olhando os <strong>{dias} dias</strong> inteiros (e não só esta campanha),
      o desconto que saiu da conta foi de
      <strong>{brl(c["total"])}</strong>:<br>
      · cupom — <strong>{brl(c["cupom"]["valor"])}</strong> ({_pct(c["cupom_pct"])})<br>
      · campanhas de desconto por anúncio — <strong>{brl(c["campanha_de_preco"]["valor"])}</strong><br>
      <span style="color:var(--fraco)">A campanha de cupom tem teto e prazo.
      As campanhas de desconto por anúncio não têm nenhum dos dois.</span>
    </div>"""

    per = (f"{_dia(periodo['de'])} a {_dia(periodo['ate'])}"
           if periodo["de"] else f"últimos {dias} dias")
    desde_txt = (f" desde {_dia(desde)}" if desde else "")

    pagina = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cupom · {_e(conta.nome_conta)}</title><style>{CSS}</style></head><body><div class="wrap">
<h1>Campanha de cupom{_e(desde_txt)}</h1>
<p class="sub">{_e(conta.nome_conta)} · medido pedido a pedido pela API do Mercado Livre ·
pedidos de {_e(per)}</p>
{cabecalho_campanha}
<h2>O que passou pelo cupom</h2>
<div class="kpis">{kpis}</div>
<p class="sub">Ticket médio de {brl(janela.get("ticket"))} nessas vendas.</p>

<h2>Em quais produtos</h2>
<p class="sub">“Dependência” é quanto das vendas daquele produto passou pelo cupom.
Alta significa que o produto gira com desconto; baixa significa que o cupom
acompanhou vendas que já aconteciam.</p>
{tabela}
{bloco_quem}
{bloco_contraste}

<div class="rodape">
<strong>Como ler estes números.</strong> Faturamento é o valor dos pedidos que
usaram cupom — não é venda causada pelo cupom. Ninguém consegue saber quantos
desses compradores comprariam sem o desconto, nem a API nem o painel do
Mercado Livre. O que está medido aqui é participação e custo.<br>
Gerado em {_e(para_br(agora_utc().isoformat()))} pelo zion-ml.
</div>
</div></body></html>"""
    return pagina, dados


def gerar(con: sqlite3.Connection, conta, dias: int = 60) -> tuple[str, dict]:
    """Grava a página em relatorios/<cliente>/ e devolve (caminho, dados)."""
    pagina, dados = montar(con, conta, dias=dias)
    pasta = garantir_dir(DIR_RELATORIOS / conta.cliente_id)
    destino = pasta / f"cupons-{conta.slug}-{datetime.now().strftime('%Y-%m-%d')}.html"
    destino.write_text(pagina, encoding="utf-8")
    return str(destino), dados


def texto_curto(dados: dict) -> str:
    """A versão para colar no WhatsApp, com a ressalva junto."""
    j = dados["janela"]
    c = dados["campanha"]
    linhas = []
    if c:
        beneficio = (f"{c['percentual']:.0f}%" if c["percentual"] else brl(c["valor_fixo"]))
        minimo = (f", compra mínima {brl(c['compra_minima'])}" if c["compra_minima"] else "")
        desde = f" desde {_dia(c['inicio'])}" if c.get("inicio") else ""
        linhas.append(f"Campanha de cupom ({beneficio} por venda{minimo}){desde}:")
    linhas.append(f"- {j['pedidos']} vendas com cupom")
    linhas.append(f"- {brl(j['faturamento'])} de faturamento nessas vendas")
    linhas.append(f"- {brl(j['custo'])} de custo em cupons ({_pct(j.get('custo_pct'))} do faturamento)")

    q = dados.get("compradores")
    if q and q["com_cupom"]:
        linhas.append(f"- {q['novos']} de {q['com_cupom']} compradores sem compra anterior")

    dep = [d for d in dados["dependencia"] if (d["dependencia"] or 0) >= 50]
    if dep:
        linhas.append(f"- {len(dep)} produto(s) com mais da metade das vendas via cupom")
    linhas.append("")
    linhas.append("Medido pedido a pedido pela API do ML. É o valor que passou "
                  "pelo cupom, não venda causada por ele.")
    return "\n".join(linhas)
