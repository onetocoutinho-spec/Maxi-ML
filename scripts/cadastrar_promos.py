"""
Cadastra as promoções liberadas pelo Mercado Livre — sabendo o custo.

O problema que este script resolve: a Central de Promoções mostra "Você
recebe", que já é líquido de tarifa e de frete grátis, mas NÃO conhece o
custo do produto nem o imposto. Aceitar a proposta do ML é um clique, e na
página 1 da FACILITA (02/09/2026) 7 das 27 propostas davam PREJUÍZO — quatro
delas eram a sugestão "Melhorar" do próprio Mercado Livre.

A regra: margem líquida entre 10% (piso) e 15% (teto). O piso era 8% e subiu
para 10% em 02/09/2026 a pedido do Matheus.
  - dentro da faixa  -> entra no preço que o ML propôs
  - acima do teto    -> entra num preço MENOR, calculado para bater o teto
                        (desconto mais fundo = mais chance de ganhar a vitrine)
  - abaixo do piso   -> não entra, e sai na lista de recusados

Fórmula da margem (a mesma que fechou com o "Você recebe" do ML em 16 casos
da Decoralli):
    Você recebe = preço − tarifa − frete grátis
    Lucro       = Você recebe − custo − imposto × preço
    Margem      = Lucro ÷ preço
O rebate do ML já está embutido na tarifa que ele cobra — somar de novo é
contar duas vezes.

Preço-alvo para uma margem m:
    P = (tarifa_fixa + frete + custo) ÷ (1 − tarifa_% − imposto − m)

MODOS
  --conferir ITEM   mostra o que a API responde para UM anúncio e para de ir.
                    Use antes da primeira rodada numa conta nova: é o único
                    jeito honesto de saber se os campos vieram com o nome que
                    este script espera.
  (sem flag)        simulação: varre a conta, calcula tudo, imprime e grava o
                    CSV. Não escreve nada no Mercado Livre.
  --aplicar         faz a adesão de verdade. Só o que passou na faixa.

USO
  python scripts/cadastrar_promos.py facilita-brasil-principal --conferir MLB4701515641
  python scripts/cadastrar_promos.py facilita-brasil-principal
  python scripts/cadastrar_promos.py facilita-brasil-principal --aplicar
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core.config import obter_conta  # noqa: E402
from core.ml_api import MLClient, sku_do_item  # noqa: E402
from core.utils import agora_iso  # noqa: E402

# Vigência do PRICE_DISCOUNT. Esse tipo é desconto do próprio vendedor: o ML
# não sugere data nenhuma, então quem define é este script. Sete dias corridos,
# renovável a cada rodada, decidido em 02/09/2026 — janela curta de propósito,
# enquanto a regra de margem ainda está sendo calibrada. Um desconto longo
# trava o preço num tipo cujo custo e frete ainda mudam.
DIAS_PRICE_DISCOUNT = 7


def janela_price_discount(dias: int = DIAS_PRICE_DISCOUNT) -> tuple[str, str]:
    """Início e fim do desconto do vendedor, em formato local (sem fuso)."""
    inicio = datetime.now().replace(microsecond=0)
    fim = (inicio + timedelta(days=dias)).replace(hour=23, minute=59, second=59)
    marca = "%Y-%m-%dT%H:%M:%S"
    return inicio.strftime(marca), fim.strftime(marca)


VERDE, AMAR, VERM, CINZA, FIM = "\033[92m", "\033[93m", "\033[91m", "\033[90m", "\033[0m"

# Só estas geram decisão: liberadas e ainda não aceitas.
CANDIDATA = ("candidate",)

# A taxa fixa por tipo de anúncio que a Facilita usa na planilha. NÃO é mais o
# padrão: na rodada de 02/09/2026 ela discordou do que o ML cobra em 264 dos
# 459 cenários, R$ 2.985,68 por rodada de vendas. O pior caso foi o
# SOFAMILAO-PRETO180 (Premium), em que a casa supõe 16% e o ML cobra 13,5% —
# a planilha se cobrava 2,5 pontos a mais do que o ML e escondia R$ 35,62 de
# margem por venda. Por decisão do Neto o padrão passou a ser a taxa medida
# anúncio a anúncio; `--taxa-casa` volta para estes números.
TAXA_FIXA = {"gold_special": 0.115, "gold_pro": 0.16}
NOME_TIPO = {"gold_special": "Clássico", "gold_pro": "Premium"}

# Quem deixa escolher o preço NÃO é o tipo da campanha — é a presença de
# min_discounted_price/max_discounted_price na resposta. Medido na FACILITA em
# 02/09/2026: SELLER_CAMPAIGN (Facilita 08), DEAL e PRICE_DISCOUNT vêm com
# price=0 e a faixa 192–864; SMART vem com price=786,28 e sem faixa nenhuma —
# nesse é pegar ou largar. Listar tipos "livres" na mão erraria o SMART.


def preco_proposto(p: dict) -> float | None:
    """O preço que a campanha oferece. price=0 significa 'use o sugerido'."""
    for chave in ("price", "suggested_discounted_price"):
        valor = p.get(chave)
        if isinstance(valor, (int, float)) and valor > 0:
            return float(valor)
    return None


def faixa_de_preco(p: dict) -> tuple[float, float] | None:
    """(mínimo, máximo) que a campanha aceita, ou None se o preço é fixo."""
    piso, teto = p.get("min_discounted_price"), p.get("max_discounted_price")
    if isinstance(piso, (int, float)) and isinstance(teto, (int, float)):
        return float(piso), float(teto)
    return None


# --------------------------------------------------------------- custo

def _so_alfanumerico(texto: str) -> str:
    """
    Reduz um SKU ao que nele é estável: sem separador, sem acento, em maiúsculas.

    Mesma regra do `core/precificacao.py` — o mesmo produto aparece escrito de
    N formas na mesma planilha, e ponto, hífen e underline não distinguem
    produto nenhum.
    """
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", str(texto or ""))
        if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]", "", sem_acento).upper()


class _TabelaDeCusto(dict):
    """
    Tabela de custo que aceita o SKU escrito de outro jeito.

    Herda de dict para os dois scripts que a consomem continuarem usando
    `sku in custos` e `custos[sku]` sem mudar uma linha. O casamento exato tem
    prioridade absoluta; a forma normalizada só entra quando o exato falha.
    """

    def __init__(self, exatos: dict, aproximados: dict):
        super().__init__(exatos)
        self._aprox = aproximados

    def __missing__(self, chave):
        valor = self._aprox.get(_so_alfanumerico(chave))
        if valor is None:
            raise KeyError(chave)
        return valor

    def __contains__(self, chave):
        return (super().__contains__(chave)
                or _so_alfanumerico(chave) in self._aprox)

    def get(self, chave, padrao=None):
        try:
            return self[chave]
        except KeyError:
            return padrao


def ler_custos(slug: str) -> tuple[dict[str, tuple[float, float]], set[str]]:
    """
    (chave -> (custo, imposto), chaves em conflito). Vírgula decimal, imposto '7%'.

    A chave normalmente é o SKU, mas pode ser o CÓDIGO DO ANÚNCIO (MLB…) —
    e aí vale para aquele anúncio específico, por cima do SKU. Existe porque
    há anúncio sem SKU nenhum: o #4398500251 e o #5696570996 voltam da API com
    seller_custom_field nulo, lista de atributos vazia e as duas variações
    também sem nada. Não é bug de leitura, é o anúncio que nunca teve SKU
    preenchido. Enquanto ninguém preenche no ML, dá para casar o custo pelo
    código do anúncio.

    Uma linha cuja `observacao` começa com CONFLITO tem duas fontes de custo
    discordando e fica DE FORA até alguém decidir. Em 02/09/2026 eram 21 SKUs,
    com diferenças de R$ 15 a R$ 100 entre a Tabela Turbo e o plano de 01/09 —
    e com piso de 10%, R$ 20 num produto de R$ 600 são três pontos de margem,
    o bastante para cadastrar promoção que não devia. Custo em dúvida não vira
    preço: vira pendência.

    O casamento é exato primeiro e, só se falhar, ignora separador, acento e
    caixa — a mesma normalização que `core/precificacao.py` já usava. Sem isso
    o custo existe e mesmo assim o anúncio cai em "sem custo": em 02/09/2026 a
    Decoralli tinha POLTRONAMONA-CORINOPRETO cadastrado como
    POLTRONAMONACORINO-PRETO, mesmo produto, mesmo custo, hífen um caractere
    adiante — e o anúncio ficava sem margem apurada por causa do traço.

    Quando dois SKUs diferentes viram a MESMA chave normalizada com custos
    diferentes, nenhum dos dois é usado por essa via: aí a semelhança está
    escondendo divergência real, e adivinhar é o erro caro.
    """
    caminho = RAIZ / "contas" / slug / "custos.csv"
    if not caminho.exists():
        raise SystemExit(f"{VERM}Não achei {caminho}.{FIM}")
    tabela: dict[str, tuple[float, float]] = {}
    conflito: set[str] = set()
    with caminho.open(encoding="utf-8-sig", newline="") as fh:
        for linha in csv.DictReader(fh, delimiter=";"):
            sku = (linha.get("sku") or "").strip().upper()
            if not sku:
                continue
            try:
                custo = float((linha.get("custo") or "").replace(".", "").replace(",", "."))
            except ValueError:
                continue
            imposto = (linha.get("imposto") or "").strip().rstrip("%").replace(",", ".")
            try:
                imp = float(imposto) / 100.0
            except ValueError:
                imp = 0.0
            if (linha.get("observacao") or "").strip().upper().startswith("CONFLITO"):
                conflito.add(sku)
                continue
            tabela[sku] = (custo, imp)

    aproximado: dict[str, tuple[float, float]] = {}
    ambiguo: set[str] = set()
    for sku, valor in tabela.items():
        chave = _so_alfanumerico(sku)
        if chave in aproximado and aproximado[chave] != valor:
            ambiguo.add(chave)
        aproximado[chave] = valor
    for chave in ambiguo:
        aproximado.pop(chave, None)

    return _TabelaDeCusto(tabela, aproximado), conflito


# --------------------------------------------------------------- margem

def reais(valor: float) -> str:
    """
    R$ no formato brasileiro: 9.356,19.

    Existe porque a primeira versao formatava em ingles e dava um
    `.replace(",", ".")` no fim da frase inteira — o que trocava o separador
    de milhar E as virgulas do texto, e imprimia "R$ 9.356.19" e "Somando. sao".
    """
    return f"R$ {valor:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def rebate_da_promocao(p: dict) -> float:
    """
    Quanto o ML devolve de tarifa nesta campanha, em reais.

    `meli_percentage` é a fatia do DESCONTO que o Mercado Livre banca, medida
    sobre o preço ORIGINAL — e ela chega ao vendedor como redução de tarifa.
    Conferido na FACILITA em 02/09/2026: no #4701515641 a campanha com
    meli_percentage 1,9 sobre preço original de R$ 960 dá R$ 18,24, e a tela
    do ML mostrou uma redução de R$ 18,04; a de 0,9 dá R$ 8,64 contra os
    R$ 9,02 da tela. A diferença de centavos vem do percentual chegar
    arredondado numa casa decimal.
    """
    pct = p.get("meli_percentage")
    base = p.get("original_price")
    if isinstance(pct, (int, float)) and isinstance(base, (int, float)):
        return float(pct) / 100.0 * float(base)
    return 0.0


def percentual_total(taxa_pct: float, imposto: float) -> float:
    """
    Taxa e imposto somados num percentual só, como a Facilita calcula.

    Os dois incidem sobre o MESMO valor — o preço de venda cheio —, então
    somar antes e descontar uma vez dá exatamente o mesmo que descontar um
    de cada vez. Fica assim porque é como eles leem: 11,5% + 7% = 18,5% no
    Clássico, e 16% + 7% = 23% no Premium.

    O que NÃO valeria é descontar em cascata (tirar a taxa e depois cobrar o
    imposto sobre o que sobrou). Isso daria um número menor e errado, e é o
    engano que essa soma explícita evita.
    """
    return taxa_pct + imposto


def preco_alvo(custo: float, frete: float, taxa_fixa: float, pct_total: float,
               margem: float, rebate: float = 0.0) -> float | None:
    """
    O preço que entrega exatamente essa margem. None se a conta não fecha.

    O rebate entra como custo NEGATIVO fixo, e não como desconto de taxa,
    porque ele é calculado sobre o preço original — não muda quando o preço
    da promoção muda.
    """
    denominador = 1.0 - pct_total - margem
    if denominador <= 0.01:
        return None
    return (taxa_fixa + frete + custo - rebate) / denominador


def avaliar(preco: float, custo: float, frete: float, taxa_fixa: float,
            pct_total: float, rebate: float = 0.0) -> tuple[float, float]:
    """
    (lucro em R$, margem em fração) daquele preço. A conta da Facilita:

        lucro  = venda − (taxa+imposto) − custo − frete + rebate
        margem = lucro ÷ venda × 100

    `pct_total` já vem somado (18,5% no Clássico, 23% no Premium) e é
    aplicado UMA vez sobre o preço de venda cheio.
    """
    lucro = preco * (1.0 - pct_total) - taxa_fixa - frete + rebate - custo
    return lucro, (lucro / preco if preco else 0.0)


def escolher(linhas: list[dict], todas: bool) -> list[dict]:
    """
    Qual das campanhas liberadas o anúncio entra.

    Um anúncio pode ter várias propostas ao mesmo tempo — o #4701515641 tinha
    cinco em 02/09/2026 (duas SMART, uma PRICE_DISCOUNT, uma DEAL e a Facilita
    08). Entrar nas cinco não é cinco vezes melhor: vale o desconto mais fundo,
    e o resto só amarra o anúncio a datas. Por padrão entra na que deixa MAIS
    DINHEIRO por venda — a lição das promoções do Ênio, onde a proposta rasa de
    5% rendeu R$ 380 a mais por venda que a campanha ativa de 31%.

    As descartadas ficam no CSV como ALTERNATIVA, para dar para conferir a
    escolha em vez de ter que confiar nela.
    """
    if todas or len(linhas) <= 1:
        return linhas
    viaveis = [l for l in linhas if l["decisao"].startswith("ENTRAR")]
    if not viaveis:
        return linhas
    # Empate é comum: no #4701515641 a PRICE_DISCOUNT, a DEAL "9.9" e a
    # Facilita 08 ofereciam os mesmos R$ 816. Nesse caso vale a CAMPANHA, que
    # põe o anúncio numa vitrine com nome e data; a PRICE_DISCOUNT é só um
    # desconto solto, sem id e sem exposição.
    # Critérios de desempate, nesta ordem: dinheiro por venda; MENOR PREÇO;
    # ser campanha de verdade (a PRICE_DISCOUNT é desconto solto, sem id e sem
    # vitrine); e durar mais — entre a "9.9" até 10/set e a "Facilita 08" até
    # 3/set, pelo mesmo dinheiro, vale a que fica mais tempo no ar.
    #
    # O MENOR PREÇO entrou em 02/09/2026. Duas campanhas podem deixar o MESMO
    # dinheiro por venda em preços diferentes, porque o rebate do ML cobre a
    # diferença: uma a R$ 900 sem rebate e outra a R$ 850 com R$ 50 de rebate
    # rendem igual para o vendedor. Sem este critério a escolha era arbitrária
    # e podia cair na mais cara. Empatado o que entra no bolso, o melhor
    # negócio é o comprador pagar menos — é anúncio mais competitivo pelo mesmo
    # resultado, e quem paga a diferença é o ML.
    melhor = max(viaveis, key=lambda l: (round(l["lucro_rs"], 2),
                                         -round(l["preco_a_cadastrar"], 2),
                                         l["tipo"] != "PRICE_DISCOUNT",
                                         bool(l["promocao_id"]),
                                         l["fim"] or ""))
    for l in linhas:
        if l is not melhor and l["decisao"].startswith("ENTRAR"):
            l["decisao"] = "ALTERNATIVA"
    return linhas


# --------------------------------------------------------------- conferência

def conferir(cli: MLClient, item_id: str) -> int:
    """Despeja o que a API responde. Nenhuma escrita, nenhum palpite."""
    item = (cli.detalhes_dos_itens([item_id]) or [{}])[0]
    corpo = item.get("body") or item
    print(f"\n{AMAR}ANÚNCIO{FIM} {item_id}")
    print(f"  título:     {corpo.get('title')}")
    print(f"  SKU:        {sku_do_item(corpo)}")
    print(f"  preço:      {corpo.get('price')}")
    print(f"  categoria:  {corpo.get('category_id')}   tipo: {corpo.get('listing_type_id')}")

    print(f"\n{AMAR}COMO O SKU FOI PROCURADO{FIM}")
    print(f"  seller_custom_field: {corpo.get('seller_custom_field')!r}")
    print(f"  atributos: {[(a.get('id'), a.get('value_name')) for a in (corpo.get('attributes') or []) if a.get('id') in ('SELLER_SKU', 'GTIN')]}")
    completo = cli.get(f"/items/{item_id}") or {}
    print(f"  {CINZA}(anúncio inteiro, sem projeção de campos){FIM}")
    print(f"  seller_custom_field: {completo.get('seller_custom_field')!r}")
    for v in (completo.get("variations") or [])[:4]:
        print(f"    id {v.get('id')} · campo livre {v.get('seller_custom_field')!r} · "
              f"attrs {[(a.get('id'), a.get('value_name')) for a in (v.get('attributes') or []) if a.get('id') in ('SELLER_SKU', 'GTIN')]}")
    print(f"  {VERDE}SKU resolvido: {sku_do_item(corpo) or sku_do_item(completo)}{FIM}")

    vars_ = corpo.get("variations")
    print(f"  variações: {len(vars_) if isinstance(vars_, list) else vars_}")
    for v in (vars_ or [])[:4]:
        print(f"    id {v.get('id')} · campo livre {v.get('seller_custom_field')!r} · "
              f"attrs {[(a.get('id'), a.get('value_name')) for a in (v.get('attributes') or []) if a.get('id') in ('SELLER_SKU', 'GTIN')]}")

    print(f"\n{AMAR}FRETE GRÁTIS (custo do vendedor){FIM}")
    valor, tentativas = cli.custo_do_frete_gratis(item_id, detalhar=True)
    for caminho, resposta in tentativas:
        print(f"  {caminho}")
        print(f"    {json.dumps(resposta, ensure_ascii=False)[:300]}")
    print(f"  {VERDE if valor is not None else VERM}resultado: {valor}{FIM}")

    print(f"\n{AMAR}TARIFA{FIM}")
    print(json.dumps(cli.tarifa_de_venda(corpo.get("price") or 0,
                                         corpo.get("category_id") or "",
                                         corpo.get("listing_type_id") or ""),
                     ensure_ascii=False, indent=2)[:1500])

    print(f"\n{AMAR}PROMOÇÕES DO ITEM{FIM}")
    print(json.dumps(cli.promocoes_do_item(item_id), ensure_ascii=False, indent=2)[:4000])
    print(f"\n{CINZA}O script usa: type, status, price, suggested_discounted_price,")
    print(f"min_discounted_price, max_discounted_price e id (quando existe — o")
    print(f"PRICE_DISCOUNT vem sem id).{FIM}")
    print(f"\n{AMAR}Atenção à tarifa:{FIM} /sites/MLB/listing_prices devolve a tarifa")
    print(f"CHEIA. As campanhas 'com redução das suas tarifas' cobram menos — no")
    print(f"#4701515641 a tela mostrou R$ 71,61 onde a tabela dá R$ 89,65. A conta")
    print(f"deste script erra para MENOS margem nesses casos, então ele deixa de")
    print(f"fora promoção boa; nunca cadastra promoção ruim por causa disso.\n")
    return 0


# --------------------------------------------------------------- rodada

def rodar(slug: str, piso: float, teto: float, aplicar: bool,
          imposto_forcado: float | None, limite: int | None,
          todas: bool, sem_rebate: bool, usar_casa: bool) -> int:
    conta = obter_conta(slug)
    cli = MLClient(slug, getattr(conta, "user_id", None))
    custos, em_conflito = ler_custos(slug)
    print(f"{CINZA}{len(custos)} SKUs com custo, {len(em_conflito)} em conflito "
          f"(pulados). Piso {piso:.0%}, teto {teto:.0%}, imposto da tabela, "
          f"taxa {'fixa da casa (11,5/16)' if usar_casa else 'medida por anúncio'}, "
          f"rebate {'FORA' if sem_rebate else 'somado'}."
          f"{' MODO SIMULAÇÃO.' if not aplicar else ''}{FIM}")

    ids = cli.ids_dos_meus_anuncios(status="active")
    if limite:
        ids = ids[:limite]
    print(f"{CINZA}{len(ids)} anúncios ativos a conferir…{FIM}")

    plano: list[dict] = []
    sem_custo: list[dict] = []
    sem_frete: list[dict] = []
    conflitados: list[dict] = []
    divergencias: list[dict] = []
    trocas: list[dict] = []
    frete_cache: dict[str, float | None] = {}
    tarifa_cache: dict[tuple[str, str, int], tuple[float, float]] = {}

    def tarifa(preco: float, categoria: str, tipo: str) -> tuple[float, float] | None:
        """
        (percentual, taxa fixa) daquela categoria e tipo de anúncio.

        O CACHE LEVA O PREÇO, e isso não é detalhe. A versão anterior guardava
        uma tarifa por (categoria, tipo) dizendo que "a tarifa do ML é linear
        no preço" — não é. Medido em 02/09/2026 nas categorias MLB458191,
        MLB186067 e MLB31039, todas gold_special: **10,5% abaixo de R$ 700 e
        11,5% a partir de R$ 700**, degrau no mesmo ponto nas três, ou seja
        regra do site e não da categoria.

        O estrago: a primeira consulta de uma categoria fixava o percentual
        para todos os preços daquela categoria na rodada inteira. Se o primeiro
        anúncio era barato, os caros herdavam 10,5% onde o ML cobra 11,5% — e
        aí a margem sai INFLADA, que é o erro perigoso. Foi assim que o
        #4701515641 apareceu com tarifa R$ 81,85 onde a Central de Promoções
        mostrava R$ 89,65.

        Chavear por preço custa mais chamadas, mas preço repetido (o mesmo SKU
        em vários anúncios) continua batendo no cache.
        """
        chave = (categoria, tipo, int(preco))
        if chave in tarifa_cache:
            return tarifa_cache[chave]
        resposta = cli.tarifa_de_venda(preco, categoria, tipo) or {}
        valor = resposta.get("sale_fee_amount")
        if not isinstance(valor, (int, float)):
            return None
        det = resposta.get("sale_fee_details") or {}
        fixa = float(det.get("fixed_fee") or 0.0)
        pct = float(det.get("percentage_fee") or 0.0) / 100.0
        if not pct and preco:
            pct = (float(valor) - fixa) / preco
        tarifa_cache[chave] = (pct, fixa)
        return pct, fixa

    # Progresso na mesma linha. Uma varredura de 178 anúncios leva minutos e a
    # versão anterior não imprimia nada nesse tempo todo — não dava para saber
    # se estava viva ou travada, e "esperar" e "travou" pareciam iguais.
    itens = cli.detalhes_dos_itens(ids)
    total = len(itens)
    for n, item in enumerate(itens, 1):
        if n % 5 == 0 or n == total:
            print(f"\r{CINZA}  {n}/{total} anúncios · {len(plano)} propostas · "
                  f"{len(sem_custo)} sem custo{FIM}   ", end="", flush=True)
        item_id = item.get("id")
        if not item_id:
            continue
        promos = cli.promocoes_do_item(item_id)
        if isinstance(promos, dict):
            promos = promos.get("results") or []
        candidatas = [p for p in (promos or [])
                      if isinstance(p, dict)
                      and (p.get("status") or "").lower() in CANDIDATA]
        if not candidatas:
            continue

        # As que JÁ ESTÃO VALENDO. O script decidia só sobre `candidate` e era
        # cego para estas — o que custou caro em 02/09/2026: 40 das 137 adesões
        # daquela rodada tinham uma promoção ativa MAIS BARATA no mesmo
        # anúncio, 8 delas furando o piso e uma vendendo no prejuízo. Conferido
        # na vitrine em seis anúncios: quem manda no preço cobrado é sempre a
        # mais barata, nunca a que este script cadastrou.
        ativas = [q for q in (promos or [])
                  if isinstance(q, dict)
                  and (q.get("status") or "").lower() == "started"
                  and (q.get("price") or 0) > 0]
        promo_ativa = min(ativas, key=lambda q: float(q["price"])) if ativas else None
        preco_ativo = round(float(promo_ativa["price"]), 2) if promo_ativa else None

        sku = (sku_do_item(item) or "").strip().upper()
        if not sku:
            # A leitura em lote (/items?ids=…&attributes=…) devolveu o
            # #4398500251 sem SKU nenhum — nem no anúncio, nem nas duas
            # variações. Mas a tela do vendedor mostra SOFABENY-BEGE140 e
            # SOFABENY-GRAFITE140 nessas mesmas variações. Ou seja, o que falta
            # é da projeção de campos, não do anúncio. Quando vier vazio, vale
            # perguntar o anúncio inteiro — é uma chamada a mais só para os
            # poucos que caem aqui.
            completo = cli.get(f"/items/{item_id}") or {}
            sku = (sku_do_item(completo) or "").strip().upper()
        titulo = (item.get("title") or "")[:60]
        # O código do anúncio, quando está na tabela, manda mais que o SKU.
        if item_id in custos:
            sku = item_id
        if sku in em_conflito:
            conflitados.append({"item_id": item_id, "sku": sku, "titulo": titulo,
                                "propostas": len(candidatas)})
            continue
        if sku not in custos:
            sem_custo.append({"item_id": item_id, "sku": sku or "(sem SKU)",
                              "titulo": titulo, "propostas": len(candidatas)})
            continue

        custo, imposto = custos[sku]
        if imposto_forcado is not None:
            imposto = imposto_forcado

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
        oferece_frete = (item.get("shipping") or {}).get("free_shipping")
        if oferece_frete is False:
            frete = 0.0
        elif item_id not in frete_cache:
            frete_cache[item_id] = cli.custo_do_frete_gratis(item_id)
            frete = frete_cache[item_id]
        else:
            frete = frete_cache[item_id]
        if frete is None:
            # Assumir frete zero é o erro que cadastra promoção no prejuízo:
            # em estofado o frete grátis chega a R$ 191 por venda.
            sem_frete.append({"item_id": item_id, "sku": sku, "titulo": titulo,
                              "propostas": len(candidatas)})
            continue

        # Quanto cada promoção JÁ ATIVA deixa por venda. Cada uma medida com a
        # tarifa do SEU preço, porque a tarifa tem degrau em R$ 700 — usar a
        # taxa de um preço para avaliar outro é o bug de 02/09/2026.
        tipo_do_anuncio = item.get("listing_type_id") or ""
        ativas_avaliadas: list[tuple[float, float, dict]] = []
        for q in ativas:
            pq = round(float(q["price"]), 2)
            med_q = tarifa(pq, item.get("category_id") or "", tipo_do_anuncio)
            if med_q is None:
                continue
            pct_q, fixa_q = med_q
            lq, _mq = avaliar(pq, custo, frete, fixa_q,
                              percentual_total(pct_q, imposto),
                              0.0 if sem_rebate else rebate_da_promocao(q))
            ativas_avaliadas.append((pq, lq, q))

        # TROCA SEM CUSTO PARA O COMPRADOR. Entre as promoções JÁ ATIVAS, quem
        # manda no preço cobrado é a mais barata. Se existe outra ATIVA no
        # MESMO preço que deixa mais dinheiro — porque tem rebate do ML e a
        # outra não — então sair da pior é ganho puro: o comprador paga
        # exatamente o mesmo e o vendedor recebe mais.
        #
        # Não é o script que sai: sair muda preço público e é decisão humana.
        # Aqui ele só mostra o caso, do jeito que já mostra o piso furado. Foi
        # assim no #7191463116, onde 4 pontos de margem estavam presos numa
        # PRICE_DISCOUNT sem rebate ao lado de uma SMART no mesmo preço.
        if len(ativas_avaliadas) > 1:
            manda = min(ativas_avaliadas, key=lambda a: (a[0], a[1]))
            iguais = [a for a in ativas_avaliadas
                      if abs(a[0] - manda[0]) < 0.02 and a[1] > manda[1] + 1.0]
            if iguais:
                melhor_i = max(iguais, key=lambda a: a[1])
                trocas.append({
                    "item_id": item_id, "sku": sku, "titulo": titulo,
                    "preco": manda[0],
                    "sair_de": manda[2].get("type") or "",
                    "sair_lucro": round(manda[1], 2),
                    "fica": melhor_i[2].get("type") or "",
                    "fica_lucro": round(melhor_i[1], 2),
                    "ganho": round(melhor_i[1] - manda[1], 2),
                })

        linhas_do_item: list[dict] = []
        for p in candidatas:
            proposto = preco_proposto(p)
            if proposto is None:
                continue
            tipo_anuncio = item.get("listing_type_id") or ""
            medida = tarifa(proposto, item.get("category_id") or "", tipo_anuncio)
            if medida is None:
                continue
            pct_medido, taxa_fixa = medida
            if not usar_casa or tipo_anuncio not in TAXA_FIXA:
                taxa_pct = pct_medido
            else:
                taxa_pct = TAXA_FIXA[tipo_anuncio]
                taxa_fixa = 0.0
                if abs(pct_medido - taxa_pct) > 0.005:
                    divergencias.append({
                        "item_id": item_id, "sku": sku, "titulo": titulo,
                        "tipo": NOME_TIPO.get(tipo_anuncio, tipo_anuncio),
                        "fixa_pct": taxa_pct * 100, "medida_pct": pct_medido * 100,
                        "por_venda": abs(pct_medido - taxa_pct) * proposto})

            rebate = 0.0 if sem_rebate else rebate_da_promocao(p)
            pct_total = percentual_total(taxa_pct, imposto)
            lucro, margem = avaliar(proposto, custo, frete, taxa_fixa,
                                    pct_total, rebate)
            tipo = p.get("type") or ""

            _l_final = lucro
            lucro_sem_afundar = lucro
            if margem < piso:
                decisao, preco_final, margem_final = "RECUSAR", proposto, margem
            elif margem <= teto:
                decisao, preco_final, margem_final = "ENTRAR", proposto, margem
            else:
                alvo = preco_alvo(custo, frete, taxa_fixa, pct_total, teto, rebate)
                faixa = faixa_de_preco(p)
                if alvo is None or faixa is None:
                    # Campanha de preço fixo: entrar no preço do ML e
                    # ganhar margem acima do teto é melhor que não entrar.
                    decisao, preco_final, margem_final = "ENTRAR", proposto, margem
                else:
                    alvo = min(max(alvo, faixa[0]), faixa[1], proposto)
                    if preco_ativo is not None and preco_ativo <= alvo + 0.02:
                        # Afundar aqui não compra vitrine nenhuma: já existe
                        # promoção ATIVA mais barata neste anúncio, e é ela que
                        # define o preço cobrado. Descer só entregaria margem
                        # sem mudar um centavo do que o comprador paga.
                        decisao, preco_final, margem_final = (
                            "ENTRAR (sem afundar: ativa mais barata)",
                            proposto, margem)
                    else:
                        _l, m2 = avaliar(alvo, custo, frete, taxa_fixa,
                                         pct_total, rebate)
                        _l_final = _l
                        lucro_sem_afundar = lucro
                        decisao, preco_final, margem_final = "ENTRAR (afundado)", alvo, m2

            linhas_do_item.append({
                "item_id": item_id, "sku": sku, "titulo": titulo,
                "promocao_id": p.get("id"), "tipo": tipo,
                # SMART e PRICE_MATCHING exigem este id no POST; sem ele o ML
                # responde "Offer id is required". Vem CANDIDATE-… enquanto é
                # proposta e OFFER-… depois de aderido.
                "ref_id": p.get("ref_id") or "",
                "nome": p.get("name") or tipo,
                "fim": p.get("finish_date") or "",
                "preco_proposto": round(proposto, 2),
                "margem_proposta_pct": round(margem * 100, 2),
                "decisao": decisao,
                "preco_a_cadastrar": round(preco_final, 2),
                "margem_final_pct": round(margem_final * 100, 2),
                "lucro_rs": round(_l_final, 2),
                "lucro_sem_afundar": round(lucro_sem_afundar, 2),
                "custo": custo, "frete": round(frete, 2),
                "rebate": round(rebate, 2),
                "taxa_ml_pct": round(taxa_pct * 100, 2),
                "taxa_mais_imposto_pct": round(pct_total * 100, 2),
                "imposto_pct": round(imposto * 100, 2),
                "faixa_do_ml": str(faixa_de_preco(p) or ""),
                # O preço que REALMENTE vale hoje neste anúncio, e a margem
                # nele. É esta margem que diz se a venda dá lucro — não a da
                # promoção que cadastramos.
                "observacao_ativa": "",
                "ativa_mais_barata": preco_ativo if preco_ativo is not None else "",
                "tipo_da_ativa": (promo_ativa.get("type") or "") if promo_ativa else "",
                "margem_da_ativa_pct": (
                    round(avaliar(preco_ativo, custo, frete, taxa_fixa, pct_total,
                                  rebate_da_promocao(promo_ativa))[1] * 100, 2)
                    if preco_ativo is not None else ""),
                "resultado": "",
            })

        # A ATIVA DOMINA quando entrega preço menor ou igual E dinheiro maior
        # ou igual do que a candidata. Aí entrar não compra nada: o comprador
        # não paga menos e o vendedor não recebe mais — e ainda corre o risco
        # de a venda ser creditada na campanha pior.
        #
        # O caso que ensinou isto foi o #7191463116 em 02/09/2026: entramos
        # numa PRICE_DISCOUNT a R$ 964,17 enquanto uma SMART, no MESMO preço,
        # rendia 13,7% contra 9,8% — porque a SMART vem com rebate do ML.
        # Quatro pontos de margem entregues à toa, sem o comprador ganhar nada.
        for linha in linhas_do_item:
            if not linha["decisao"].startswith("ENTRAR"):
                continue
            pl = round(linha["preco_a_cadastrar"], 2)
            ll = round(linha["lucro_rs"], 2)
            dom = [a for a in ativas_avaliadas
                   if a[0] <= pl + 0.02 and round(a[1], 2) >= ll - 0.02
                   and not (abs(a[0] - pl) < 0.02
                            and (a[2].get("type") or "") == linha["tipo"])]
            if dom:
                melhor_a = max(dom, key=lambda a: (round(a[1], 2), -a[0]))
                linha["decisao"] = "RECUSAR (ativa domina)"
                linha["observacao_ativa"] = (
                    f"{melhor_a[2].get('type')} R$ {melhor_a[0]:.2f} "
                    f"deixa R$ {melhor_a[1]:.2f}")

        plano += escolher(linhas_do_item, todas)
    print()

    if aplicar:
        for linha in plano:
            if not linha["decisao"].startswith("ENTRAR"):
                linha["resultado"] = "não enviado"
                continue
            ini_pd, fim_pd = (janela_price_discount()
                              if linha["tipo"] == "PRICE_DISCOUNT"
                              else (None, None))
            status, corpo = cli.aderir_promocao(
                linha["item_id"], linha["promocao_id"], linha["tipo"],
                linha["preco_a_cadastrar"],
                offer_id=linha.get("ref_id") or None,
                inicio=ini_pd, fim=fim_pd)
            ok = 200 <= status < 300

            # ERROR_CREDIBILITY_DISCOUNTED_PRICE não é sobre custo — é o ML
            # achando o desconto fundo demais pra ser crível. A única saída
            # é um preço mais raso (mais perto do original), e quem sabe até
            # onde é raso o bastante é a própria API: max_discounted_price da
            # MESMA campanha, relido na hora, porque a faixa muda ao longo do
            # dia. Só reoferece se isso ainda cobrir o piso pedido.
            if not ok and "CREDIBILITY" in str(corpo):
                props_novas = cli.promocoes_do_item(linha["item_id"]) or []
                cand = next((p for p in props_novas
                            if p.get("type") == linha["tipo"]), None)
                faixa_nova = faixa_de_preco(cand) if cand else None
                if faixa_nova:
                    _, mais_raso = faixa_nova
                    pct_total = linha["taxa_ml_pct"] / 100 + linha["imposto_pct"] / 100
                    _, margem_rasa = avaliar(mais_raso, linha["custo"], linha["frete"],
                                             0.0, pct_total, linha["rebate"])
                    if margem_rasa * 100 >= piso * 100 - 0.05 and mais_raso > linha["preco_a_cadastrar"]:
                        status2, corpo2 = cli.aderir_promocao(
                            linha["item_id"], linha["promocao_id"], linha["tipo"],
                            round(mais_raso, 2),
                            offer_id=linha.get("ref_id") or None,
                            inicio=ini_pd, fim=fim_pd)
                        if 200 <= status2 < 300:
                            linha["preco_a_cadastrar"] = round(mais_raso, 2)
                            linha["margem_final_pct"] = round(margem_rasa * 100, 2)
                            linha["lucro_rs"] = round(
                                avaliar(mais_raso, linha["custo"], linha["frete"], 0.0,
                                       pct_total, linha["rebate"])[0], 2)
                            status, corpo, ok = status2, corpo2, True
                            linha["decisao"] += " (raso)"
                        else:
                            corpo = f"raso também recusado: {corpo2}"

            linha["resultado"] = "OK" if ok else f"ERRO {status}: {str(corpo)[:180]}"
            cor = VERDE if ok else VERM
            print(f"  {cor}{linha['resultado'][:60]:60s}{FIM} {linha['sku']:28s} "
                  f"R$ {linha['preco_a_cadastrar']:>9.2f}  {linha['nome'][:30]}")
            time.sleep(0.4)

    # O nome leva hora e escopo porque a versão anterior usava só a data: uma
    # rodada de teste com --limite 10 sobrescrevia o plano da conta inteira que
    # tinha acabado de levar oito minutos para sair.
    escopo = f"limite{limite}" if limite else ("aplicado" if aplicar else "simulacao")
    carimbo = agora_iso()[:16].replace(":", "").replace("-", "").replace("T", "-")
    saida = RAIZ / "relatorios" / f"promos-{slug}-{carimbo}-{escopo}.csv"
    saida.parent.mkdir(exist_ok=True)
    if plano:
        with saida.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(plano[0].keys()), delimiter=";")
            w.writeheader()
            w.writerows(plano)

    entrar = [l for l in plano if l["decisao"].startswith("ENTRAR")]
    fundo = [l for l in plano if l["decisao"] == "ENTRAR (afundado)"]
    recusar = [l for l in plano if l["decisao"] == "RECUSAR"]
    prejuizo = [l for l in recusar if l["margem_proposta_pct"] < 0]

    print(f"\n{'─' * 68}")
    print(f"  propostas analisadas   {len(plano)}")
    print(f"  {VERDE}entrar                 {len(entrar)}{FIM}"
          f"   (destas, {len(fundo)} com preço afundado até o teto)")
    alternativas = [l for l in plano if l["decisao"] == "ALTERNATIVA"]
    print(f"  {CINZA}alternativas descartadas {len(alternativas)}{FIM}"
          f"   (mesma anúncio, campanha que rende menos)")
    dominadas = [l for l in plano if l["decisao"] == "RECUSAR (ativa domina)"]
    if dominadas:
        print(f"  {VERDE}ativa já domina          {len(dominadas)}{FIM}"
              f"   (mesmo preço ou menor, e rende mais — entrar não compraria nada)")
    print(f"  {AMAR}recusar (abaixo do piso) {len(recusar) - len(prejuizo)}{FIM}")
    print(f"  {VERM}recusar (prejuízo)       {len(prejuizo)}{FIM}")
    print(f"  {CINZA}sem custo na tabela      {len(sem_custo)} anúncios{FIM}")
    print(f"  {CINZA}sem frete apurado        {len(sem_frete)} anúncios{FIM}")
    print(f"  {AMAR}custo em conflito        {len(conflitados)} anúncios{FIM}"
          f"   (duas fontes discordam — decidir antes)")
    print(f"{'─' * 68}")
    if fundo:
        perdido = sum(l["lucro_sem_afundar"] - l["lucro_rs"] for l in fundo)
        print(f"  {AMAR}O teto de {teto:.0%} abre mão de {reais(perdido)} por rodada"
              f" de vendas{FIM}")
        print(f"  {CINZA}(é o preço de descer {len(fundo)} anúncios até o teto para ganhar"
              f" vitrine; sem afundar, os mesmos {len(fundo)} rendem mais por venda){FIM}")
    if plano:
        print(f"  planilha: {saida}")
    # O aviso que faltava em 02/09/2026: a trava de margem protege a promoção
    # que este script cadastra, mas quem define o preço COBRADO é a promoção
    # ativa mais barata do anúncio. Quando ela fura o piso, o anúncio vende
    # magro (ou no prejuízo) por mais correta que esteja a nossa adesão. Aqui
    # não adianta cadastrar: resolver é decidir SAIR de uma promoção.
    # Sem filtrar por decisão: vender magro é propriedade do ANÚNCIO, não da
    # nossa escolha. Um anúncio que recusamos por prejuízo pode estar vendendo
    # abaixo do piso por uma promoção que já estava ativa — e esse é dos casos
    # que mais importam. A primeira versão deste aviso só olhava as linhas
    # ENTRAR e engolia três anúncios abaixo do piso na conta da FACILITA.
    vistos: dict[str, dict] = {}
    for linha in plano:
        m = linha.get("margem_da_ativa_pct")
        if m == "" or m is None:
            continue
        if float(m) < piso * 100 and linha["item_id"] not in vistos:
            vistos[linha["item_id"]] = linha
    if vistos:
        prej = [x for x in vistos.values() if float(x["margem_da_ativa_pct"]) < 0]
        aviso = f"A promoção ATIVA mais barata fura o piso em {len(vistos)} anúncios"
        if prej:
            aviso += f", {len(prej)} no PREJUÍZO"
        print(f"\n{VERM}{aviso}:{FIM}")
        print(f"  {CINZA}Cadastrar não resolve: quem manda no preço cobrado é a "
              f"mais barata. Resolver aqui é decidir SAIR dela.{FIM}")
        for x in sorted(vistos.values(), key=lambda y: float(y["margem_da_ativa_pct"])):
            cor = VERM if float(x["margem_da_ativa_pct"]) < 0 else AMAR
            print(f"  {cor}{float(x['margem_da_ativa_pct']):6.1f}%{FIM} "
                  f"{x['item_id']:16s} {x['sku'][:24]:24s} "
                  f"{x['tipo_da_ativa']:16s} R$ {float(x['ativa_mais_barata']):>9.2f}")
    if trocas:
        trocas.sort(key=lambda x: -x["ganho"])
        soma = sum(x["ganho"] for x in trocas)
        print(f"\n{VERDE}Troca sem custo para o comprador em {len(trocas)} anúncios "
              f"— {reais(soma)} por rodada de vendas:{FIM}")
        print(f"  {CINZA}Duas promoções ATIVAS no mesmo preço, uma rendendo mais que a "
              f"outra (rebate do ML). Sair da pior não muda um centavo para quem "
              f"compra.{FIM}")
        for x in trocas[:40]:
            print(f"  {VERDE}+{x['ganho']:>8.2f}{FIM} {x['item_id']:16s} "
                  f"{x['sku'][:24]:24s} R$ {x['preco']:>9.2f}  "
                  f"sair de {x['sair_de']:16s} (R$ {x['sair_lucro']:.2f}) "
                  f"e ficar com {x['fica']} (R$ {x['fica_lucro']:.2f})")
        print(f"  {CINZA}Só enxerga anúncios com alguma proposta candidata — os que "
              f"já estão totalmente aderidos não passam por aqui.{FIM}")
    if sem_custo:
        print(f"\n{AMAR}Sem custo — ficaram de fora, confirme o produto de cada um:{FIM}")
        for s in sem_custo[:40]:
            print(f"  {s['item_id']:16s} {s['sku']:26s} {s['titulo']}")
    if divergencias:
        pior = max(divergencias, key=lambda d: d["por_venda"])
        soma = sum(d["por_venda"] for d in divergencias)
        print(f"\n{AMAR}Taxa: em {len(divergencias)} anúncios o ML cobra diferente "
              f"do 11,5%/16% da casa.{FIM}")
        print(f"{CINZA}  Somando, são {reais(soma)} por rodada de vendas de diferença.{FIM}")
        print(f"{CINZA}  Pior caso: {pior['sku']} ({pior['tipo']}) — a casa usa "
              f"{pior['fixa_pct']:.1f}%, o ML cobra {pior['medida_pct']:.1f}%, "
              f"{reais(pior['por_venda'])} por venda.{FIM}")
        acima = [d for d in divergencias if d["medida_pct"] > d["fixa_pct"]]
        print(f"{CINZA}  Em {len(acima)} o ML cobra MAIS que a casa supõe (margem real menor"
              f" que a calculada) e em {len(divergencias) - len(acima)} cobra MENOS.{FIM}")
        print(f"{CINZA}  Rodando com --taxa-casa; sem essa flag o cálculo usa a "
              f"taxa real de cada anúncio.{FIM}")
    if conflitados:
        print(f"\n{AMAR}Custo em conflito — pulados até alguém decidir a fonte:{FIM}")
        for c in conflitados[:40]:
            print(f"  {c['item_id']:16s} {c['sku']:28s} {c['titulo']}")
    if sem_frete:
        print(f"\n{AMAR}Sem custo de frete pela API — pulados de propósito"
              f" (frete zero inventado vira promoção no prejuízo):{FIM}")
        for f in sem_frete[:20]:
            print(f"  {f['item_id']:16s} {f['sku']:26s} {f['titulo']}")
    if not aplicar and entrar:
        print(f"\n{CINZA}Nada foi escrito no Mercado Livre. Para valer:"
              f" --aplicar{FIM}")
    return 0


def main() -> int:
    # O console do Windows abre em cp1252; sem isto os separadores ─ e o
    # texto acentuado no resumo final derrubam a rodada inteira depois de
    # minutos varrendo a conta, com o CSV já salvo e o traceback escondendo
    # o resultado.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug")
    p.add_argument("--conferir", metavar="ITEM_ID",
                   help="mostra o que a API responde para um anúncio e para")
    p.add_argument("--aplicar", action="store_true",
                   help="faz a adesão de verdade (sem isto, é simulação)")
    p.add_argument("--piso", type=float, default=10.0,
                   help="margem líquida mínima %% (padrão 10, pedido do Matheus "
                        "em 02/09/2026; antes era 8)")
    p.add_argument("--teto", type=float, default=15.0, help="margem máxima %% (padrão 15)")
    p.add_argument("--imposto", type=float, default=None,
                   help="força a alíquota %% em vez da coluna do custos.csv")
    p.add_argument("--taxa-casa", action="store_true", dest="taxa_casa",
                   help="usa o 11,5%% Clássico / 16%% Premium da planilha em vez "
                        "da taxa que o ML cobra em cada anúncio (padrão)")
    p.add_argument("--sem-rebate", action="store_true", dest="sem_rebate",
                   help="ignora o rebate do ML (conta mais conservadora: a "
                        "margem sai menor que a real nas campanhas com redução "
                        "de tarifa)")
    p.add_argument("--todas", action="store_true",
                   help="entra em TODAS as campanhas liberadas do anúncio, não "
                        "só na que deixa mais dinheiro por venda")
    p.add_argument("--limite", type=int, default=None,
                   help="olha só os N primeiros anúncios (para testar)")
    a = p.parse_args()

    if a.conferir:
        conta = obter_conta(a.slug)
        return conferir(MLClient(a.slug, getattr(conta, "user_id", None)), a.conferir)

    if a.piso >= a.teto:
        print(f"{VERM}O piso tem que ser menor que o teto.{FIM}")
        return 1
    return rodar(a.slug, a.piso / 100.0, a.teto / 100.0, a.aplicar,
                 (a.imposto / 100.0) if a.imposto is not None else None,
                 a.limite, a.todas, a.sem_rebate, a.taxa_casa)


if __name__ == "__main__":
    raise SystemExit(main())
