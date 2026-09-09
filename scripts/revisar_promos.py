"""
Revisa o que está NO AR — não o que daria para cadastrar.

O `cadastrar_promos.py` decide sobre PROPOSTAS: ele varre as `candidate` e
escolhe onde entrar. Isso deixa um ponto cego que custou caro em 02/09/2026:
anúncio já totalmente aderido não tem candidata nenhuma, então o script pula
antes mesmo de apurar custo e frete — e nunca descobre que ele está vendendo
no prejuízo. Foi assim que o #6717022002 passou despercebido em duas rodadas.

Esta revisão faz o contrário: olha TODO anúncio ativo, apura o preço que está
valendo hoje (a promoção ATIVA mais barata, que é quem manda — medido na
vitrine em 02/09) e diz qual é a margem real dele.

Não escreve nada. Nenhuma chamada de escrita, nenhuma decisão automática.

USO
  python scripts/revisar_promos.py facilita-brasil-principal
  python scripts/revisar_promos.py facilita-brasil-principal --limite 20
  python scripts/revisar_promos.py facilita-brasil-principal --csv
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from core.config import obter_conta  # noqa: E402
from core.ml_api import MLClient, sku_do_item  # noqa: E402
from core.utils import agora_iso  # noqa: E402
from cadastrar_promos import (  # noqa: E402
    avaliar, ler_custos, percentual_total, rebate_da_promocao, reais,
)

VERDE, AMAR, VERM, CINZA, FIM = "\033[92m", "\033[93m", "\033[91m", "\033[90m", "\033[0m"


def revisar(slug: str, piso: float, teto: float, limite: int | None,
            gerar_csv: bool) -> int:
    conta = obter_conta(slug)
    cli = MLClient(slug, getattr(conta, "user_id", None))
    custos, conflitos = ler_custos(slug)
    print(f"{CINZA}{len(custos)} SKUs com custo. Piso {piso:.0%}, teto {teto:.0%}. "
          f"SOMENTE LEITURA.{FIM}")

    ids = cli.ids_dos_meus_anuncios(status="active")
    if limite:
        ids = ids[:limite]
    itens = cli.detalhes_dos_itens(ids)
    print(f"{CINZA}{len(itens)} anúncios ativos a revisar…{FIM}")

    tarifa_cache: dict[tuple[str, str, int], tuple[float, float]] = {}

    def tarifa(preco: float, categoria: str, tipo: str) -> tuple[float, float] | None:
        """Igual à do cadastrar_promos: chaveada por PREÇO, porque a tarifa do
        ML tem degrau em R$ 700 (10,5%/11,5% no Clássico, 13,5%/16,5% no
        Premium)."""
        chave = (categoria, tipo, int(preco))
        if chave in tarifa_cache:
            return tarifa_cache[chave]
        r = cli.tarifa_de_venda(preco, categoria, tipo) or {}
        valor = r.get("sale_fee_amount")
        if not isinstance(valor, (int, float)):
            return None
        det = r.get("sale_fee_details") or {}
        fixa = float(det.get("fixed_fee") or 0.0)
        pct = float(det.get("percentage_fee") or 0.0) / 100.0
        if not pct and preco:
            pct = (float(valor) - fixa) / preco
        tarifa_cache[chave] = (pct, fixa)
        return pct, fixa

    linhas: list[dict] = []
    sem_custo: list[dict] = []
    sem_frete: list[dict] = []
    sem_promo: list[dict] = []
    sem_apurar: list[dict] = []
    frete_cache: dict[str, float | None] = {}

    for n, item in enumerate(itens, 1):
        corpo = item.get("body") or item
        item_id = corpo.get("id")
        if not item_id:
            continue
        titulo = (corpo.get("title") or "")[:60]

        sku = (sku_do_item(corpo) or "").strip().upper()
        if not sku:
            completo = cli.get(f"/items/{item_id}") or {}
            sku = (sku_do_item(completo) or "").strip().upper()
        chave = item_id if item_id in custos else sku
        if chave not in custos:
            sem_custo.append({"item_id": item_id, "sku": sku or "(sem SKU)",
                              "titulo": titulo})
            continue
        custo, imposto = custos[chave]

        # Um anúncio que a API se recusa a responder não pode custar os outros.
        # Em 02/09/2026 um 409 no item 131 de 177 abortou a rodada inteira: os
        # 46 seguintes nunca foram olhados e o CSV nem chegou a ser gravado.
        # O `get` do core já repete o 409; isto é a segunda linha de defesa,
        # para o que insistir em falhar. Vai para uma lista que o relatório
        # mostra — margem desconhecida é pendência, nunca zero.
        try:
            promos = cli.promocoes_do_item(item_id)
        except Exception as erro:
            sem_apurar.append({"item_id": item_id, "sku": sku or "(sem SKU)",
                               "titulo": titulo, "erro": str(erro)[:90]})
            continue
        if isinstance(promos, dict):
            promos = promos.get("results") or []
        ativas = [p for p in (promos or [])
                  if isinstance(p, dict)
                  and (p.get("status") or "").lower() == "started"
                  and (p.get("price") or 0) > 0]
        # Anúncio SEM promoção não é anúncio sem risco. A primeira versão desta
        # revisão pulava aqui, e escondeu dois SOFANUVEM vendendo a -4,6% pelo
        # preço de tabela — sem promoção nenhuma, só preço abaixo do custo mais
        # frete. Agora ele é avaliado pelo próprio preço do anúncio.
        if not ativas:
            sem_promo.append({"item_id": item_id, "sku": sku, "titulo": titulo,
                              "preco": corpo.get("price")})

        # O vendedor só paga o frete grátis se o anúncio REALMENTE oferecer.
        # Descoberto em 02/09/2026: o #6717022002 aparecia vendendo a -9,8%,
        # o único "prejuízo" da conta, porque descontávamos R$ 379,90 de frete
        # de um anúncio com `free_shipping: false`. Sem o custo fantasma ele
        # está a +21%. Eram 5 anúncios assim na FACILITA, R$ 1.223,50 de custo
        # inventado por rodada — todos sofá-cama, que perderam o Mercado Envios
        # por dimensão (tag `lost_me2_by_dimensions`) e combinam a entrega.
        #
        # `free_shipping` ausente NÃO vira zero: aí continua perguntando e
        # descontando. Errar para mais custo deixa promoção boa de fora; errar
        # para menos cadastra promoção ruim, que é o erro caro.
        oferece_frete = (corpo.get("shipping") or {}).get("free_shipping")
        if oferece_frete is False:
            frete = 0.0
        elif item_id not in frete_cache:
            frete_cache[item_id] = cli.custo_do_frete_gratis(item_id)
            frete = frete_cache[item_id]
        else:
            frete = frete_cache[item_id]
        if frete is None:
            # Frete inventado é o que faz promoção parecer lucrativa.
            sem_frete.append({"item_id": item_id, "sku": sku, "titulo": titulo})
            continue

        categoria = corpo.get("category_id") or ""
        tipo_anuncio = corpo.get("listing_type_id") or ""
        # Sem promoção, quem vale é o preço de tabela: entra como uma "campanha"
        # sintética, sem rebate, para o anúncio ser avaliado como todos os
        # outros em vez de sumir do relatório.
        base = list(ativas) or [{"price": corpo.get("price"), "type": "(sem promoção)",
                                 "name": "preço de tabela"}]
        avaliadas = []
        for p in base:
            if not p.get("price"):
                continue
            pr = round(float(p["price"]), 2)
            med = tarifa(pr, categoria, tipo_anuncio)
            if med is None:
                continue
            pct, fixa = med
            lucro, margem = avaliar(pr, custo, frete, fixa,
                                    percentual_total(pct, imposto),
                                    rebate_da_promocao(p) if ativas else 0.0)
            avaliadas.append((pr, lucro, margem, p, pct))
        if not avaliadas:
            continue

        # Quem MANDA é a mais barata — medido na vitrine em 02/09/2026, em seis
        # anúncios. Empate no preço: vale a que rende menos, que é o risco.
        manda = min(avaliadas, key=lambda a: (a[0], a[1]))
        # Troca sem custo: outra ATIVA no mesmo preço rendendo mais.
        iguais = [a for a in avaliadas
                  if abs(a[0] - manda[0]) < 0.02 and a[1] > manda[1] + 1.0]
        troca = max(iguais, key=lambda a: a[1]) if iguais else None

        m = manda[2] * 100
        if m < 0:
            estado = "PREJUIZO"
        elif m < piso * 100:
            estado = "ABAIXO DO PISO"
        elif m <= teto * 100:
            estado = "na faixa"
        else:
            estado = "acima do teto"

        linhas.append({
            "item_id": item_id, "sku": sku, "titulo": titulo,
            "preco_cadastro": corpo.get("price"),
            "preco_valendo": manda[0],
            "campanha": manda[3].get("type") or "",
            "nome_campanha": (manda[3].get("name") or "")[:30],
            "lucro": round(manda[1], 2),
            "margem_pct": round(m, 2),
            "estado": estado,
            "custo": custo, "frete": round(frete, 2),
            "taxa_ml_pct": round(manda[4] * 100, 2),
            "imposto_pct": round(imposto * 100, 2),
            "promocoes_ativas": len(avaliadas),
            "troca_ganho": round(troca[1] - manda[1], 2) if troca else "",
            "troca_para": (troca[3].get("type") or "") if troca else "",
        })
        print(f"{CINZA}  {n}/{len(itens)}{FIM}", end="\r")
        time.sleep(0.15)

    print(" " * 40, end="\r")
    return relatar(linhas, sem_custo, sem_frete, sem_promo, sem_apurar,
                   conflitos, piso, teto, slug, gerar_csv)


def relatar(linhas, sem_custo, sem_frete, sem_promo, sem_apurar, conflitos,
            piso, teto, slug, gerar_csv) -> int:
    prejuizo = [l for l in linhas if l["estado"] == "PREJUIZO"]
    abaixo = [l for l in linhas if l["estado"] == "ABAIXO DO PISO"]
    faixa = [l for l in linhas if l["estado"] == "na faixa"]
    acima = [l for l in linhas if l["estado"] == "acima do teto"]
    trocas = [l for l in linhas if l["troca_ganho"] != ""]

    print(f"\n{'─' * 72}")
    print(f"  anúncios avaliados            {len(linhas)}")
    print(f"  {VERM}vendendo no PREJUÍZO          {len(prejuizo)}{FIM}")
    print(f"  {AMAR}abaixo do piso de {piso:.0%}         {len(abaixo)}{FIM}")
    print(f"  {VERDE}dentro da faixa               {len(faixa)}{FIM}")
    print(f"  {CINZA}acima do teto de {teto:.0%}          {len(acima)}{FIM}")
    print(f"  {CINZA}(destes, sem promoção ativa)  {len(sem_promo)}"
          f"   — avaliados pelo preço de tabela{FIM}")
    print(f"  {CINZA}sem custo na tabela           {len(sem_custo)}{FIM}")
    print(f"  {CINZA}sem frete apurado             {len(sem_frete)}{FIM}")
    print(f"  {CINZA}campanhas não apuradas        {len(sem_apurar)}{FIM}")
    print(f"{'─' * 72}")

    if prejuizo:
        perda = sum(l["lucro"] for l in prejuizo)
        print(f"\n{VERM}PERDENDO DINHEIRO AGORA — {reais(abs(perda))} por rodada "
              f"de vendas:{FIM}")
        for l in sorted(prejuizo, key=lambda x: x["margem_pct"]):
            print(f"  {VERM}{l['margem_pct']:7.1f}%{FIM} {l['item_id']:16s} "
                  f"{l['sku'][:24]:24s} {l['campanha']:16s} "
                  f"R$ {l['preco_valendo']:>9.2f}  lucro {reais(l['lucro'])}")
            print(f"           {CINZA}custo {reais(l['custo'])} + frete "
                  f"{reais(l['frete'])} + taxa {l['taxa_ml_pct']}% + imposto "
                  f"{l['imposto_pct']}%{FIM}")

    if abaixo:
        print(f"\n{AMAR}Abaixo do piso — vendem magro:{FIM}")
        for l in sorted(abaixo, key=lambda x: x["margem_pct"])[:30]:
            print(f"  {AMAR}{l['margem_pct']:7.1f}%{FIM} {l['item_id']:16s} "
                  f"{l['sku'][:24]:24s} {l['campanha']:16s} "
                  f"R$ {l['preco_valendo']:>9.2f}  lucro {reais(l['lucro'])}")

    if trocas:
        soma = sum(l["troca_ganho"] for l in trocas)
        print(f"\n{VERDE}Troca sem custo para o comprador — {reais(soma)} por "
              f"rodada, em {len(trocas)} anúncios:{FIM}")
        for l in sorted(trocas, key=lambda x: -x["troca_ganho"]):
            print(f"  {VERDE}+{l['troca_ganho']:>8.2f}{FIM} {l['item_id']:16s} "
                  f"{l['sku'][:24]:24s} R$ {l['preco_valendo']:>9.2f}  "
                  f"sair de {l['campanha']} e ficar com {l['troca_para']}")

    if sem_promo:
        print(f"\n{CINZA}Sem promoção ativa ({len(sem_promo)}) — vendem pelo preço "
              f"de tabela:{FIM}")
        for s in sem_promo[:15]:
            print(f"  {s['item_id']:16s} {s['sku'][:24]:24s} R$ {s['preco']}")
        if len(sem_promo) > 15:
            print(f"  {CINZA}… e mais {len(sem_promo) - 15}{FIM}")

    if sem_custo:
        print(f"\n{AMAR}Sem custo na tabela ({len(sem_custo)}) — margem "
              f"desconhecida, confira o produto:{FIM}")
        for s in sem_custo[:15]:
            print(f"  {s['item_id']:16s} {s['sku'][:24]:24s} {s['titulo']}")
        if len(sem_custo) > 15:
            print(f"  {CINZA}… e mais {len(sem_custo) - 15}{FIM}")

    if sem_frete:
        print(f"\n{AMAR}Sem frete apurado ({len(sem_frete)}) — PULADOS de "
              f"propósito: frete zero inventado esconde prejuízo:{FIM}")
        for s in sem_frete[:15]:
            print(f"  {s['item_id']:16s} {s['sku'][:24]:24s} {s['titulo']}")

    if sem_apurar:
        print(f"\n{AMAR}Campanhas não apuradas ({len(sem_apurar)}) — a API "
              f"recusou a leitura destes. Margem DESCONHECIDA, não zero:{FIM}")
        for s_ in sem_apurar[:15]:
            print(f"  {s_['item_id']:16s} {s_['sku'][:24]:24s} {s_['erro']}")

    if conflitos:
        print(f"\n{AMAR}Custo em conflito ({len(conflitos)}) — duas fontes "
              f"discordam, decidir antes de confiar na margem:{FIM}")
        for c in sorted(conflitos)[:15]:
            print(f"  {c}")

    if gerar_csv and linhas:
        carimbo = agora_iso()[:16].replace(":", "").replace("-", "").replace("T", "-")
        saida = RAIZ / "relatorios" / f"revisao-{slug}-{carimbo}.csv"
        saida.parent.mkdir(parents=True, exist_ok=True)
        with open(saida, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()), delimiter=";")
            w.writeheader()
            w.writerows(linhas)
        print(f"\n  planilha: {saida}")

    print(f"\n{CINZA}Revisão somente leitura. Nada foi alterado no Mercado "
          f"Livre.{FIM}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug")
    p.add_argument("--piso", type=float, default=10.0)
    p.add_argument("--teto", type=float, default=15.0)
    p.add_argument("--limite", type=int, default=None)
    p.add_argument("--csv", action="store_true", dest="gerar_csv",
                   help="grava a revisão em relatorios/")
    a = p.parse_args()
    return revisar(a.slug, a.piso / 100.0, a.teto / 100.0, a.limite, a.gerar_csv)


if __name__ == "__main__":
    raise SystemExit(main())
