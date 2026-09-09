"""
Gera um PDF com os produtos da conta, suas derivacoes e o tipo de anuncio.

"Derivacao" aqui e cada ANUNCIO que compartilha o mesmo SKU. Na FACILITA isso
e regra, nao excecao: 73 SKUs espalhados em 176 anuncios, alguns com cinco
derivacoes. Elas competem entre si na mesma busca, e quando os precos divergem
o anuncio mais barato do proprio cliente ganha do irmao — canibalizacao, nao
concorrencia.

O PDF sai agrupado por SKU, mostrando de cada derivacao o tipo de anuncio
(Classico/Premium, que muda a tarifa), o preco de tabela, o preco que esta
valendo hoje e a margem. Marca em vermelho o que fura o piso e destaca os SKUs
com preco divergente entre derivacoes.

Le a planilha mais recente de `relatorios/revisao-<slug>-*.csv` para margem e
preco valendo. Sem ela, sai so com os dados do anuncio.

USO
  python scripts/relatorio_produtos_pdf.py facilita-brasil-principal
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_RIGHT  # noqa: E402
from reportlab.lib.pagesizes import A4, landscape  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

NOME_TIPO = {"gold_special": "Clássico", "gold_pro": "Premium"}
TINTA = colors.HexColor("#1f2933")
CINZA = colors.HexColor("#7b8794")
LINHA = colors.HexColor("#d7dde3")
FUNDO = colors.HexColor("#f4f6f8")
VERMELHO = colors.HexColor("#b02a37")
AMBAR = colors.HexColor("#946200")
VERDE = colors.HexColor("#1b6b3a")


def dinheiro(v) -> str:
    """R$ 1.234,56. O separador vai por format(), nao por '%' — '%,.2f' nao
    existe no formato antigo e devolvia ValueError, o que enchia o PDF de
    travessoes na primeira versao."""
    try:
        bruto = format(float(v), ",.2f")
    except (TypeError, ValueError):
        return "—"
    return "R$ " + bruto.replace(",", "@").replace(".", ",").replace("@", ".")


def carregar_revisao(slug: str) -> dict[str, dict]:
    achados = sorted(glob.glob(str(RAIZ / "relatorios" / f"revisao-{slug}-*.csv")))
    if not achados:
        return {}
    with open(achados[-1], encoding="utf-8-sig") as fh:
        return {r["item_id"]: r for r in csv.DictReader(fh, delimiter=";")}


def cor_da_margem(m: float | None) -> colors.Color:
    if m is None:
        return CINZA
    if m < 0:
        return VERMELHO
    if m < 10:
        return AMBAR
    return TINTA


def montar(slug: str, anuncios: list[dict], revisao: dict, saida: Path) -> None:
    est = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=est["Title"], fontName="Helvetica-Bold",
                        fontSize=19, textColor=TINTA, alignment=0, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=est["Normal"], fontSize=9.5,
                         textColor=CINZA, spaceAfter=14)
    h2 = ParagraphStyle("h2", parent=est["Normal"], fontName="Helvetica-Bold",
                        fontSize=11.5, textColor=TINTA, spaceBefore=10, spaceAfter=3)
    nota = ParagraphStyle("nota", parent=est["Normal"], fontSize=8.5,
                          textColor=CINZA, spaceAfter=6)
    celula = ParagraphStyle("celula", parent=est["Normal"], fontSize=7.6,
                            textColor=TINTA, leading=9)

    por_sku: dict[str, list[dict]] = defaultdict(list)
    sem_sku: list[dict] = []
    for a in anuncios:
        (por_sku[a["sku"]] if a["sku"] else sem_sku).append(a)

    doc = SimpleDocTemplate(
        str(saida), pagesize=landscape(A4),
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=13 * mm, bottomMargin=13 * mm,
        title=f"Produtos e derivações — {slug}", author="zion-ml",
    )
    hist: list = []

    # ------------------------------------------------------------------ capa
    hist.append(Paragraph("Produtos, derivações e tipo de anúncio", h1))
    hist.append(Paragraph(
        f"Conta <b>{slug}</b> · gerado em "
        f"{datetime.now().strftime('%d/%m/%Y às %H:%M')} · somente leitura", sub))

    com_varias = {s: v for s, v in por_sku.items() if len(v) > 1}
    divergentes = {s: v for s, v in com_varias.items()
                   if len({round(x["preco"], 2) for x in v}) > 1}
    tipos = defaultdict(int)
    for a in anuncios:
        tipos[a["tipo"]] += 1

    resumo = [
        ["Anúncios ativos", str(len(anuncios))],
        ["SKUs distintos", str(len(por_sku))],
        ["SKUs com mais de uma derivação", str(len(com_varias))],
        ["SKUs com preço divergente entre derivações", str(len(divergentes))],
        ["Anúncios sem SKU", str(len(sem_sku))],
        ["Clássico / Premium",
         f"{tipos.get('gold_special', 0)} / {tipos.get('gold_pro', 0)}"],
    ]
    t = Table(resumo, colWidths=[95 * mm, 30 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (1, 0), (1, -1), "Helvetica-Bold", 9),
        ("TEXTCOLOR", (0, 0), (0, -1), CINZA),
        ("TEXTCOLOR", (1, 0), (1, -1), TINTA),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINHA),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    hist.append(t)
    hist.append(Spacer(1, 8))
    hist.append(Paragraph(
        "<b>Derivação</b> é cada anúncio que compartilha o mesmo SKU. Elas disputam "
        "a mesma busca entre si: quando os preços divergem, o anúncio mais barato do "
        "próprio cliente ganha do irmão — isso é canibalização, não concorrência. "
        "O <b>tipo</b> muda a tarifa do Mercado Livre: Clássico cobra 10,5% abaixo de "
        "R$ 700 e 11,5% acima; Premium cobra 13,5% e 16,5% nos mesmos degraus.", nota))
    hist.append(PageBreak())

    # ------------------------------------------------- SKUs com preço divergente
    if divergentes:
        hist.append(Paragraph("SKUs com preço divergente entre derivações", h2))
        hist.append(Paragraph(
            "Ordenados pela maior diferença. O anúncio mais barato de cada SKU é o "
            "que tende a receber a venda — e é quase sempre o que aparece com margem "
            "baixa nas promoções.", nota))
        linhas = [["SKU", "Deriv.", "Menor preço", "Maior preço", "Diferença"]]
        ordem = sorted(divergentes.items(),
                       key=lambda kv: -(max(x["preco"] for x in kv[1])
                                        / max(min(x["preco"] for x in kv[1]), 0.01)))
        for sku, v in ordem:
            lo = min(x["preco"] for x in v)
            hi = max(x["preco"] for x in v)
            linhas.append([sku, str(len(v)), dinheiro(lo), dinheiro(hi),
                           "%.0f%%" % ((hi / lo - 1) * 100)])
        t = Table(linhas, colWidths=[75 * mm, 18 * mm, 32 * mm, 32 * mm, 24 * mm],
                  repeatRows=1)
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (-1, 0), TINTA),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FUNDO]),
            ("GRID", (0, 0), (-1, -1), 0.3, LINHA),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        hist.append(t)
        hist.append(PageBreak())

    # ------------------------------------------------------ o corpo, por SKU
    hist.append(Paragraph("Produtos e suas derivações", h2))
    hist.append(Paragraph(
        "Margem calculada sobre o preço que está valendo hoje — a promoção ativa "
        "mais barata, que é a que define o preço cobrado. "
        "<font color='#b02a37'>Vermelho</font> = prejuízo, "
        "<font color='#946200'>âmbar</font> = abaixo do piso de 10%.", nota))

    cab = ["Anúncio", "Tipo", "Preço tabela", "Valendo hoje", "Campanha",
           "Margem", "Frete grátis", "Estoque"]
    largura = [30 * mm, 18 * mm, 26 * mm, 26 * mm, 45 * mm, 20 * mm, 22 * mm, 18 * mm]

    for sku in sorted(por_sku):
        v = sorted(por_sku[sku], key=lambda x: x["preco"])
        bloco: list = []
        titulo = v[0]["titulo"][:95]
        marca = "  ·  preços divergentes" if sku in divergentes else ""
        bloco.append(Paragraph(
            f"<font size=10><b>{sku}</b></font>"
            f"<font size=8 color='#7b8794'>  ({len(v)} "
            f"{'derivação' if len(v) == 1 else 'derivações'}){marca}</font><br/>"
            f"<font size=7.5 color='#7b8794'>{titulo}</font>",
            ParagraphStyle("sku", parent=est["Normal"], spaceBefore=7, spaceAfter=3)))

        linhas = [cab]
        estilo_extra = []
        for i, a in enumerate(v, start=1):
            r = revisao.get(a["id"]) or {}
            try:
                m = float(r["margem_pct"]) if r.get("margem_pct") else None
            except ValueError:
                m = None
            valendo = dinheiro(r["preco_valendo"]) if r.get("preco_valendo") else "—"
            camp = (r.get("nome_campanha") or r.get("campanha") or "—")[:34]
            linhas.append([
                a["id"], NOME_TIPO.get(a["tipo"], a["tipo"]),
                dinheiro(a["preco"]), valendo, camp,
                ("%.1f%%" % m) if m is not None else "—",
                "sim" if a["frete_gratis"] else "não",
                str(a["estoque"] if a["estoque"] is not None else "—"),
            ])
            estilo_extra.append(("TEXTCOLOR", (5, i), (5, i), cor_da_margem(m)))
            if m is not None and m < 10:
                estilo_extra.append(("FONT", (5, i), (5, i), "Helvetica-Bold", 7.6))
        t = Table(linhas, colWidths=largura, repeatRows=1)
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.2),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 7.6),
            ("TEXTCOLOR", (0, 0), (-1, 0), CINZA),
            ("BACKGROUND", (0, 0), (-1, 0), FUNDO),
            ("ALIGN", (2, 0), (3, -1), "RIGHT"),
            ("ALIGN", (5, 0), (-1, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINHA),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ] + estilo_extra))
        bloco.append(t)
        hist.append(KeepTogether(bloco))

    # ------------------------------------------------------------- sem SKU
    if sem_sku:
        hist.append(PageBreak())
        hist.append(Paragraph("Anúncios sem SKU", h2))
        hist.append(Paragraph(
            "Sem SKU não há como casar custo, e sem custo não há margem. "
            "Dá para resolver pelo código do anúncio no custos.csv, mas o certo é "
            "preencher o SKU no Mercado Livre.", nota))
        linhas = [["Anúncio", "Tipo", "Preço", "Título"]]
        for a in sem_sku:
            linhas.append([a["id"], NOME_TIPO.get(a["tipo"], a["tipo"]),
                           dinheiro(a["preco"]),
                           Paragraph(a["titulo"][:110], celula)])
        t = Table(linhas, colWidths=[30 * mm, 20 * mm, 26 * mm, 130 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (-1, 0), TINTA),
            ("GRID", (0, 0), (-1, -1), 0.3, LINHA),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        hist.append(t)

    def rodape(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(CINZA)
        canvas.drawString(14 * mm, 8 * mm, f"zion-ml · {slug}")
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 8 * mm,
                               "página %d" % canvas.getPageNumber())
        canvas.restoreState()

    doc.build(hist, onFirstPage=rodape, onLaterPages=rodape)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug")
    p.add_argument("--dados", default=None,
                   help="JSON com os anúncios já coletados (evita ir na API)")
    a = p.parse_args()

    if a.dados and os.path.exists(a.dados):
        anuncios = json.load(open(a.dados, encoding="utf-8"))
    else:
        from core.config import obter_conta
        from core.ml_api import MLClient, sku_do_item
        conta = obter_conta(a.slug)
        cli = MLClient(a.slug, getattr(conta, "user_id", None))
        anuncios = []
        for it in cli.detalhes_dos_itens(cli.ids_dos_meus_anuncios(status="active")):
            b = it.get("body") or it
            sh = b.get("shipping") or {}
            anuncios.append({
                "id": b.get("id"), "sku": (sku_do_item(b) or "").strip().upper(),
                "titulo": b.get("title") or "", "preco": float(b.get("price") or 0),
                "tipo": b.get("listing_type_id") or "",
                "frete_gratis": sh.get("free_shipping"),
                "estoque": b.get("available_quantity"),
            })

    revisao = carregar_revisao(a.slug)
    carimbo = datetime.now().strftime("%Y%m%d-%H%M")
    saida = RAIZ / "relatorios" / f"produtos-{a.slug}-{carimbo}.pdf"
    saida.parent.mkdir(parents=True, exist_ok=True)
    montar(a.slug, anuncios, revisao, saida)
    print(f"{len(anuncios)} anúncios · revisão: "
          f"{'sim' if revisao else 'não encontrada'}")
    print(saida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
