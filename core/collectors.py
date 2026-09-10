"""
Coletores: transformam o estado atual do Mercado Livre em snapshots no banco.

Cada função recebe uma Conta (do registro) e um MLClient já travado naquela
conta. Nenhum coletor decide sozinho em que conta opera.
"""
from __future__ import annotations

import re
import sqlite3

from . import db
from .config import Conta
from .ml_api import MLClient, sku_do_item
from .utils import agora_iso, preco_real


# ----------------------------------------------------------------------
# 1. Meus anúncios: preço, estoque, vendas, saúde
# ----------------------------------------------------------------------
def _link_da_ficha(cli: MLClient, product_id: str) -> str | None:
    """
    Endereço da ficha de catálogo, ou nada.

    Nunca monta endereço de anúncio a partir do ID: o formato exige hífen e
    apelido do produto, e o palpite direto leva a "esta página não existe" —
    foi o link quebrado que o bot chegou a mandar.
    """
    try:
        return cli.link_do_produto(product_id)
    except Exception:
        return None


def _fila_de_fretes(con: sqlite3.Connection, conta: Conta, itens: list[dict],
                    quantos: int) -> set[str]:
    """
    Escolhe QUAIS anúncios têm o frete medido nesta rodada.

    Medir os 41 a cada 5 minutos seria 41 chamadas por ciclo; medir uma vez
    por dia era pouco demais, porque o Mercado Livre mexe na tabela de frete a
    toda hora. A saída é um rodízio: alguns por rodada, girando, de modo que
    todos passem dentro de meia hora.

    A fila é ordenada por quem dói mais: anúncio com FRETE GRÁTIS primeiro,
    porque nele o reajuste sai direto da margem do vendedor; entre eles, os
    que mais vendem. O cursor fica gravado no banco e sobrevive a reinício —
    sem isso o rodízio recomeçaria do zero toda vez que o vigia subisse, e os
    últimos da lista nunca seriam medidos.
    """
    if quantos <= 0:
        return set()

    candidatos = [it for it in itens if it.get("status") == "active"]
    if not candidatos:
        return set()
    candidatos.sort(key=lambda it: (
        0 if (it.get("shipping") or {}).get("free_shipping") else 1,
        -int(it.get("sold_quantity") or 0),
        str(it.get("id")),
    ))
    ids = [str(it.get("id")) for it in candidatos]
    if quantos >= len(ids):
        return set(ids)

    chave = f"frete_cursor_{conta.slug}"
    ultimo = db.ler_marcador(con, chave)
    inicio = (ids.index(ultimo) + 1) if ultimo in ids else 0
    escolhidos = [ids[(inicio + i) % len(ids)] for i in range(quantos)]
    db.gravar_marcador(con, chave, escolhidos[-1])
    return set(escolhidos)


def coletar_meus_anuncios(con: sqlite3.Connection, conta: Conta, cli: MLClient, carimbo: str,
                          com_visitas: bool = True, cep: str = "01001000",
                          max_fretes: int = 80) -> int:
    """
    com_visitas=True marca a passada LARGA do dia: além das visitas, é quando
    medimos o custo do frete dos seus próprios anúncios.

    Por que medir o nosso: o Mercado Livre reajusta a tabela de frete sem
    avisar ninguém. Quando isso acontece num anúncio com frete grátis, nada
    visível muda — a etiqueta continua "frete grátis", o modo de envio
    continua o mesmo — e a diferença sai inteira da margem do vendedor. Sem
    medir o valor, esse é um custo que sobe em silêncio.

    Fica só na passada diária porque é uma chamada por anúncio: no ciclo de
    5 minutos seria desperdício, já que tabela de frete não muda de minuto
    em minuto.
    """
    ids = cli.ids_dos_meus_anuncios()
    itens = cli.detalhes_dos_itens(ids)

    # Na passada larga do dia, todo mundo; nas rodadas curtas, o rodízio.
    na_fila = (set(str(it.get("id")) for it in itens) if com_visitas
               else _fila_de_fretes(con, conta, itens, max_fretes))

    linhas = []
    for it in itens:
        envio = it.get("shipping") or {}
        visitas = None
        frete_custo = None
        frete_lista = None
        frete_origem = None
        preco_vitrine = None

        if str(it.get("id")) in na_fila and it.get("status") == "active":
            try:
                # 'custo' é o que o comprador paga: em frete grátis vem 0 e não
                # diz nada sobre margem. 'custo_lista' é o valor cheio da mesma
                # opção — a medida do que sai do bolso de quem vende.
                medida = cli.frete_do_item(it["id"], cep) or {}
                frete_custo = medida.get("custo")
                frete_lista = medida.get("custo_lista")
                if isinstance(frete_lista, (int, float)):
                    frete_origem = "opcao_do_item"
            except Exception:
                frete_custo = None
                frete_lista = None

            # Segundo caminho, para quem o primeiro não alcança. Anúncio em
            # `not_specified` não tem opção de envio no ML, então
            # /items/.../shipping_options devolve nada e o frete ficava NULO —
            # e frete nulo entra no piso como ZERO, que é o erro mais caro que
            # existe aqui. Medido em 03/09/2026 na Decoralli: 80 anúncios
            # nessa situação, mediana de R$ 224,90, faixa R$ 53,90 a R$ 498,90.
            #
            # O número é uma COTAÇÃO — o que o ML cobraria por aquele
            # despacho — e não o que a loja paga entregando por fora, que só o
            # cliente sabe. Por isso vai carimbado em frete_origem: é melhor
            # estimativa que zero, e não pode ser confundido com medição.
            if not isinstance(frete_lista, (int, float)) and (envio.get("free_shipping")):
                try:
                    cotado = cli.custo_do_frete_gratis(it["id"])
                    if isinstance(cotado, (int, float)):
                        frete_lista = cotado
                        frete_origem = "cotacao_frete_gratis"
                except Exception:
                    pass

        if com_visitas and it.get("status") == "active":
            try:
                visitas = cli.visitas(it["id"], dias=7)
            except Exception:
                visitas = None
            # Preço da vitrine junto, na mesma passada: o campo `price` do item
            # ignora campanha promocional, e comparar preço de tabela com preço
            # real de concorrente produz conclusão invertida.
            try:
                preco_vitrine = cli.preco_de_vitrine(it["id"])
            except Exception:
                preco_vitrine = None

        linhas.append(
            {
                "coletado_em": carimbo,
                "cliente_id": conta.cliente_id,
                "conta_slug": conta.slug,
                "item_id": it.get("id"),
                "sku": sku_do_item(it),
                "titulo": it.get("title"),
                "preco": it.get("price"),
                "preco_original": it.get("original_price"),
                "estoque": it.get("available_quantity"),
                "vendidos": it.get("sold_quantity"),
                "status": it.get("status"),
                "sub_status": ",".join(it.get("sub_status") or []),
                "tipo_anuncio": it.get("listing_type_id"),
                "catalogo": int(bool(it.get("catalog_listing"))),
                "produto_catalogo": it.get("catalog_product_id"),
                "categoria": it.get("category_id"),
                "saude": it.get("health"),
                "frete_gratis": int(bool(envio.get("free_shipping"))),
                "visitas_7d": visitas,
                "permalink": it.get("permalink"),
                "thumbnail": it.get("thumbnail"),
                "descontos": ",".join(it.get("deal_ids") or []),
                "envio_modo": envio.get("logistic_type") or envio.get("mode"),
                "frete_custo": frete_custo,
                "frete_lista": frete_lista,
                "frete_origem": frete_origem,
                "preco_vitrine": preco_vitrine,
            }
        )

    return db.inserir_muitos(con, "snap_anuncio", linhas)


# ----------------------------------------------------------------------
# 2. Destaques da categoria — quem mais vende, e onde EU estou nessa lista
#
# Substitui a antiga busca por palavra-chave, que o ML bloqueou. Em troca de
# não saber a posição num termo específico, ganhamos algo que o termo não dava:
# a lista real de mais vendidos da categoria, que descobre concorrente novo
# sozinho, sem você precisar listar ninguém.
# ----------------------------------------------------------------------
def coletar_destaques(con: sqlite3.Connection, conta: Conta, cli: MLClient,
                      carimbo: str) -> tuple[int, int]:
    """
    Os destaques vêm em dois formatos e isso importa:

      type: ITEM     -> um anúncio específico. Basta buscar os detalhes.
      type: PRODUCT  -> um produto de CATÁLOGO. O id não é de anúncio; para
                        saber quem vende e por quanto é preciso pedir as
                        ofertas daquele produto.

    Em categoria dominada por catálogo — que é o caso de boa parte do que o
    Ênio vende — quase tudo volta como PRODUCT. Ignorar esse tipo era o que
    fazia a coleta devolver zero.
    """
    categorias = conta.parametros.get("categorias_monitoradas") or []
    if not categorias:
        categorias = [
            l["categoria"] for l in con.execute(
                "SELECT categoria, COUNT(*) n FROM snap_anuncio "
                "WHERE conta_slug = ? AND coletado_em = ? AND categoria IS NOT NULL "
                "GROUP BY categoria ORDER BY n DESC LIMIT 8",
                (conta.slug, carimbo),
            )
        ]

    meus_ids = {
        l["item_id"] for l in con.execute(
            "SELECT item_id FROM snap_anuncio WHERE conta_slug = ? AND coletado_em = ?",
            (conta.slug, carimbo),
        )
    }

    linhas_conc, linhas_pos = [], []
    apelidos: dict[str, str] = {}
    resumo = {"categorias": 0, "itens": 0, "produtos": 0, "vazias": 0}

    def apelido(seller_id: str) -> str:
        if seller_id and seller_id not in apelidos:
            try:
                apelidos[seller_id] = cli.apelido_do_vendedor(seller_id) or seller_id
            except Exception:
                apelidos[seller_id] = seller_id
        return apelidos.get(seller_id, seller_id)

    def registrar(item_id, titulo, preco, vendidos, seller_id, frete, pos,
                  categoria, eh_catalogo, permalink):
        if seller_id == cli.user_id or item_id in meus_ids:
            linhas_pos.append({
                "coletado_em": carimbo, "cliente_id": conta.cliente_id,
                "conta_slug": conta.slug, "termo": f"top:{categoria}",
                "item_id": item_id, "posicao": pos, "preco": preco,
                "preco_topo": None, "total_result": None,
            })
        else:
            linhas_conc.append({
                "coletado_em": carimbo, "cliente_id": conta.cliente_id,
                "conta_slug": conta.slug, "origem": "destaques",
                "referencia": categoria, "item_id": item_id, "titulo": titulo,
                "preco": preco, "vendidos": vendidos, "seller_id": seller_id,
                "seller_nickname": apelido(seller_id),
                "frete_gratis": int(bool(frete)), "posicao": pos,
                "catalogo": int(bool(eh_catalogo)), "permalink": permalink,
            })

    for categoria in categorias:
        try:
            destaques = cli.destaques_da_categoria(categoria, site_id=conta.site_id)
        except Exception:
            continue
        resumo["categorias"] += 1
        if not destaques:
            resumo["vazias"] += 1
            continue

        posicao_por_id, ids_itens, ids_produtos = {}, [], []
        for i, d in enumerate(destaques):
            ident = d.get("id")
            if not ident:
                continue
            posicao_por_id[ident] = d.get("position", i + 1)
            if (d.get("type") or "ITEM").upper() == "PRODUCT":
                ids_produtos.append(ident)
            else:
                ids_itens.append(ident)

        # ---- destaques que são anúncios ----
        if ids_itens:
            resumo["itens"] += len(ids_itens)
            for it in cli.detalhes_dos_itens(ids_itens[:50]):
                envio = it.get("shipping") or {}
                registrar(it.get("id"), it.get("title"), it.get("price"),
                          it.get("sold_quantity"), str(it.get("seller_id") or ""),
                          envio.get("free_shipping"), posicao_por_id.get(it.get("id")),
                          categoria, it.get("catalog_listing"), it.get("permalink"))

        # ---- destaques que são produtos de catálogo ----
        for product_id in ids_produtos[:20]:
            resumo["produtos"] += 1
            try:
                ofertas = cli.vendedores_do_produto(product_id, limite=10)
            except Exception:
                continue
            nome = None
            try:
                nome = (cli.produto_do_catalogo(product_id) or {}).get("name")
            except Exception:
                pass

            pos_destaque = posicao_por_id.get(product_id)
            for ordem, oferta in enumerate(ofertas, start=1):
                envio = oferta.get("shipping") or {}
                titulo = nome or oferta.get("title")
                # a posição no destaque é do produto; guardamos junto a ordem
                # da oferta, porque o 1º da lista é quem está com o buy box
                rotulo = f"{titulo} (oferta {ordem})" if ordem > 1 else titulo
                registrar(oferta.get("item_id"), rotulo, oferta.get("price"),
                          oferta.get("sold_quantity"), str(oferta.get("seller_id") or ""),
                          envio.get("free_shipping"), pos_destaque, categoria, True,
                          oferta.get("permalink") or _link_da_ficha(cli, product_id))

    # preço do 1º colocado de cada categoria, para comparar
    melhor_por_categoria: dict[str, float] = {}
    for c in linhas_conc:
        if c["posicao"] == 1 and c["preco"]:
            melhor_por_categoria.setdefault(c["referencia"], c["preco"])
    for linha in linhas_pos:
        linha["preco_topo"] = melhor_por_categoria.get(linha["termo"].removeprefix("top:"))

    n1 = db.inserir_muitos(con, "snap_concorrente", linhas_conc)
    n2 = db.inserir_muitos(con, "snap_posicao", linhas_pos)
    coletar_destaques.ultimo_resumo = resumo
    return n1, n2


# ----------------------------------------------------------------------
# 3a. Catálogo por termo — todos os vendedores de um produto
#
# Este é o dado de concorrência mais limpo que existe no ML: mesmo produto,
# mesma ficha, só muda quem vende e por quanto. Vale ouro para a linha de
# móveis; para produto sob medida (toldo) o catálogo costuma ser raso.
# ----------------------------------------------------------------------
def coletar_catalogo(con: sqlite3.Connection, conta: Conta, cli: MLClient,
                     carimbo: str) -> int:
    linhas = []
    apelidos: dict[str, str] = {}

    for entrada in conta.palavras_chave:
        termo = entrada["termo"] if isinstance(entrada, dict) else str(entrada)
        if termo.lower().startswith("ajustar"):
            continue
        max_produtos = int(entrada.get("max_produtos", 3)) if isinstance(entrada, dict) else 3

        try:
            produtos = cli.buscar_no_catalogo(termo, site_id=conta.site_id, limite=max_produtos)
        except Exception:
            continue

        for produto in produtos[:max_produtos]:
            product_id = produto.get("id")
            if not product_id:
                continue
            try:
                ofertas = cli.vendedores_do_produto(product_id, limite=20)
            except Exception:
                continue

            for pos, oferta in enumerate(ofertas, start=1):
                seller_id = str(oferta.get("seller_id") or "")
                if seller_id == cli.user_id:
                    continue
                if seller_id and seller_id not in apelidos:
                    try:
                        apelidos[seller_id] = cli.apelido_do_vendedor(seller_id) or seller_id
                    except Exception:
                        apelidos[seller_id] = seller_id
                envio = oferta.get("shipping") or {}
                linhas.append({
                    "coletado_em": carimbo, "cliente_id": conta.cliente_id,
                    "conta_slug": conta.slug, "origem": "catalogo",
                    "referencia": termo, "item_id": oferta.get("item_id"),
                    "titulo": produto.get("name") or oferta.get("title"),
                    "preco": oferta.get("price"),
                    "vendidos": oferta.get("sold_quantity"),
                    "seller_id": seller_id,
                    "seller_nickname": apelidos.get(seller_id),
                    "frete_gratis": int(bool(envio.get("free_shipping"))),
                    "posicao": pos, "catalogo": 1,
                    "permalink": oferta.get("permalink") or _link_da_ficha(cli, product_id),
                })

    return db.inserir_muitos(con, "snap_concorrente", linhas)


# ----------------------------------------------------------------------
# 3b. (removido) Concorrentes vigiados por ID de anúncio
#
# Havia aqui um coletor que lia o anúncio do concorrente pelo ID dele. Ele
# morreu: o Mercado Livre passou a devolver `access_denied` (403) para
# QUALQUER leitura de item de terceiro, tanto em /items/{id} quanto no
# multiget /items?ids=. Confirmado com controle — até um anúncio que o
# sistema lê sem problema pela ficha de catálogo é recusado quando pedido
# pelo ID.
#
# O acompanhamento de concorrente vive inteiro em core/vigilancia.py, que
# observa PRODUTOS DE CATÁLOGO (/products/{id}/items). Aquele módulo também
# cobre o que este coletor fazia com as fichas de concorrentes.yaml, por isso
# o antigo `coletar_produtos_vigiados` saiu junto: eram duas leituras da mesma
# coisa, gastando o dobro de chamadas de API por rodada.
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# 4. Saúde da conta
# ----------------------------------------------------------------------
def coletar_saude_da_conta(con: sqlite3.Connection, conta: Conta, cli: MLClient, carimbo: str) -> None:
    rep = cli.reputacao()

    contagem = dict(
        con.execute(
            "SELECT status, COUNT(*) FROM snap_anuncio WHERE conta_slug = ? AND coletado_em = ? GROUP BY status",
            (conta.slug, carimbo),
        ).fetchall()
    )

    # Os pedidos do dia saem da MESMA busca dos 7 dias, filtrando por data.
    # Uma chamada de API, duas respostas: "quanto vendeu hoje" é a pergunta
    # que o operador faz de verdade, e "em 7 dias" é o pano de fundo dela.
    from datetime import datetime as _dt
    from .utils import TZ_BR as _TZ
    inicio_do_dia = _dt.now(_TZ).replace(hour=0, minute=0, second=0, microsecond=0)

    from datetime import timedelta as _td
    dias_janela = 7
    inicio_janela = (_dt.now(_TZ) - _td(days=dias_janela)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    janela = f"{inicio_janela:%d/%m}–{_dt.now(_TZ):%d/%m}"

    vendas_7d, receita_7d = 0, 0.0
    vendas_hoje, receita_hoje = 0, 0.0
    cancelados_7d, receita_cancelada = 0, 0.0
    try:
        for pedido in cli.vendas_recentes(dias=dias_janela):
            valor = 0.0
            quantas = 0
            for it in pedido.get("order_items", []):
                q = int(it.get("quantity", 0))
                quantas += q
                valor += float(it.get("unit_price", 0)) * q

            # Cancelado conta à parte, nunca junto. O painel do Mercado Livre
            # soma cancelado em "vendas brutas" e mostra o cancelamento numa
            # caixinha separada — foi daí que veio a diferença de R$ 890,99
            # entre os dois números em 26/08. Aqui a receita é a que entrou;
            # o cancelado aparece do lado, para a conferência fechar.
            if str(pedido.get("status")) in ("cancelled", "invalid"):
                cancelados_7d += quantas
                receita_cancelada += valor
                continue

            vendas_7d += quantas
            receita_7d += valor

            criado = str(pedido.get("date_created") or "")
            try:
                quando = _dt.fromisoformat(criado.replace("Z", "+00:00"))
                if quando.astimezone(_TZ) >= inicio_do_dia:
                    vendas_hoje += quantas
                    receita_hoje += valor
            except Exception:
                pass          # pedido sem data legível não entra no "hoje"
    except Exception:
        pass  # escopo de pedidos pode não estar liberado no app

    db.inserir(
        con,
        "snap_conta",
        {
            "coletado_em": carimbo,
            "cliente_id": conta.cliente_id,
            "conta_slug": conta.slug,
            "nickname": rep.get("nickname"),
            "nivel": rep.get("nivel"),
            "power_seller": rep.get("power_seller"),
            "transacoes": rep.get("transacoes"),
            "reclamacoes_pct": rep.get("reclamacoes_pct"),
            "cancelamentos_pct": rep.get("cancelamentos_pct"),
            "atrasos_pct": rep.get("atrasos_pct"),
            "anuncios_ativos": contagem.get("active", 0),
            "anuncios_pausados": contagem.get("paused", 0),
            "vendas_7d": vendas_7d,
            "receita_7d": receita_7d,
            "vendas_hoje": vendas_hoje,
            "receita_hoje": receita_hoje,
            "cancelados_7d": cancelados_7d,
            "receita_cancelada_7d": receita_cancelada,
            "janela_vendas": janela,
        },
    )


# ----------------------------------------------------------------------
# 5. Buy box do catálogo
# ----------------------------------------------------------------------
def _dono_do_anuncio(con: sqlite3.Connection, item_id: str) -> tuple[str | None, str | None]:
    """
    De quem é este MLB: (conta_slug, apelido) se for de uma conta que operamos,
    (None, apelido) se for de terceiro conhecido, (None, None) se nunca visto.

    Existe porque /items/{id}/price_to_win identifica o vencedor SÓ pelo
    item_id — o campo `winner` traz {item_id, price} e mais nada. Ler
    `winner.seller_id` devolvia None em 100% dos casos (400 de 400 alertas
    conferidos em 03/09/2026), e sem o dono o alerta não sabe distinguir
    concorrente de conta irmã. O item resolve isso sem chute: ou o MLB está no
    nosso próprio snapshot, ou está no de concorrentes com o seller junto.
    """
    proprio = con.execute(
        "SELECT conta_slug FROM snap_anuncio WHERE item_id = ? "
        "ORDER BY coletado_em DESC LIMIT 1", (item_id,)).fetchone()
    if proprio:
        apelido = con.execute(
            "SELECT nickname FROM snap_conta WHERE conta_slug = ? "
            "ORDER BY coletado_em DESC LIMIT 1", (proprio["conta_slug"],)).fetchone()
        return proprio["conta_slug"], (apelido["nickname"] if apelido else None)

    alheio = con.execute(
        "SELECT seller_nickname FROM snap_concorrente WHERE item_id = ? "
        "AND seller_nickname IS NOT NULL ORDER BY coletado_em DESC LIMIT 1",
        (item_id,)).fetchone()
    return None, (alheio["seller_nickname"] if alheio else None)


def coletar_buy_box(con: sqlite3.Connection, conta: Conta, cli: MLClient, carimbo: str) -> list[dict]:
    """Retorna a situação de catálogo dos itens; o motor de regras usa isso."""
    itens_catalogo = con.execute(
        "SELECT item_id, titulo, preco, preco_vitrine FROM snap_anuncio "
        "WHERE conta_slug = ? AND coletado_em = ? AND catalogo = 1 AND status = 'active'",
        (conta.slug, carimbo),
    ).fetchall()

    # O preço que vale para comparar com o do vencedor é o da VITRINE. O de
    # cadastro ignora campanha, e o alerta então anuncia um corte que já foi
    # dado: em 03/09/2026 o "custo da buy box" saía a R$ 21.320 na FACILITA
    # contra R$ 7.978 reais, e a R$ 3.669 na Maxi contra R$ 628 — inflado em
    # 63% e 83%. Mesmo remédio de concorrente_cruzou_preco e do frete.
    vitrines = db.vitrines_recentes(con, conta.slug)

    situacao = []
    for it in itens_catalogo:
        try:
            dados = cli.preco_para_ganhar(it["item_id"]) or {}
        except Exception:
            continue
        vencedor = dados.get("winner") or {}
        vencedor_item = vencedor.get("item_id")
        dono_slug, dono_apelido = (
            _dono_do_anuncio(con, vencedor_item) if vencedor_item else (None, None))
        situacao.append(
            {
                "item_id": it["item_id"],
                "titulo": it["titulo"],
                "meu_preco": preco_real(it, vitrines),
                "status": dados.get("status"),                     # 'winning' | 'sharing_first_place' | 'competing' | 'listed'
                "preco_para_ganhar": dados.get("price_to_win"),
                "preco_vencedor": vencedor.get("price"),
                "vencedor_item": vencedor_item,
                "vencedor_slug": dono_slug,                        # preenchido = a vitrine é de uma conta NOSSA
                "vencedor_apelido": dono_apelido,
                "ficha": dados.get("catalog_product_id"),
            }
        )
    return situacao
