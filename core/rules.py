"""
Motor de regras: compara o snapshot novo com o anterior e gera alertas.

Toda regra tem a mesma forma: recebe (con, conta, carimbo_novo, carimbo_velho,
config_da_regra) e grava zero ou mais alertas. Ligar/desligar e calibrar
limiares é feito em config/alertas.yaml, sem tocar em código.
"""
from __future__ import annotations

import sqlite3

from . import db, humano
from .config import Conta, carregar_clientes, carregar_regras
from .utils import brl, pct, preco_real, truncar


def _reg(regras: dict, nome: str) -> dict | None:
    r = regras.get(nome) or {}
    return r if r.get("ativa", True) else None


def avaliar_mudancas_concorrentes(con: sqlite3.Connection, conta: Conta,
                                  carimbo_novo: str, novos: dict | None = None) -> int:
    """
    Só a regra 'concorrente mexeu'. Separada porque o vigia em tempo quase real
    roda isto sozinho, a cada poucos minutos, sem refazer a coleta dos seus
    próprios anúncios — que não muda de 5 em 5 minutos.
    """
    regras = carregar_regras()
    gerados = 0

    if novos is None:
        ultimo_meu = db.ultima_coleta(con, "snap_anuncio", conta.slug)
        novos = db.snapshot_por_item(con, "snap_anuncio", conta.slug, ultimo_meu) if ultimo_meu else {}

    def alerta(regra_nome, cfg, mensagem, item_id=None, titulo=None, dados=None):
        nonlocal gerados
        entrou = db.registrar_alerta(
            con, cliente_id=conta.cliente_id, conta_slug=conta.slug,
            regra=regra_nome, critico=bool(cfg.get("critico", False)),
            mensagem=mensagem, item_id=item_id, titulo=titulo, dados=dados,
        )
        if entrou:
            gerados += 1

    # ---------------- o concorrente mexeu no anúncio dele ----------------
    #
    # Aqui não comparamos com o SEU preço: comparamos o concorrente com ele
    # mesmo na rodada anterior. É o que responde "mexeram em alguma coisa?"
    # em vez de "quem está mais barato?", e é o que precisa chegar na hora.
    if (cfg := _reg(regras, "concorrente_mexeu")):
        anterior_vig = db.ultima_coleta(con, "snap_concorrente", conta.slug,
                                        antes_de=carimbo_novo)
        if anterior_vig:
            antes = {
                l["item_id"]: l for l in con.execute(
                    "SELECT * FROM snap_concorrente WHERE conta_slug = ? "
                    "AND coletado_em = ? AND origem = 'vigilancia'",
                    (conta.slug, anterior_vig),
                )
            }
            agora_ = con.execute(
                "SELECT * FROM snap_concorrente WHERE conta_slug = ? "
                "AND coletado_em = ? AND origem = 'vigilancia'",
                (conta.slug, carimbo_novo),
            ).fetchall()

            min_preco = float(cfg.get("variacao_minima_percentual", 2.0))
            avisar_estoque = bool(cfg.get("avisar_estoque", True))
            avisar_frete = bool(cfg.get("avisar_frete", True))
            juntar_a_partir_de = int(cfg.get("agrupar_a_partir_de", 4))

            # Os eventos são guardados antes de virar alerta. O motivo é
            # concreto: um concorrente grande reajusta a tabela inteira de uma
            # vez, e sem agrupar isso chega como vinte mensagens iguais no
            # celular. Vinte mensagens iguais ensinam a ignorar o alerta.
            eventos: list[dict] = []

            def anotar(tipo, texto, atual, dados=None, peso=0.0):
                eventos.append({
                    "tipo": tipo, "quem": atual["seller_nickname"] or "concorrente",
                    "texto": texto, "item_id": atual["comparar_com"],
                    "titulo": atual["titulo"], "dados": dados or {}, "peso": peso,
                })

            for atual in agora_:
                velho = antes.get(atual["item_id"])
                if not velho:
                    continue

                quem = atual["seller_nickname"] or "concorrente"
                onde = truncar(atual["titulo"], 40)
                meu = novos.get(atual["comparar_com"]) if atual["comparar_com"] else None
                meu_preco = preco_real(meu) if meu else None
                contexto = ""
                if meu_preco and atual["preco"]:
                    d = pct(atual["preco"], meu_preco)
                    if d is not None:
                        contexto = (f" — {'abaixo' if d < 0 else 'acima'} do seu "
                                    f"{brl(meu_preco)} em {abs(d):.1f}%")

                # ---- preço ----
                variacao = pct(atual["preco"], velho["preco"])
                if variacao is not None and abs(variacao) >= min_preco:
                    direcao = "subiu" if variacao > 0 else "BAIXOU"
                    anotar("preco",
                           f"{quem} {direcao} o preço {abs(variacao):.1f}% "
                           f"({brl(velho['preco'])} → {brl(atual['preco'])}) "
                           f"em {onde}{contexto}",
                           atual,
                           {"permalink_dele": atual["permalink"], "item_dele": atual["item_id"],
                            "de": velho["preco"], "para": atual["preco"]},
                           peso=abs(variacao))

                # ---- frete ----
                if avisar_frete:
                    if velho["frete_gratis"] is not None and \
                       bool(velho["frete_gratis"]) != bool(atual["frete_gratis"]):
                        # Frete é preço disfarçado: o valor do produto não se
                        # mexe, mas o que o comprador paga no fim, sim. Dizer
                        # só "mudou o frete" esconde a jogada.
                        if atual["frete_gratis"]:
                            texto = (f"{quem} passou a dar FRETE GRÁTIS em {onde}. "
                                     f"Na prática ele ficou mais barato sem baixar "
                                     f"o preço{contexto}.")
                        else:
                            custo = atual["frete_custo"]
                            quanto = (f" — o comprador dele agora paga {brl(custo)} "
                                      f"a mais no fechamento" if custo else "")
                            texto = (f"{quem} TIROU o frete grátis de {onde}{quanto}. "
                                     f"Na prática ele ficou mais caro sem subir o preço.")
                        anotar("frete", texto, atual, {"permalink_dele": atual["permalink"]})
                    elif velho["frete_custo"] is not None and atual["frete_custo"] is not None:
                        dif_frete = pct(atual["frete_custo"], velho["frete_custo"])
                        if dif_frete is not None and abs(dif_frete) >= 10:
                            direcao = "subiu" if dif_frete > 0 else "baixou"
                            anotar("frete",
                                   f"{quem}: frete {direcao} "
                                   f"({brl(velho['frete_custo'])} → {brl(atual['frete_custo'])}) "
                                   f"em {onde}", atual, peso=abs(dif_frete))

                # ---- estoque e disponibilidade ----
                if avisar_estoque and velho["estoque"] is not None \
                        and atual["estoque"] is not None:
                    if velho["estoque"] > 0 and atual["estoque"] == 0:
                        anotar("estoque",
                               f"{quem} FICOU SEM ESTOQUE em {onde} — janela para vender",
                               atual, {"permalink_dele": atual["permalink"]})
                    elif velho["estoque"] == 0 and atual["estoque"] > 0:
                        anotar("estoque", f"{quem} repôs estoque em {onde}", atual)

                if velho["status"] == "active" and atual["status"] != "active":
                    anotar("status",
                           f"{quem} saiu do ar ({atual['status']}) em {onde} "
                           f"— janela para vender", atual)

            # ---- vira alerta: individual quando é pontual, resumo quando é
            #      reajuste de tabela ----
            RESUMO = {
                "preco": "mexeu no preço de {n} produtos que você disputa",
                "frete": "mudou o frete de {n} produtos que você disputa",
                "estoque": "mudou o estoque de {n} produtos que você disputa",
                "status": "tirou do ar {n} anúncios que você disputa",
            }
            grupos: dict[tuple, list[dict]] = {}
            for e in eventos:
                grupos.setdefault((e["quem"], e["tipo"]), []).append(e)

            for (quem, tipo), lista in grupos.items():
                if len(lista) < juntar_a_partir_de:
                    for e in lista:
                        alerta("concorrente_mexeu", cfg, e["texto"],
                               e["item_id"], e["titulo"], e["dados"])
                    continue

                maiores = sorted(lista, key=lambda e: -e["peso"])[:3]
                linhas = []
                for e in maiores:
                    linha = f"  • {truncar(e['titulo'], 44)}"
                    if e["dados"].get("de"):
                        linha += f" — {brl(e['dados']['de'])} → {brl(e['dados']['para'])}"
                    linhas.append(linha)
                if len(lista) > len(maiores):
                    linhas.append(f"  (e mais {len(lista) - len(maiores)})")

                texto = (f"{quem} " + RESUMO[tipo].format(n=len(lista)) +
                         " de uma vez. É reajuste de tabela, não ajuste de "
                         "anúncio isolado.\n" + "\n".join(linhas))
                alerta("concorrente_mexeu", cfg, texto, None, quem,
                       {"quantos": len(lista), "tipo": tipo})

    # ------------- o concorrente está ganhando atenção -------------
    #
    # Preço é o sinal que chega DEPOIS. Quando o concorrente baixa o preço, a
    # disputa já começou. Visita é o que se move antes: ele aparece mais, é
    # visto mais, e só então o efeito vira venda.
    #
    # Por isso a régua é RELATIVA e comparada com a nossa na mesma ficha. Um
    # concorrente crescendo 60% numa semana em que nós crescemos 55% é
    # sazonalidade da categoria, não jogada dele — e avisar sobre isso ensina
    # o operador a ignorar o alerta.
    if (cfg := _reg(regras, "concorrente_ganhando_atencao")):
        crescimento_min = float(cfg.get("crescimento_percentual", 50))
        piso_visitas = int(cfg.get("minimo_visitas", 150))

        for l in con.execute(
            """
            WITH j AS (
              SELECT item_id, referencia, proprio, seller_id,
                     SUM(CASE WHEN data >= date('now', '-7 day')  THEN visitas END) AS agora,
                     SUM(CASE WHEN data <  date('now', '-7 day')
                               AND data >= date('now', '-14 day') THEN visitas END) AS antes
                FROM snap_visita_dia
               WHERE conta_slug = ?
               GROUP BY item_id
            )
            SELECT d.referencia, d.item_id, d.seller_id,
                   d.agora AS dele_agora, d.antes AS dele_antes,
                   n.agora AS meu_agora,  n.antes AS meu_antes
              FROM j d
              JOIN j n ON n.referencia = d.referencia AND n.proprio = 1
             WHERE d.proprio = 0 AND d.antes > 0 AND d.agora >= ?
            """, (conta.slug, piso_visitas),
        ):
            dele = pct(l["dele_agora"], l["dele_antes"])
            if dele is None or dele < crescimento_min:
                continue
            meu = pct(l["meu_agora"], l["meu_antes"]) if l["meu_antes"] else None

            # Só interessa se ele cresceu e nós não acompanhamos. A margem de
            # 15 pontos evita alarme por ruído de medição entre dois itens.
            if meu is not None and meu >= dele - 15:
                continue

            nosso = (f"o nosso ficou em {meu:+.0f}%" if meu is not None
                     else "não temos série do nosso para comparar")
            alerta("concorrente_ganhando_atencao", cfg,
                   f"Concorrente ganhando atenção em {truncar(l['referencia'], 44)}: "
                   f"as visitas dele subiram {dele:+.0f}% em 7 dias "
                   f"({l['dele_antes']} → {l['dele_agora']}) e {nosso}. "
                   f"Interesse se move antes do preço — vale olhar o que ele mudou "
                   f"antes de a venda migrar.",
                   l["item_id"], l["referencia"],
                   {"item_dele": l["item_id"], "seller_id": l["seller_id"],
                    "dele_antes": l["dele_antes"], "dele_agora": l["dele_agora"],
                    "meu_antes": l["meu_antes"], "meu_agora": l["meu_agora"]})

    con.commit()
    return gerados


def _sem_repetir(itens: list[dict]) -> list[dict]:
    """
    Um mesmo anúncio pode chegar duas vezes na lista de catálogo. Sem isso o
    operador recebe a mesma frase duplicada e conclui, com razão, que o
    sistema está confuso.
    """
    vistos, saida = set(), []
    for i in itens:
        chave = i.get("item_id")
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(i)
    return saida


def _contas_da_casa() -> dict[str, dict]:
    """
    seller_id do ML -> a conta nossa que tem aquele id.

    O motor precisa disto porque o ML não sabe que duas lojas são do mesmo
    dono: DECORALLI aparece em `snap_concorrente` da FACILITA 7.898 vezes,
    igualzinho a um terceiro. Sem separar, o alerta de preço recomenda baixar
    contra a própria irmã — em 03/09/2026 havia 19 avisos em 24 h dizendo "dá
    para acompanhar, seu piso é X" apontando para a conta ao lado, e 42 dos
    137 cruzamentos da FACILITA eram a Decoralli.

    ATENÇÃO ao ponto cego: conta com `user_id: SUBSTITUIR` no
    config/clientes.yaml não tem id para casar e volta a ser contada como
    terceiro, em silêncio. É o caso de `facilita-brasil-loja2` hoje, que vende
    a mesma Poltrona Mona das outras duas.
    """
    casa: dict[str, dict] = {}
    try:
        clientes = carregar_clientes(apenas_ativos=True)
    except Exception:
        return casa
    for cl in clientes:
        for ct in cl.contas:
            if ct.configurada:
                casa[str(ct.user_id)] = {"slug": ct.slug,
                                         "cliente_id": ct.cliente_id,
                                         "cliente_nome": cl.nome}
    return casa


def _virou(antes, depois) -> bool:
    """
    Verdadeiro só quando houve mudança REAL de um valor conhecido para outro.

    Se o valor anterior é nulo ou vazio, não houve mudança: o campo passou a
    ser coletado agora. Sem esta trava, toda coluna nova gera um alerta falso
    por anúncio na primeira leitura depois da atualização — foi assim que a
    conta do Ênio disparou 76 alertas de "foto trocada" e "modo de envio
    mudou" sem que nada tivesse mudado.
    """
    if antes is None or antes == "":
        return False
    if depois is None or depois == "":
        return False
    return antes != depois


def _diferenca_de_texto(antes: str, depois: str, limite: int = 70) -> str:
    """
    Mostra o que mudou, não os dois textos inteiros truncados no mesmo ponto —
    que é o jeito mais fácil de produzir um alerta ilegível quando a diferença
    está no fim da frase.
    """
    antes, depois = (antes or ""), (depois or "")
    if depois.startswith(antes):
        return f'acrescentaram "{truncar(depois[len(antes):].strip(), limite)}"'
    if antes.startswith(depois):
        return f'removeram "{truncar(antes[len(depois):].strip(), limite)}"'

    # acha o primeiro e o último ponto em comum, e mostra só o miolo que mudou
    inicio = 0
    while inicio < min(len(antes), len(depois)) and antes[inicio] == depois[inicio]:
        inicio += 1
    fim = 0
    while (fim < min(len(antes), len(depois)) - inicio
           and antes[-1 - fim] == depois[-1 - fim]):
        fim += 1
    trecho_antes = antes[inicio:len(antes) - fim].strip()
    trecho_depois = depois[inicio:len(depois) - fim].strip()
    if trecho_antes or trecho_depois:
        return (f'"{truncar(trecho_antes, 40) or "(nada)"}" virou '
                f'"{truncar(trecho_depois, 40) or "(nada)"}"')
    return f'agora: {truncar(depois, limite)}'


def avaliar_mudancas_proprias(con: sqlite3.Connection, conta: Conta,
                              carimbo_novo: str, novos: dict | None = None) -> int:
    """
    Tudo que mudou nos SEUS anúncios desde a coleta anterior.

    Existe separada de avaliar() pelo mesmo motivo da de concorrentes: o vigia
    contínuo roda isto a cada poucos minutos. São 2 chamadas à API para uma
    conta de 38 anúncios, então cabe no ciclo curto sem pesar.

    Cobre o que o Mercado Livre pode mexer sem te avisar — moderação, mudança
    de categoria, queda de qualidade — e o que alguém com acesso à conta pode
    alterar sem passar por você.
    """
    regras = carregar_regras()
    cfg = _reg(regras, "meu_anuncio_mudou")
    cfg_venda = _reg(regras, "venda_nova")
    if not cfg and not cfg_venda:
        return 0

    carimbo_velho = db.ultima_coleta(con, "snap_anuncio", conta.slug, antes_de=carimbo_novo)
    if not carimbo_velho:
        return 0

    if novos is None:
        novos = db.snapshot_por_item(con, "snap_anuncio", conta.slug, carimbo_novo)
    velhos = db.snapshot_por_item(con, "snap_anuncio", conta.slug, carimbo_velho)
    if not novos:
        return 0          # carimbo sem coleta: comparar contra nada inventa notícia
    gerados = 0

    # Último frete MEDIDO de cada anúncio, não o da coleta anterior.
    #
    # O frete próprio passou a ser medido por rodízio — alguns anúncios por
    # rodada, girando. Então na leitura anterior a maioria vem nula, e
    # comparar com ela nunca acusaria mudança nenhuma. O que vale é a última
    # medição de verdade, seja de 20 minutos ou de 3 horas atrás.
    frete_anterior: dict[str, float] = {}
    for l in con.execute(
        "SELECT item_id, frete_custo FROM snap_anuncio WHERE conta_slug = ? "
        "AND coletado_em < ? AND frete_custo IS NOT NULL "
        "GROUP BY item_id HAVING coletado_em = MAX(coletado_em)",
        (conta.slug, carimbo_novo)
    ):
        frete_anterior[l["item_id"]] = l["frete_custo"]

    def alerta(regra_nome, conf, mensagem, item_id=None, titulo=None, dados=None):
        nonlocal gerados
        entrou = db.registrar_alerta(
            con, cliente_id=conta.cliente_id, conta_slug=conta.slug,
            regra=regra_nome, critico=bool(conf.get("critico", False)),
            mensagem=mensagem, item_id=item_id, titulo=titulo, dados=dados,
        )
        if entrou:
            gerados += 1

    for item_id, n in novos.items():
        v = velhos.get(item_id)
        if not v:
            if cfg:
                alerta("meu_anuncio_mudou", cfg,
                       f"Publicaram um anúncio novo, a {brl(n['preco'])}: "
                       f"{humano.titulo_curto(n['titulo'], 60)}", item_id, n["titulo"],
                       {"permalink": n["permalink"]})
            continue

        rotulo = humano.titulo_curto(n["titulo"])

        # ---- venda ----
        if cfg_venda:
            novas = (n["vendidos"] or 0) - (v["vendidos"] or 0)
            if novas > 0:
                unidade = "unidade" if novas == 1 else "unidades"
                sobrou = n["estoque"] or 0
                texto = (f"Vendeu {novas} {unidade} de {rotulo} "
                         f"— {brl((n['preco'] or 0) * novas)}.")
                if sobrou == 0:
                    texto += " Era a última: o anúncio ficou sem estoque."
                elif sobrou <= 3:
                    texto += f" Restam só {sobrou}."
                else:
                    texto += f" Restam {sobrou}."
                alerta("venda_nova", cfg_venda, texto,
                       item_id, n["titulo"], {"permalink": n["permalink"]})

        if not cfg:
            continue

        # ---- título ----
        if _virou(v["titulo"], n["titulo"]):
            alerta("meu_anuncio_mudou", cfg,
                   f"Mudaram o título de {rotulo}. "
                   + _diferenca_de_texto(v["titulo"], n["titulo"]),
                   item_id, n["titulo"], {"permalink": n["permalink"],
                                          "antes": v["titulo"], "depois": n["titulo"]})

        # ---- foto de capa ----
        if _virou(v["thumbnail"], n["thumbnail"]):
            alerta("meu_anuncio_mudou", cfg,
                   f"Trocaram a foto de capa de {rotulo}. "
                   f"Se não foi você nem o cliente, alguém com acesso à conta mexeu.",
                   item_id, n["titulo"], {"permalink": n["permalink"]})

        # ---- infração / moderação ----
        antes_sub = set(str(v["sub_status"] or "").split(",")) - {""}
        agora_sub = set(str(n["sub_status"] or "").split(",")) - {""}
        entrou = agora_sub - antes_sub
        if entrou:
            descricao = humano.sub_status(sorted(entrou))
            consequencia = ""
            if "paused_by_seller" in entrou:
                consequencia = " Parou de vender agora."
            elif entrou & {"suspended", "freeze", "banned_registration", "moderated"}:
                consequencia = " Isso é ação do Mercado Livre, não da conta — precisa resolver."
            elif "out_of_stock" in entrou:
                consequencia = " Segue no ar mas não pode vender, e perde posição na busca."
            alerta("meu_anuncio_mudou", cfg,
                   f"{rotulo} está {descricao}.{consequencia}",
                   item_id, n["titulo"], {"permalink": n["permalink"],
                                          "codigos": sorted(entrou)})

        # ---- tipo de anúncio (muda a comissão) ----
        if _virou(v["tipo_anuncio"], n["tipo_anuncio"]):
            alerta("meu_anuncio_mudou", cfg,
                   f"O tipo do anúncio {rotulo} mudou de "
                   f"{humano.tipo_anuncio(v['tipo_anuncio'])} para "
                   f"{humano.tipo_anuncio(n['tipo_anuncio'])}. "
                   f"Isso muda a comissão que o Mercado Livre cobra por venda.",
                   item_id, n["titulo"])

        # ---- frete ----
        if _virou(v["frete_gratis"], n["frete_gratis"]):
            if n["frete_gratis"]:
                alerta("meu_anuncio_mudou", cfg,
                       f"{rotulo} passou a ter frete grátis.",
                       item_id, n["titulo"])
            else:
                alerta("meu_anuncio_mudou", cfg,
                       f"{rotulo} perdeu o frete grátis. "
                       f"Anúncio sem frete grátis costuma cair de posição na busca.",
                       item_id, n["titulo"])
        # ---- o Mercado Livre reajustou o frete DESTE anúncio ----
        #
        # Só compara quando os dois lados foram medidos — o custo é lido uma
        # vez por dia, e no resto das rodadas o campo vem nulo. Sem essa
        # trava, toda rodada do vigia acusaria "frete mudou" comparando com
        # nada, que foi exatamente o erro dos 76 alertas falsos.
        try:
            frete_agora = n["frete_custo"]
        except (KeyError, IndexError):
            frete_agora = None
        frete_antes = frete_anterior.get(item_id)
        if frete_antes is not None and frete_agora is not None:
            dif = pct(frete_agora, frete_antes)
            if dif is not None and abs(dif) >= 5 and abs(frete_agora - frete_antes) >= 2:
                if n["frete_gratis"]:
                    quem_paga = ("Como o anúncio é frete grátis, essa diferença "
                                 "sai da sua margem.")
                else:
                    quem_paga = "Quem paga é o comprador, no fechamento do pedido."
                alerta("meu_anuncio_mudou", cfg,
                       f"O Mercado Livre {'aumentou' if dif > 0 else 'reduziu'} o frete "
                       f"de {rotulo} em {abs(dif):.0f}% "
                       f"({brl(frete_antes)} → {brl(frete_agora)}). {quem_paga}",
                       item_id, n["titulo"], {"permalink": n["permalink"],
                                              "de": frete_antes, "para": frete_agora})

        if _virou(v["envio_modo"], n["envio_modo"]):
            alerta("meu_anuncio_mudou", cfg,
                   f"O envio de {rotulo} mudou de {humano.envio(v['envio_modo'])} "
                   f"para {humano.envio(n['envio_modo'])}.",
                   item_id, n["titulo"])

        # ---- categoria ----
        if _virou(v["categoria"], n["categoria"]):
            alerta("meu_anuncio_mudou", cfg,
                   f"{rotulo} mudou de categoria. Isso mexe na comissão e em "
                   f"onde o anúncio aparece na busca. "
                   f"(de {v['categoria']} para {n['categoria']})",
                   item_id, n["titulo"])

        # ---- catálogo ----
        if _virou(v["catalogo"], n["catalogo"]):
            if n["catalogo"]:
                alerta("meu_anuncio_mudou", cfg,
                       f"{rotulo} entrou no catálogo — agora disputa a vitrine "
                       f"com outros vendedores do mesmo produto.",
                       item_id, n["titulo"])
            else:
                alerta("meu_anuncio_mudou", cfg,
                       f"{rotulo} saiu do catálogo e voltou a ser anúncio comum.",
                       item_id, n["titulo"])

        # ---- qualidade ----
        if v["saude"] is not None and n["saude"] is not None:
            if n["saude"] < v["saude"] - 0.05:
                alerta("meu_anuncio_mudou", cfg,
                       f"A qualidade de {rotulo} caiu de {v['saude']:.0%} para "
                       f"{n['saude']:.0%}. Qualidade baixa derruba a exposição — "
                       f"costuma ser ficha técnica ou foto faltando.",
                       item_id, n["titulo"], {"permalink": n["permalink"]})

        # ---- promoção ----
        d_velho = bool(v["descontos"])
        d_novo = bool(n["descontos"])
        if d_novo - d_velho:
            alerta("meu_anuncio_mudou", cfg,
                   f"{rotulo} entrou numa promoção do Mercado Livre.",
                   item_id, n["titulo"])
        elif d_velho - d_novo:
            alerta("meu_anuncio_mudou", cfg,
                   f"{rotulo} saiu da promoção do Mercado Livre.",
                   item_id, n["titulo"])

    # ---- anúncio sumiu da conta ----
    if cfg:
        for item_id, v in velhos.items():
            if item_id not in novos:
                alerta("meu_anuncio_mudou", cfg,
                       f"{humano.titulo_curto(v['titulo'], 50)} sumiu da conta — "
                       f"foi excluído, ou o Mercado Livre tirou do ar.",
                       item_id, v["titulo"])

    con.commit()
    return gerados


def avaliar(con: sqlite3.Connection, conta: Conta, carimbo_novo: str,
            buy_box: list[dict] | None = None) -> int:
    regras = carregar_regras()
    carimbo_velho = db.ultima_coleta(con, "snap_anuncio", conta.slug, antes_de=carimbo_novo)

    novos = db.snapshot_por_item(con, "snap_anuncio", conta.slug, carimbo_novo)
    velhos = db.snapshot_por_item(con, "snap_anuncio", conta.slug, carimbo_velho) if carimbo_velho else {}

    # Sem anúncios neste carimbo, não houve coleta — e a ausência de coleta não
    # é notícia. Sem esta trava, todas as regras que percorrem os anúncios
    # concluem que a conta inteira desapareceu.
    if not novos:
        return avaliar_busca(con, conta, carimbo_novo)

    gerados = 0

    def alerta(regra_nome, cfg, mensagem, item_id=None, titulo=None, dados=None):
        nonlocal gerados
        entrou = db.registrar_alerta(
            con,
            cliente_id=conta.cliente_id,
            conta_slug=conta.slug,
            regra=regra_nome,
            critico=bool(cfg.get("critico", False)),
            mensagem=mensagem,
            item_id=item_id,
            titulo=titulo,
            dados=dados,
        )
        if entrou:
            gerados += 1

    # ---------------- estoque zerado / baixo ----------------
    if (cfg := _reg(regras, "estoque_zerado")):
        for item_id, n in novos.items():
            if n["status"] == "active" and (n["estoque"] or 0) == 0:
                anterior = velhos.get(item_id)
                if not anterior or (anterior["estoque"] or 0) > 0:
                    alerta("estoque_zerado", cfg,
                           f"ACABOU O ESTOQUE de {truncar(n['titulo'], 46)}. O anúncio segue no ar mas não pode vender — e anúncio ativo sem estoque perde posição na busca.",
                           item_id, n["titulo"], {"permalink": n["permalink"]})

    if (cfg := _reg(regras, "estoque_baixo")):
        limiar = int(cfg.get("limiar_unidades", 5))
        for item_id, n in novos.items():
            est = n["estoque"] or 0
            if n["status"] == "active" and 0 < est <= limiar:
                anterior = velhos.get(item_id)
                if not anterior or (anterior["estoque"] or 0) > limiar:
                    alerta("estoque_baixo", cfg,
                           f"Restam só {est} unidade(s) de {truncar(n['titulo'], 44)}. Hora de repor antes de zerar.",
                           item_id, n["titulo"])

    # ---------------- anúncio pausado ----------------
    if (cfg := _reg(regras, "anuncio_pausado")):
        for item_id, n in novos.items():
            anterior = velhos.get(item_id)
            if anterior and anterior["status"] == "active" and n["status"] != "active":
                sub = f" ({n['sub_status']})" if n["sub_status"] else ""
                alerta("anuncio_pausado", cfg,
                       f"SAIU DO AR o anúncio {truncar(n['titulo'], 44)}. "
                       f"Situação: {n['status']}{sub}. Enquanto estiver assim, não vende "
                       f"e não aparece na busca.",
                       item_id, n["titulo"], {"permalink": n["permalink"]})

    # ---------------- meu preço mudou ----------------
    if (cfg := _reg(regras, "meu_preco_caiu_ou_subiu")):
        minimo = float(cfg.get("variacao_minima_percentual", 3.0))
        for item_id, n in novos.items():
            anterior = velhos.get(item_id)
            if not anterior:
                continue
            variacao = pct(n["preco"], anterior["preco"])
            if variacao is not None and abs(variacao) >= minimo:
                direcao = "subiu" if variacao > 0 else "caiu"
                alerta("meu_preco_caiu_ou_subiu", cfg,
                       f"O SEU preço {direcao}: {brl(anterior['preco'])} → {brl(n['preco'])} "
                       f"({abs(variacao):.1f}%) em {truncar(n['titulo'], 42)}. "
                       f"Se não foi você quem mexeu, confira quem tem acesso à conta.",
                       item_id, n["titulo"])

    # ---------------- venda travada ----------------
    if (cfg := _reg(regras, "venda_travada")):
        dias = int(cfg.get("dias_sem_venda", 7))
        antigo_carimbo = con.execute(
            "SELECT MAX(coletado_em) t FROM snap_anuncio "
            "WHERE conta_slug = ? AND coletado_em <= datetime(?, ?)",
            (conta.slug, carimbo_novo, f"-{dias} days"),
        ).fetchone()
        base = db.snapshot_por_item(con, "snap_anuncio", conta.slug, antigo_carimbo["t"]) if antigo_carimbo and antigo_carimbo["t"] else {}
        for item_id, n in novos.items():
            b = base.get(item_id)
            if not b or n["status"] != "active":
                continue
            if (b["vendidos"] or 0) > 0 and (n["vendidos"] or 0) == (b["vendidos"] or 0):
                alerta("venda_travada", cfg,
                       f"PAROU DE VENDER: {truncar(n['titulo'], 44)} está há {dias} dias sem "
                       f"nenhuma venda nova (segue em {n['vendidos']} no total). "
                       f"Cruze com as visitas: muita visita e nenhuma venda é preço; "
                       f"pouca visita é posição.",
                       item_id, n["titulo"])

    # ---------------- concorrente cruzou meu preço ----------------
    #
    # Só comparamos preço quando a comparação é HONESTA. Duas fontes servem:
    #
    #   1. buy box  — mesmo produto de catálogo, mesma ficha. Comparação exata.
    #   2. produto vigiado com vínculo — a ficha de catálogo tem um anúncio
    #      SEU declarado como par dela, em concorrentes.yaml ou pelo próprio
    #      anúncio que já vive naquele produto.
    #
    # O que NÃO serve: comparar com qualquer item que apareceu na mesma
    # categoria ou no mesmo termo de busca. Em produto sob medida isso compara
    # um toldo 380x100 com um 200x60 e gera alerta que só ensina a ignorar
    # alertas.
    if (cfg := _reg(regras, "concorrente_cruzou_preco")):
        tolerancia = float(cfg.get("tolerancia_percentual", 1.0))

        # Piso de preço, se o cliente já mandou a planilha de custo. É o que
        # transforma "o concorrente está mais barato" em decisão: sem saber
        # até onde dá para descer, o alerta obriga a pessoa a ir procurar a
        # resposta em outro lugar, que é o mesmo que não avisar.
        pisos: dict[str, dict] = {}
        try:
            from . import precificacao
            pisos = {p["item_id"]: p for p in precificacao.carregar(con, conta)}
        except Exception:
            pisos = {}
        vigiados = con.execute(
            "SELECT * FROM snap_concorrente WHERE conta_slug = ? AND coletado_em = ? "
            "AND origem = 'vigilancia' AND comparar_com IS NOT NULL",
            (conta.slug, carimbo_novo),
        ).fetchall()

        # Última vitrine medida de cada anúncio. Sem isto, nos ciclos curtos
        # do vigia a comparação usa o preço de cadastro e o alerta mente.
        vitrines = db.vitrines_recentes(con, conta.slug)

        # Quem "cruzou o preço" pode ser a loja ao lado. Ver _contas_da_casa.
        casa = _contas_da_casa()
        cfg_canibal = _reg(regras, "canibalizacao_interna")

        for c in vigiados:
            meu = novos.get(c["comparar_com"])
            meu_preco = preco_real(meu, vitrines) if meu else None
            if not meu or meu_preco is None or c["preco"] is None:
                continue
            limite = meu_preco * (1 - tolerancia / 100.0)
            if float(c["preco"]) < limite:
                dif = pct(c["preco"], meu_preco) or 0.0
                piso = pisos.get(meu["item_id"])

                # ---- é conta nossa do outro lado? ----
                # Sai por outra regra e com outra frase. O conselho de piso
                # abaixo ("dá para acompanhar") é correto contra um terceiro e
                # destrutivo contra a irmã: as duas descem juntas na mesma
                # ficha e o buy box não muda de dono.
                nossa = casa.get(str(c["seller_id"] or ""))
                if nossa and nossa["slug"] != conta.slug:
                    if not cfg_canibal:
                        continue
                    quem = c["seller_nickname"] or nossa["slug"]
                    if nossa["cliente_id"] == conta.cliente_id:
                        texto_casa = (
                            f"CANIBALIZAÇÃO: {quem} é conta do MESMO cliente, não "
                            f"concorrente. Está a {brl(c['preco'])} ({dif:.1f}% vs. "
                            f"seus {brl(meu_preco)}) em {truncar(meu['titulo'], 40)}. "
                            f"Acompanhar aqui é as duas perderem margem na mesma "
                            f"ficha — quem recua se decide pela carteira, não pelo piso.")
                    else:
                        texto_casa = (
                            f"{quem} está a {brl(c['preco'])} ({dif:.1f}% vs. seus "
                            f"{brl(meu_preco)}) em {truncar(meu['titulo'], 40)} — mas "
                            f"essa conta também é operada por nós "
                            f"({nossa['cliente_nome']}). Confirme que relação é essa "
                            f"antes de mexer no preço: entre Ênio e Maxi, por exemplo, "
                            f"é fábrica e revenda, não disputa.")
                    alerta("canibalizacao_interna", cfg_canibal, texto_casa,
                           meu["item_id"], meu["titulo"],
                           {"por_item": True,
                            "permalink": meu["permalink"],
                            "permalink_dele": c["permalink"],
                            "item_dele": c["item_id"],
                            "conta_dele": nossa["slug"],
                            "mesmo_cliente": nossa["cliente_id"] == conta.cliente_id,
                            "preco_dele": c["preco"], "meu_preco": meu_preco,
                            "piso": (piso or {}).get("piso")})
                    continue

                texto = (f"{c['seller_nickname'] or 'concorrente'} está a "
                         f"{brl(c['preco'])} ({dif:.1f}% vs. seus "
                         f"{brl(meu_preco)}) — {truncar(meu['titulo'], 42)}.")

                if piso and piso.get("piso"):
                    if float(c["preco"]) >= piso["piso"]:
                        texto += (f" Dá para acompanhar: seu piso é "
                                  f"{brl(piso['piso'])}.")
                    elif piso.get("empate") and float(c["preco"]) >= piso["empate"]:
                        texto += (f" Acompanhar sai da sua margem: o preço dele "
                                  f"fica entre o empate ({brl(piso['empate'])}) e "
                                  f"o seu piso ({brl(piso['piso'])}).")
                    else:
                        texto += (f" NÃO acompanhe: abaixo de {brl(piso['empate'])} "
                                  f"você vende no prejuízo.")

                # Os dois links vão juntos: sem o seu, é preciso caçar o
                # anúncio na conta para conferir; sem o dele, é preciso
                # procurar o concorrente na busca. O alerta existe para
                # poupar exatamente esses dois passos.
                alerta("concorrente_cruzou_preco", cfg, texto,
                       meu["item_id"], meu["titulo"],
                       {"por_item": True,
                        "permalink": meu["permalink"],
                        "permalink_dele": c["permalink"],
                        "item_dele": c["item_id"],
                        "preco_dele": c["preco"], "meu_preco": meu_preco,
                        "piso": (piso or {}).get("piso")})

    # ---------------- mudanças nos meus anúncios e nos dos concorrentes ----
    gerados += avaliar_mudancas_proprias(con, conta, carimbo_novo, novos)
    gerados += avaliar_mudancas_concorrentes(con, conta, carimbo_novo, novos)

    # ---------------- queda de posição ----------------
    # As regras que dependem da busca vivem numa função própria: elas também
    # rodam sozinhas quando chega uma medição de posição, sem coleta junto.
    gerados += avaliar_busca(con, conta, carimbo_novo, alerta_externo=alerta)

    # ---------------- buy box ----------------
    if (cfg := _reg(regras, "perdeu_buy_box")) and buy_box:
        cfg_canibal_bb = _reg(regras, "canibalizacao_interna")
        for b in _sem_repetir(buy_box):
            if b.get("status") and b["status"] not in ("winning", "sharing_first_place"):
                alvo = b.get("preco_para_ganhar")
                meu = b.get("meu_preco")

                # Quem levou a vitrine? O coletor resolve o dono pelo MLB do
                # vencedor, porque a API não manda o seller. Três desfechos
                # diferentes, e só o terceiro é perder de verdade.
                dono_slug = b.get("vencedor_slug")
                quem = b.get("vencedor_apelido") or dono_slug
                preco_dele = b.get("preco_vencedor") or alvo

                # (1) A ficha está com OUTRO anúncio SEU, na mesma conta. Não é
                # derrota: é duplicata dividindo a própria ficha. Chamar isso de
                # "você perdeu para MRBRASILL" manda a pessoa cortar preço
                # contra ela mesma — 15 avisos assim em 30 min na FACILITA.
                if dono_slug and dono_slug == conta.slug:
                    if not cfg_canibal_bb:
                        continue
                    texto = (f"A vitrine do catálogo em {truncar(b['titulo'], 40)} "
                             f"está com OUTRO ANÚNCIO SEU ({b.get('vencedor_item')}"
                             f"{', ' + brl(preco_dele) if preco_dele else ''}). "
                             f"Você não perdeu a ficha — está dividindo ela consigo "
                             f"mesmo. Dois anúncios na mesma ficha só se sustentam "
                             f"com preço ou tipo diferentes de propósito; senão é "
                             f"duplicata, e o corte é por histórico.")
                    alerta("canibalizacao_interna", cfg_canibal_bb, texto,
                           b["item_id"], b["titulo"], {**b, "por_item": True})
                    continue

                # (2) A ficha está com outra conta da casa.
                if dono_slug:
                    if not cfg_canibal_bb:
                        continue
                    texto = (f"A vitrine do catálogo em {truncar(b['titulo'], 42)} "
                             f"está com {quem} — conta NOSSA, não concorrente.")
                    if alvo and meu:
                        texto += (f" Seu preço é {brl(meu)} e o dela {brl(preco_dele)}: "
                                  f"cortar para ganhar seria tirar a venda de dentro de casa "
                                  f"e afundar as duas na mesma ficha.")
                    alerta("canibalizacao_interna", cfg_canibal_bb, texto,
                           b["item_id"], b["titulo"], {**b, "por_item": True})
                    continue

                texto = (f"Você PERDEU a vitrine do catálogo em "
                         f"{truncar(b['titulo'], 46)}. "
                         f"Quem clica em comprar está indo para "
                         f"{quem if quem else 'outro vendedor'}.")
                if alvo and meu:
                    quanto = float(meu) - float(alvo)
                    texto += (f" Seu preço é {brl(meu)}; para voltar a aparecer "
                              f"teria que ir para {brl(alvo)} — {brl(quanto)} a menos.")
                elif alvo:
                    texto += f" Para voltar a aparecer, o preço teria que ser {brl(alvo)}."
                alerta("perdeu_buy_box", cfg, texto, b["item_id"], b["titulo"], b)

    # ---------------- buy box no fio ----------------
    # Ganhar o buy box por 1% é ganhar hoje e perder amanhã. Avisar antes de
    # virar dá tempo de decidir com calma em vez de reagir.
    if (cfg := _reg(regras, "buy_box_no_fio")) and buy_box:
        margem_min = float(cfg.get("margem_percentual", 3.0))
        for b in _sem_repetir(buy_box):
            if b.get("status") not in ("winning", "sharing_first_place"):
                continue
            meu_preco, alvo = b.get("meu_preco"), b.get("preco_para_ganhar")
            if not meu_preco or not alvo:
                continue
            folga = pct(meu_preco, alvo)
            if folga is None or abs(folga) > margem_min:
                continue
            diferenca = abs(float(meu_preco) - float(alvo))
            alerta("buy_box_no_fio", cfg,
                   f"Você está ganhando a vitrine do catálogo em "
                   f"{truncar(b['titulo'], 44)} por apenas {brl(diferenca)}. "
                   f"Se um concorrente baixar para {brl(alvo)}, você perde o "
                   f"botão de comprar.",
                   b["item_id"], b["titulo"], b)

    # ---------------- reputação ----------------
    if (cfg := _reg(regras, "reputacao_caiu")):
        historico = con.execute(
            "SELECT nivel, coletado_em FROM snap_conta WHERE conta_slug = ? ORDER BY coletado_em DESC LIMIT 2",
            (conta.slug,),
        ).fetchall()
        if len(historico) == 2 and historico[0]["nivel"] and historico[1]["nivel"]:
            ordem = ["1_red", "2_orange", "3_yellow", "4_light_green", "5_green"]
            try:
                if ordem.index(historico[0]["nivel"]) < ordem.index(historico[1]["nivel"]):
                    alerta("reputacao_caiu", cfg,
                           f"A REPUTAÇÃO DA CONTA PIOROU: {historico[1]['nivel']} → "
                           f"{historico[0]['nivel']}. Isso afeta todos os anúncios ao "
                           f"mesmo tempo — é a prioridade número um.")
            except ValueError:
                pass

    con.commit()
    return gerados



def avaliar_busca(con: sqlite3.Connection, conta: Conta, carimbo_novo: str,
                  alerta_externo=None) -> int:
    """
    As duas regras que dependem da busca: queda de posição e concorrente novo
    no topo.

    Separada porque a medição de posição chega de fora, sem coleta junto — e
    chamar avaliar() inteiro nesse momento é desastre: sem snap_anuncio naquele
    carimbo, TODOS os anúncios da conta parecem ter sumido. Foi exatamente o
    que aconteceu no primeiro teste: 41 alertas de "sumiu da conta" numa
    importação que só trazia posições.
    """
    regras = carregar_regras()
    gerados = 0

    if alerta_externo is not None:
        alerta = alerta_externo
    else:
        def alerta(regra_nome, cfg, mensagem, item_id=None, titulo=None, dados=None):
            nonlocal gerados
            entrou = db.registrar_alerta(
                con, cliente_id=conta.cliente_id, conta_slug=conta.slug,
                regra=regra_nome, critico=bool(cfg.get("critico", False)),
                mensagem=mensagem, item_id=item_id, titulo=titulo, dados=dados)
            if entrou:
                gerados += 1

    if (cfg := _reg(regras, "queda_de_posicao")):
        minimo = int(cfg.get("queda_minima_posicoes", 3))
        anterior_pos = db.ultima_coleta(con, "snap_posicao", conta.slug, antes_de=carimbo_novo)
        if anterior_pos:
            velhas = {
                (l["termo"], l["item_id"]): l["posicao"]
                for l in con.execute(
                    "SELECT termo, item_id, posicao FROM snap_posicao WHERE conta_slug = ? AND coletado_em = ?",
                    (conta.slug, anterior_pos),
                )
            }
            for l in con.execute(
                "SELECT termo, item_id, posicao FROM snap_posicao WHERE conta_slug = ? AND coletado_em = ?",
                (conta.slug, carimbo_novo),
            ):
                antes = velhas.get((l["termo"], l["item_id"]))
                if antes and l["posicao"] and l["posicao"] - antes >= minimo:
                    onde = (f"mais vendidos de {l['termo'].removeprefix('top:')}"
                            if l["termo"].startswith("top:") else l["termo"])
                    alerta("queda_de_posicao", cfg,
                           f"Seu anúncio caiu da posição {antes} para "
                           f"{l['posicao']} em {onde}.",
                           l["item_id"], f"busca: {l['termo']}")

    # ---------------- concorrente novo no topo ----------------
    if (cfg := _reg(regras, "concorrente_novo_no_topo")):
        top_n = int(cfg.get("top_n", 10))
        vistos_novos: set = set()
        anterior_conc = db.ultima_coleta(con, "snap_concorrente", conta.slug, antes_de=carimbo_novo)
        if anterior_conc:
            for termo_row in con.execute(
                "SELECT DISTINCT referencia FROM snap_concorrente "
                "WHERE conta_slug = ? AND coletado_em = ? AND origem = 'palavra-chave'",
                (conta.slug, carimbo_novo),
            ):
                termo = termo_row["referencia"]
                antes = {
                    l["seller_id"]
                    for l in con.execute(
                        "SELECT seller_id FROM snap_concorrente WHERE conta_slug = ? AND coletado_em = ? "
                        "AND referencia = ? AND posicao <= ?",
                        (conta.slug, anterior_conc, termo, top_n),
                    )
                }
                for l in con.execute(
                    "SELECT seller_id, seller_nickname, preco, posicao FROM snap_concorrente "
                    "WHERE conta_slug = ? AND coletado_em = ? AND referencia = ? AND posicao <= ?",
                    (conta.slug, carimbo_novo, termo, top_n),
                ):
                    chave = (l["seller_id"], "novo_no_topo")
                    if l["seller_id"] and l["seller_id"] not in antes and chave not in vistos_novos:
                        vistos_novos.add(chave)
                        # o termo vai como título para a mensagem agrupar por
                        # busca, em vez de virar uma linha solta sem contexto
                        alerta("concorrente_novo_no_topo", cfg,
                               f"{l['seller_nickname'] or l['seller_id']} entrou no "
                               f"top {top_n}: posição {l['posicao']} a {brl(l['preco'])}",
                               None, f"busca: {termo}")


    con.commit()
    return gerados


def avaliar_promocoes(con: sqlite3.Connection, conta: Conta, carimbo_novo: str,
                      alerta_externo=None) -> int:
    """
    Avisa quando o Mercado Livre LIBERA uma campanha para um anúncio.

    O ML oferece campanha anúncio por anúncio, com o preço já calculado, e no
    aplicativo isso é um botão de aceitar sem nenhuma menção a custo. É assim
    que um anúncio saudável vira prejuízo em dois toques — e foi o que já
    aconteceu nesta conta: as campanhas em curso derrubaram a linha de metal
    para perto do custo.

    Por isso o alerta não diz só "liberou promoção". Ele cruza o preço da
    campanha com o piso do anúncio e entrega o veredito junto, porque a
    pergunta que o operador tem nesse momento não é 'existe promoção?', é
    'dá para aceitar?'.

    Só entra campanha NOVA. Repetir a cada rodada as mesmas 47 campanhas
    abertas treinaria qualquer um a ignorar o canal.
    """
    from . import promocoes as _promo
    from . import precificacao as _prec

    regras = carregar_regras()
    cfg = _reg(regras, "promocao_liberada")
    if not cfg:
        return 0

    gerados = 0
    if alerta_externo is not None:
        alerta = alerta_externo
    else:
        def alerta(regra_nome, cfg_, mensagem, item_id=None, titulo=None, dados=None):
            nonlocal gerados
            entrou = db.registrar_alerta(
                con, cliente_id=conta.cliente_id, conta_slug=conta.slug,
                regra=regra_nome, critico=bool(cfg_.get("critico", False)),
                mensagem=mensagem, item_id=item_id, titulo=titulo, dados=dados)
            if entrou:
                gerados += 1

    novas = [l for l in _promo.novidades(con, conta.slug, carimbo_novo)
             if l["status"] == "candidate"]
    if not novas:
        return gerados

    pisos = {r["item_id"]: r for r in _prec.carregar(con, conta)}
    anuncios = {l["item_id"]: l for l in con.execute(
        "SELECT item_id, titulo, permalink FROM snap_anuncio "
        "WHERE conta_slug = ? AND coletado_em = ("
        "  SELECT MAX(coletado_em) FROM snap_anuncio WHERE conta_slug = ?)",
        (conta.slug, conta.slug))}

    for l in novas:
        item_id = l["item_id"]
        a = anuncios.get(item_id)
        titulo = a["titulo"] if a else item_id
        r = pisos.get(item_id)
        v = _promo.veredito(l, r["piso"] if r else None, r["preco"] if r else None)
        nome = _promo.nome_legivel(l)

        if v["cabe"] is None:
            # Sem custo cadastrado não há veredito. Dizer 'talvez' é pior que
            # avisar que falta o dado.
            msg = (f"O Mercado Livre liberou a campanha *{nome}* para este anúncio, "
                   f"a {brl(v.get('preco'))}. Não consigo dizer se compensa: "
                   f"este anúncio não tem custo na planilha.")
        elif v["cabe"]:
            msg = (f"O Mercado Livre liberou a campanha *{nome}* para este anúncio. "
                   f"O preço iria para {brl(v['preco'])} e ainda sobra "
                   f"{brl(v['sobra'])} acima do piso — dá para aceitar.")
        else:
            msg = (f"O Mercado Livre liberou a campanha *{nome}* para este anúncio, "
                   f"a {brl(v['preco'])}. Isso fica {brl(abs(v['sobra']))} ABAIXO do "
                   f"seu piso de {brl(r['piso'])}. Aceitar é vender com margem "
                   f"menor que a combinada.")

        if l["parte_do_vendedor"] is not None:
            msg += (f" Nesta campanha o Mercado Livre entra com "
                    f"{l['parte_do_ml']:.0f}% do desconto e você com "
                    f"{l['parte_do_vendedor']:.0f}%.")

        if l["tipo"] == "LIGHTNING" and l["preco_minimo"]:
            msg += (f" É oferta relâmpago: o sugerido é "
                    f"{brl(l['preco_sugerido'])}, mas o ML aceita descer até "
                    f"{brl(l['preco_minimo'])} — não há trava do lado deles.")

        # O link do anúncio vai junto: a decisão de aceitar ou não a campanha
        # se toma na página dele, e sem o endereço é preciso caçá-lo na conta.
        # Campanha liberada é ESTADO, não acontecimento: ela continua aberta
        # rodada após rodada. O texto carrega preço e sobra, e basta o piso
        # mudar um centavo para a deduplicação por mensagem achar que é
        # campanha nova — foi o que mandou a mesma oferta às 08:00 e às 08:06.
        alerta("promocao_liberada", cfg, msg, item_id=item_id, titulo=titulo,
               dados={"por_item": True,
                      "promocao": l["promocao_id"], "tipo": l["tipo"],
                      "permalink": (a["permalink"] if a else None),
                      "preco": v.get("preco"), "piso": r["piso"] if r else None,
                      "cabe": v["cabe"]})

    return gerados


def _dias_desde(inicio: str | None, agora: str) -> float | None:
    """Dias corridos entre o início da campanha e a leitura."""
    if not inicio:
        return None
    horas = _horas_entre(inicio, agora)
    return (horas / 24.0) if horas else None


def _quantos_dias(dias: float) -> str:
    if dias < 1.5:
        return "1 dia"
    return f"{dias:.0f} dias"


def _prazo(dias: float) -> str:
    """'em 3 dias' é informação; 'em 0 dia(s)' é defeito."""
    horas = dias * 24
    if horas < 12:
        return f"em menos de {max(1, round(horas))}h"
    if dias < 1.5:
        return "amanhã"
    return f"em {dias:.0f} dias"


def _data_curta(iso: str) -> str:
    """
    A data como o operador lê, no fuso dele.

    Não é frescura: o ML devolve o fim da campanha em UTC como
    '2026-09-30T02:59:59Z', que no Brasil é dia 29 às 23:59. Cortar a string
    em dez caracteres anunciaria um dia a mais de campanha do que existe.
    """
    from .utils import para_br
    try:
        return para_br(iso).split(" ")[0][:5]
    except Exception:
        return str(iso)[:10]


def _passou_o_intervalo(con: sqlite3.Connection, chave: str, agora: str,
                        horas: int) -> bool:
    """
    Deixa passar no máximo um aviso a cada N horas para a mesma chave.

    Diferente da janela de mensagem repetida do registrar_alerta: aqui a
    mensagem MUDA a cada rodada (os números sobem), então a defesa contra
    repetição tem que ser por assunto, não por texto.
    """
    ultimo = db.ler_marcador(con, chave)
    if ultimo:
        passadas = _horas_entre(ultimo, agora)
        if passadas is not None and passadas < horas:
            return False
    db.gravar_marcador(con, chave, agora)
    return True


def _horas_entre(inicio: str, fim: str) -> float | None:
    """Distância em horas entre dois carimbos ISO do banco."""
    from datetime import datetime
    try:
        a = datetime.fromisoformat(str(inicio).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(fim).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return abs((b - a).total_seconds()) / 3600.0 or None


def _preco_com_cupom(preco: float | None, campanha) -> float | None:
    """
    O preço que o comprador realmente paga quando usa o cupom.

    Cupom não altera o preço do anúncio — some no checkout. Comparar o preço
    de vitrine com o piso numa conta que tem cupom ativo dá o veredito errado
    para todo anúncio participante, porque falta exatamente o desconto que
    vai sair do bolso do vendedor.
    """
    if preco is None:
        return None
    if campanha["valor_fixo"]:
        return preco - float(campanha["valor_fixo"])
    if campanha["percentual"]:
        desconto = preco * float(campanha["percentual"]) / 100.0
        teto = campanha["compra_maxima"]
        if teto:
            desconto = min(desconto, float(teto))
        return preco - desconto
    return preco


def _quando_acaba(gasto_por_dia: float | None, restante: float | None) -> float | None:
    if not gasto_por_dia or gasto_por_dia <= 0 or restante is None:
        return None
    return restante / gasto_por_dia


def avaliar_cupons(con: sqlite3.Connection, conta: Conta, carimbo_novo: str,
                   alerta_externo=None) -> int:
    """
    Três perguntas sobre campanha de cupom, nenhuma respondida pelo painel do ML.

    1. Apareceu campanha nova? Cupom é criado no aplicativo, em três toques, e
       quem opera a conta raramente avisa. A campanha não muda o preço de
       nenhum anúncio, então nada no relatório denuncia que ela existe — o
       dinheiro simplesmente começa a sumir no checkout.

    2. O orçamento está queimando rápido? Aqui o Mercado Livre não
       co-participa: o orçamento é 100% do vendedor. Um cupom de R$ 20 com
       R$ 4.000 de teto são 200 vendas com R$ 20 a menos cada, e o teto é a
       única trava — quando ele acaba, já acabou.

    3. O cupom derruba algum anúncio abaixo do piso? É a pergunta que o preço
       de vitrine não responde, porque o desconto do cupom só aparece no
       checkout.
    """
    from . import cupons as _cup
    from . import precificacao as _prec

    regras = carregar_regras()
    gerados = 0
    if alerta_externo is not None:
        alerta = alerta_externo
    else:
        def alerta(regra_nome, cfg_, mensagem, item_id=None, titulo=None, dados=None):
            nonlocal gerados
            entrou = db.registrar_alerta(
                con, cliente_id=conta.cliente_id, conta_slug=conta.slug,
                regra=regra_nome, critico=bool(cfg_.get("critico", False)),
                mensagem=mensagem, item_id=item_id, titulo=titulo, dados=dados)
            if entrou:
                gerados += 1

    atuais = con.execute(
        "SELECT * FROM snap_cupom WHERE conta_slug = ? AND coletado_em = ?",
        (conta.slug, carimbo_novo)).fetchall()
    if not atuais:
        return gerados

    pisos = {r["item_id"]: r for r in _prec.carregar(con, conta)}

    for c in atuais:
        if c["status"] not in _cup.VIVAS:
            continue

        anterior = con.execute(
            "SELECT * FROM snap_cupom WHERE conta_slug = ? AND promocao_id = ? "
            "AND coletado_em < ? ORDER BY coletado_em DESC LIMIT 1",
            (conta.slug, c["promocao_id"], carimbo_novo)).fetchone()

        beneficio = (f"{c['percentual']:.0f}%" if c["percentual"]
                     else brl(c["valor_fixo"]))
        consumo = _cup.consumo(c)

        # ------------------------------------------------ 1. campanha nova
        cfg_novo = _reg(regras, "cupom_novo")
        if cfg_novo and anterior is None:
            quantos = None
            if c["valor_fixo"] and c["orcamento"]:
                quantos = int(float(c["orcamento"]) // float(c["valor_fixo"]))
            codigo = (f"código {c['codigo']}" if c["codigo"] else "aberto a todo mundo")

            # Primeira leitura não quer dizer campanha recém-criada. Cupom
            # existente antes de a coleta começar a olhar — ou criado enquanto
            # a rotina estava parada — chega aqui exatamente igual a um novo,
            # e chamar de "nova" uma campanha que já queimou R$ 1.200 esconde
            # justamente o número que interessa. Quem separa os dois casos é o
            # que a própria campanha já mostra: uso registrado ou dias
            # corridos desde o início.
            dias_correndo = _dias_desde(c["inicio"], c["coletado_em"])
            ja_usou = (c["cupons_usados"] or 0) > 0
            em_curso = ja_usou or (dias_correndo is not None and dias_correndo >= 1)

            if em_curso:
                # Sem "nesta conta" e sem o total de usos que o teto paga: o
                # cabeçalho da mensagem já diz de qual conta é, e logo abaixo
                # vem o uso REAL, que é o número que importa. Cada palavra a
                # mais aqui empurra para fora do limite de 320 a última frase,
                # que é a de quem paga a conta.
                desde = (f" desde {_data_curta(c['inicio'])}" if c["inicio"] else "")
                msg = (f"Campanha de CUPOM em curso{desde}: *{c['nome']}* — "
                       f"{beneficio} por venda, {codigo}, teto de "
                       f"{brl(c['orcamento'])}.")
            else:
                # A mensagem tem 320 caracteres antes de ser cortada no
                # Telegram, e a frase que não pode faltar é a última — a de
                # quem paga a conta.
                msg = (f"Campanha de CUPOM nova: *{c['nome']}* — {beneficio} por "
                       f"venda, {codigo}, teto de {brl(c['orcamento'])}")
                msg += f" (dá {quantos} usos)." if quantos else "."

            if em_curso and consumo["gasto"]:
                msg += (f" Já foram {c['cupons_usados']} usos, "
                        f"{brl(consumo['gasto'])} do teto")
                msg += (f" ({consumo['gasto_pct']:.0f}%"
                        + (f" em {_quantos_dias(dias_correndo)}" if dias_correndo else "")
                        + ").")
                por_dia = (consumo["gasto"] / dias_correndo) if dias_correndo else None
                sobra = _quando_acaba(por_dia, c["orcamento_restante"])
                if sobra is not None and sobra < 30:
                    msg += f" Nessa média o teto acaba {_prazo(sobra)}."

            detalhes = []
            if c["compra_minima"]:
                detalhes.append(f"mínimo de compra {brl(c['compra_minima'])}")
            if c["fim"]:
                detalhes.append(f"vale até {_data_curta(c['fim'])}")
            if detalhes:
                # capitalize() minúsculo o resto da frase e transformava
                # "R$ 200,00" em "r$ 200,00". Só a primeira letra muda.
                frase = ", ".join(detalhes)
                msg += " " + frase[0].upper() + frase[1:] + "."
            msg += (f" O ML não co-participa: sai tudo da conta."
                    if em_curso else
                    f" O ML não co-participa em cupom: os {brl(c['orcamento'])} "
                    f"saem inteiros da conta.")
            alerta("cupom_novo", cfg_novo, msg, titulo=c["nome"],
                   dados={"promocao": c["promocao_id"], "orcamento": c["orcamento"]})

        # -------------------------------------------- 2. orçamento queimando
        cfg_queima = _reg(regras, "cupom_queimando")
        if cfg_queima and anterior is not None and consumo["gasto_pct"] is not None:
            faixas = sorted(cfg_queima.get("faixas_percentuais") or [50, 80, 100])
            antes_pct = _cup.consumo(anterior)["gasto_pct"] or 0.0
            cruzou = [f for f in faixas if antes_pct < f <= consumo["gasto_pct"]]

            horas = _horas_entre(anterior["coletado_em"], c["coletado_em"])
            queimado = (anterior["orcamento_restante"] - c["orcamento_restante"]) \
                if (anterior["orcamento_restante"] is not None
                    and c["orcamento_restante"] is not None) else None
            novos = (c["cupons_usados"] or 0) - (anterior["cupons_usados"] or 0)
            por_dia = (queimado / horas * 24) if (queimado and horas) else None
            dias = _quando_acaba(por_dia, c["orcamento_restante"])

            if cruzou:
                msg = (f"A campanha de cupom *{c['nome']}* já consumiu "
                       f"{consumo['gasto_pct']:.0f}% do teto: "
                       f"{brl(consumo['gasto'])} de {brl(c['orcamento'])}, em "
                       f"{c['cupons_usados']} usos.")
                if dias is not None and dias < 30:
                    msg += (f" No ritmo das últimas {horas:.0f}h "
                            f"({brl(por_dia)}/dia) o teto acaba {_prazo(dias)}.")
                alerta("cupom_queimando", cfg_queima, msg, titulo=c["nome"],
                       dados={"promocao": c["promocao_id"],
                              "pct": consumo["gasto_pct"]})
            elif (novos >= int(cfg_queima.get("usos_por_rodada", 999)) and novos > 0
                    and _passou_o_intervalo(
                        con, f"cupom_ritmo:{conta.slug}:{c['promocao_id']}",
                        c["coletado_em"],
                        int(cfg_queima.get("horas_entre_avisos", 12)))):
                msg = (f"{novos} cupons usados na campanha *{c['nome']}* desde a "
                       f"leitura anterior — {brl(queimado)} do teto em "
                       f"{horas:.0f}h. Restam {brl(c['orcamento_restante'])}.")
                if dias is not None and dias < 15:
                    msg += f" Nesse ritmo acaba {_prazo(dias)}."
                alerta("cupom_queimando", cfg_queima, msg, titulo=c["nome"],
                       dados={"promocao": c["promocao_id"], "novos": novos})

        # ------------------------------------------------- 3. fura o piso
        cfg_piso = _reg(regras, "cupom_fura_o_piso")
        if cfg_piso:
            for p in _cup.anuncios_da_campanha(con, conta.slug, c["promocao_id"]):
                if p["status"] not in ("started", "pending"):
                    continue
                r = pisos.get(p["item_id"])
                if not r or not r["piso"]:
                    continue
                preco = p["preco_vitrine"] or p["preco"]
                com_cupom = _preco_com_cupom(preco, c)
                if com_cupom is None or com_cupom >= r["piso"]:
                    continue
                # Enquanto a campanha durar a condição continua verdadeira, e
                # repetir a mesma frase de 6 em 6 horas por trinta dias é a
                # forma mais rápida de treinar alguém a ignorar o canal. Um
                # aviso por anúncio; volta a avisar se o preço mudar.
                chave = f"cupom_piso:{conta.slug}:{c['promocao_id']}:{p['item_id']}"
                assinatura = f"{round(com_cupom, 2)}|{round(r['piso'], 2)}"
                if db.ler_marcador(con, chave) == assinatura:
                    continue
                db.gravar_marcador(con, chave, assinatura)
                msg = (f"Com o cupom de {beneficio} este anúncio sai por "
                       f"{brl(com_cupom)} — {brl(r['piso'] - com_cupom)} ABAIXO do "
                       f"piso de {brl(r['piso'])}. Na vitrine ele aparece a "
                       f"{brl(preco)} e parece saudável; o desconto só some no "
                       f"checkout, e sai do seu bolso.")
                alerta("cupom_fura_o_piso", cfg_piso, msg,
                       item_id=p["item_id"], titulo=p["titulo"] or p["item_id"],
                       dados={"por_item": True, "promocao": c["promocao_id"],
                              "preco_com_cupom": com_cupom, "piso": r["piso"]})

    return gerados


def avaliar_canibalizacao(con: sqlite3.Connection, cliente, carimbo: str) -> int:
    """
    Regra que só existe para cliente com múltiplas contas: duas contas do
    mesmo dono disputando a mesma palavra-chave com preços diferentes.
    """
    regras = carregar_regras()
    cfg = _reg(regras, "canibalizacao_interna")
    if not cfg or not cliente.coordenar_preco or len(cliente.contas) < 2:
        return 0

    slugs = [c.slug for c in cliente.contas]
    marcas = ",".join("?" for _ in slugs)
    linhas = con.execute(
        f"SELECT termo, conta_slug, item_id, posicao, preco FROM snap_posicao "
        f"WHERE conta_slug IN ({marcas}) AND coletado_em >= datetime(?, '-6 hours')",
        (*slugs, carimbo),
    ).fetchall()

    por_termo: dict[str, list] = {}
    for l in linhas:
        por_termo.setdefault(l["termo"], []).append(l)

    gerados = 0
    for termo, itens in por_termo.items():
        contas_distintas = {i["conta_slug"] for i in itens}
        if len(contas_distintas) < 2:
            continue
        precos = [i["preco"] for i in itens if i["preco"] is not None]
        if not precos:
            continue
        spread = pct(max(precos), min(precos)) or 0

        # Uma linha por CONTA, a mais barata de cada — não uma por medição.
        # Sem isto o mesmo anúncio entra a cada passada e a mensagem cresce
        # sozinha: em 03/09/2026 os alertas deste termo saíram com 5.851
        # caracteres repetindo o mesmo preço dezenas de vezes, e mensagem que
        # ninguém lê é o mesmo que alerta que não existe.
        melhor: dict[str, object] = {}
        for i in itens:
            if i["preco"] is None:
                continue
            atual = melhor.get(i["conta_slug"])
            if atual is None or i["preco"] < atual["preco"]:
                melhor[i["conta_slug"]] = i
        detalhe = " | ".join(
            f"{l['conta_slug']}: {brl(l['preco'])} (pos {l['posicao']})"
            for l in sorted(melhor.values(), key=lambda x: x["preco"]))
        entrou = db.registrar_alerta(
            con,
            cliente_id=cliente.id,
            conta_slug=",".join(sorted(contas_distintas)),
            regra="canibalizacao_interna",
            critico=bool(cfg.get("critico", False)),
            mensagem=f"[{termo}] {len(contas_distintas)} contas do mesmo cliente disputando "
                     f"(diferença de {spread:.1f}%) — {detalhe}",
            titulo=termo,
        )
        if entrou:
            gerados += 1

    con.commit()
    return gerados
