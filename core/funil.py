"""
Motor de funil: em qual degrau um anúncio ATIVO trava, e quanto isso vale
por mês. Não substitui core.diagnostico (saúde de cadastro — pausado, sem
custo, duplicata): funil olha tráfego e conversão de quem já está no ar.

Três degraus, três culpados diferentes — exposição, conversão, teto de
categoria. Sem separar isso, todo diagnóstico vira palpite: um anúncio com
pouca visita e um anúncio com muita visita que não vendem têm doenças
opostas.

Janela padrão de 7 dias porque visitas_7d é a ÚNICA leitura de visita que
existe hoje: soma corrida de 7 dias, de /items/{id}/visits/time_window,
amostrada 1x por dia em core.collectors.coletar_meus_anuncios (a "passada
larga" do vigia). Não é visita por dia exata — é sempre "os últimos 7 dias
até a hora da coleta". Comparar isso com venda de 30 dias descasaria a
janela de quem viu com a janela de quem comprou; por isso os pedidos usados
aqui somam a MESMA janela de `dias`, não um período diferente.

Pares são só INTERNOS (outros anúncios ativos da própria conta, mesma
categoria e faixa de preço ±30%, alargando para a categoria inteira quando
sobra pouco). Comparação com concorrente externo é outra frente
(core.confrontos / vigilância de catálogo) e não entra aqui.

SEM_EXPOSICAO é sempre inferido pelo par interno (visita abaixo do p25),
mas quando existe medição real de posição na busca (snap_posicao, importada
de skills/posicao-na-busca — a API de busca devolve 403, só dá pra medir
pelo navegador) ela entra como causa concreta, na frente das hipóteses sem
dado. É fato lido, não inferência, mesmo que a medição não seja em tempo
real.

SEM_CONVERSAO tem DUAS réguas, não uma. A relativa (abaixo do p25 de
conversão do par) fica cega exatamente no caso que mais importa: se a conta
inteira converte mal, os vizinhos também convertem 0%, o p25 vira 0%, e nada
consegue ficar "abaixo de zero" — o motor conclui "normal" quando na verdade
é "ninguém aqui está convertendo, e isso é um problema do operador, não do
mercado". A régua ABSOLUTA (visita de sobra + zero venda, ver
LIMIAR_VISITAS_SEM_CONVERSAO) não depende de vizinho nenhum e pega esse caso.
As duas rodam sempre que há visita para julgar; o veredito bate se qualquer
uma disparar.
"""
from __future__ import annotations

import sqlite3
import statistics
from collections import defaultdict
from typing import Any

from . import db

JANELA_DIAS_PADRAO = 7
FAIXA_PRECO = 0.30       # ±30%
MINIMO_PAR_ESTREITO = 5  # abaixo disso, alarga para a categoria inteira

# Visita "de sobra" o bastante para que zero venda pare de ser coincidência.
# Não é teste estatístico — é limiar operacional. Mesmo num item de conversão
# baixa (1%), (0,99)^30 ≈ 74% de chance de ainda dar zero venda por acaso, então
# isto marca "vale olhar", não "está provado". Ajustar aqui se virar ruído.
LIMIAR_VISITAS_SEM_CONVERSAO = 30


def _pedidos_por_item(con: sqlite3.Connection, conta_slug: str, dias: int) -> dict[str, int]:
    """
    Pedidos que contêm o item, na janela. É contagem de PEDIDO, não de
    unidade: a coluna `itens` de `venda` guarda os MLB do pedido separados
    por vírgula, sem quantidade por item — mesma leitura que
    core.cupons usa para o denominador de conversão de cupom.
    """
    vivos = "(status IS NULL OR status NOT IN ('cancelled','invalid'))"
    linhas = con.execute(
        f"SELECT itens FROM venda WHERE conta_slug = ? "
        f"AND data_pedido >= datetime('now', ?) AND {vivos}",
        (conta_slug, f"-{dias} days"),
    ).fetchall()
    contagem: dict[str, int] = defaultdict(int)
    for l in linhas:
        for item_id in (l["itens"] or "").split(","):
            item_id = item_id.strip()
            if item_id:
                contagem[item_id] += 1
    return dict(contagem)


def _media_mensal_historica(con: sqlite3.Connection, conta_slug: str,
                            dias_lookback: int = 90) -> dict[str, float]:
    """Pedidos/mês de cada item no histórico disponível — usado para dar
    valor a RUPTURA e PAUSADO, onde não há venda na janela atual por
    definição."""
    contagem = _pedidos_por_item(con, conta_slug, dias_lookback)
    fator = 30 / dias_lookback
    return {item_id: n * fator for item_id, n in contagem.items()}


def _visitas_por_item(con: sqlite3.Connection, conta_slug: str) -> tuple[str | None, dict[str, int]]:
    """Última leitura de visitas_7d de cada item — mesma guarda de recência
    que core.diagnostico usa: o vigia grava NULL nos ciclos curtos, e olhar
    só o snapshot da vez zeraria a conversão de todo mundo."""
    carimbo = con.execute(
        "SELECT MAX(coletado_em) t FROM snap_anuncio "
        "WHERE conta_slug = ? AND visitas_7d IS NOT NULL", (conta_slug,)
    ).fetchone()["t"]
    if not carimbo:
        return None, {}
    linhas = con.execute(
        "SELECT item_id, visitas_7d FROM snap_anuncio "
        "WHERE conta_slug = ? AND coletado_em = ?", (conta_slug, carimbo))
    return carimbo, {l["item_id"]: l["visitas_7d"] for l in linhas}


def _frete_custo_recente(con: sqlite3.Connection, conta_slug: str) -> dict[str, float]:
    """Último frete_custo não nulo — o que o COMPRADOR paga (em frete grátis
    é sempre 0). Medido na mesma passada diária das visitas."""
    linhas = con.execute(
        "SELECT item_id, frete_custo FROM snap_anuncio a "
        "WHERE conta_slug = ? AND frete_custo IS NOT NULL AND coletado_em = ("
        "  SELECT MAX(coletado_em) FROM snap_anuncio "
        "  WHERE conta_slug = a.conta_slug AND item_id = a.item_id "
        "    AND frete_custo IS NOT NULL)",
        (conta_slug,)).fetchall()
    return {l["item_id"]: float(l["frete_custo"]) for l in linhas}


def _promocoes_por_item(con: sqlite3.Connection, conta_slug: str) -> dict[str, set[str]]:
    """Status de campanha vigente por item (candidate | started | pending |
    finished), da última coleta de snap_promocao."""
    ultimo = db.ultima_coleta(con, "snap_promocao", conta_slug)
    saida: dict[str, set[str]] = defaultdict(set)
    if not ultimo:
        return saida
    for l in con.execute(
            "SELECT item_id, status FROM snap_promocao "
            "WHERE conta_slug = ? AND coletado_em = ?", (conta_slug, ultimo)):
        saida[l["item_id"]].add(l["status"])
    return saida


def _posicoes_por_item(con: sqlite3.Connection, conta_slug: str) -> dict[str, list[dict]]:
    """Última medição de posição por (item, termo) em snap_posicao — vinda do
    roteiro skills/posicao-na-busca, lida por um navegador de verdade, não
    pelo vigia de 5 em 5 minutos (a API de busca devolve 403). Um item pode
    estar calibrado em mais de um termo em palavras-chave.yaml, e a posição
    pode divergir entre eles — por isso guarda todas, não só a melhor."""
    linhas = con.execute(
        "SELECT s.item_id, s.termo, s.posicao, s.total_result, s.coletado_em "
        "FROM snap_posicao s JOIN ("
        "  SELECT item_id, termo, MAX(coletado_em) m FROM snap_posicao "
        "  WHERE conta_slug = ? GROUP BY item_id, termo"
        ") u ON u.item_id = s.item_id AND u.termo = s.termo AND u.m = s.coletado_em "
        "WHERE s.conta_slug = ?", (conta_slug, conta_slug)).fetchall()
    saida: dict[str, list[dict]] = defaultdict(list)
    for l in linhas:
        saida[l["item_id"]].append({
            "termo": l["termo"], "posicao": l["posicao"],
            "total_result": l["total_result"], "medido_em": l["coletado_em"],
        })
    return dict(saida)


def _disputados_no_catalogo(con: sqlite3.Connection, conta_slug: str) -> set[str]:
    """Nossos item_id que têm ao menos um confronto de concorrente
    registrado — mesma leitura que core.diagnostico usa."""
    uc = db.ultima_coleta(con, "snap_concorrente", conta_slug)
    if not uc:
        return set()
    return {
        l["comparar_com"] for l in con.execute(
            "SELECT DISTINCT comparar_com FROM snap_concorrente "
            "WHERE conta_slug = ? AND coletado_em = ? AND origem = 'confronto' "
            "AND comparar_com IS NOT NULL", (conta_slug, uc))
    }


def _percentil25(valores: list[float]) -> float | None:
    dados = sorted(v for v in valores if v is not None)
    if len(dados) < 4:
        return None
    return statistics.quantiles(dados, n=4, method="inclusive")[0]


def _sem_conversao_absoluta(visitas: int, pedidos: int) -> bool:
    """Não compara com par nenhum: visita de sobra e zero venda já é
    suspeito por si só, mesmo quando os vizinhos também não vendem nada
    (conta inteira patinando) ou quando não existe par para comparar."""
    return visitas >= LIMIAR_VISITAS_SEM_CONVERSAO and pedidos == 0


def _mediana(valores: list[float]) -> float | None:
    dados = [v for v in valores if v is not None]
    return statistics.median(dados) if dados else None


def _par_de(item: sqlite3.Row, ativos: list[sqlite3.Row]) -> tuple[list[sqlite3.Row], bool]:
    """Mesma categoria e faixa de preço ±30%. Se sobrar menos de
    MINIMO_PAR_ESTREITO, alarga para a categoria inteira."""
    categoria = item["categoria"]
    preco = item["preco"] or 0
    baixo, alto = preco * (1 - FAIXA_PRECO), preco * (1 + FAIXA_PRECO)
    estreito = [a for a in ativos if a["categoria"] == categoria and baixo <= (a["preco"] or 0) <= alto]
    if len(estreito) >= MINIMO_PAR_ESTREITO:
        return estreito, False
    amplo = [a for a in ativos if a["categoria"] == categoria]
    return amplo, True


def _preco_efetivo(item: sqlite3.Row, frete_por_item: dict[str, float]) -> float | None:
    preco = item["preco"]
    if preco is None:
        return None
    if item["frete_gratis"]:
        return float(preco)
    custo = frete_por_item.get(item["item_id"])
    return float(preco) + (custo or 0.0)


def _tipo_dominante(itens: list[sqlite3.Row]) -> str | None:
    contagem: dict[str, int] = defaultdict(int)
    for i in itens:
        if i["tipo_anuncio"]:
            contagem[i["tipo_anuncio"]] += 1
    if not contagem:
        return None
    return max(contagem, key=contagem.get)


def _causas_sem_exposicao(item, par, disputados, promo_por_item, posicoes_por_item) -> list[dict]:
    causas = []

    # Posição real (medida por navegador, skills/posicao-na-busca) é fato,
    # não inferência de par interno — entra na frente das causas abaixo.
    # Quando não existe medição, a causa não vira "sem dado" como foto/
    # avaliação: aqui existe caminho pra conseguir o dado, então a causa
    # aponta pra ele em vez de virar beco sem saída.
    medicoes = posicoes_por_item.get(item["item_id"]) or []
    if medicoes:
        for m in medicoes:
            if m["posicao"] is None:
                continue
            total = m["total_result"] if m["total_result"] is not None else "?"
            causas.insert(0, {
                "causa": f"posição real na busca: {m['posicao']}º de {total} para \"{m['termo']}\"",
                "evidencia": f"medido em {m['medido_em']} via skills/posicao-na-busca "
                             f"— não é leitura em tempo real, é medição manual",
            })
    else:
        causas.append({
            "causa": "posição na busca ainda não medida",
            "evidencia": "rodar skills/posicao-na-busca para este item/termo — "
                         "a API de busca do ML devolve 403, só dá pra medir pelo navegador",
        })

    if not item["catalogo"] and any(p["catalogo"] for p in par):
        pct_par = sum(1 for p in par if p["catalogo"]) / len(par) * 100
        causas.append({
            "causa": "fora do catálogo",
            "evidencia": f"{pct_par:.0f}% dos pares está em catálogo, este não está",
        })
    elif item["catalogo"] and item["item_id"] not in disputados:
        causas.append({
            "causa": "catálogo sem concorrente monitorado",
            "evidencia": "sem dado de buy box — checar com o confronto de "
                         "catálogo (core.confrontos / ml-concorrencia), fora do escopo deste motor",
        })

    dominante = _tipo_dominante(par)
    if dominante and item["tipo_anuncio"] and item["tipo_anuncio"] != dominante:
        pct = sum(1 for p in par if p["tipo_anuncio"] == dominante) / len(par) * 100
        if pct >= 60:
            causas.append({
                "causa": f"{item['tipo_anuncio']} onde o par é majoritariamente {dominante}",
                "evidencia": f"{pct:.0f}% do par é {dominante}",
            })

    if not item["frete_gratis"] and par:
        pct_gratis = sum(1 for p in par if p["frete_gratis"]) / len(par) * 100
        if pct_gratis >= 60:
            causas.append({
                "causa": "sem frete grátis onde o par tem",
                "evidencia": f"{pct_gratis:.0f}% do par tem frete grátis",
            })

    status_par = set()
    for p in par:
        status_par |= promo_por_item.get(p["item_id"], set())
    status_proprio = promo_por_item.get(item["item_id"], set())
    if "started" in status_par and not status_proprio:
        causas.append({
            "causa": "fora de promoção onde o par está dentro",
            "evidencia": "há par com campanha 'started' e este item não tem nenhuma campanha registrada",
        })

    causas.append({"causa": "atributos obrigatórios em branco", "evidencia": "sem dado"})
    causas.append({"causa": "título sem os termos dos pares que vendem", "evidencia": "sem dado"})
    return causas


def _causas_sem_conversao(item, par, frete_por_item, promo_por_item) -> list[dict]:
    causas = []
    precos_par = [_preco_efetivo(p, frete_por_item) for p in par if p["item_id"] != item["item_id"]]
    mediana_par = _mediana(precos_par)
    preco_proprio = _preco_efetivo(item, frete_por_item)
    if mediana_par and preco_proprio and preco_proprio > mediana_par:
        gap_reais = preco_proprio - mediana_par
        gap_pct = gap_reais / mediana_par * 100
        causas.append({
            "causa": "preço efetivo acima da mediana do par",
            "evidencia": f"R$ {gap_reais:.2f} ({gap_pct:.1f}%) acima da mediana do par",
        })

    if "started" in promo_por_item.get(item["item_id"], set()):
        causas.append({
            "causa": "já tem desconto ativo e mesmo assim não converte",
            "evidencia": "campanha com status 'started' neste item — o problema não é preço",
        })

    causas.append({"causa": "prazo de entrega maior que o do par", "evidencia": "sem dado"})
    causas.append({"causa": "menos fotos ou capa fora do padrão", "evidencia": "sem dado"})
    causas.append({"causa": "sem avaliação ou nota abaixo do par", "evidencia": "sem dado"})
    return causas


def _avaliar_item(item, ativos, visitas_por_item, pedidos_por_item, frete_por_item,
                  disputados, promo_por_item, posicoes_por_item, media_mensal, dias) -> dict:
    """
    Devolve o veredito, as causas prováveis, e `receita_bruta_perdida_mes` —
    faturamento, ainda SEM descontar comissão. Quem chama (`analisar`) aplica
    a margem líquida por cima quando a tarifa real do anúncio está medida;
    quando não está, o valor bruto fica de pé mesmo assim (é fato, não chute)
    e o resultado sai marcado como `liquido=False`.
    """
    item_id = item["item_id"]
    visitas = visitas_por_item.get(item_id) or 0
    pedidos = pedidos_por_item.get(item_id, 0)
    conversao = (pedidos / visitas) if visitas else None
    preco = item["preco"] or 0

    resultado: dict[str, Any] = {
        "item_id": item_id, "titulo": item["titulo"], "sku": item["sku"],
        "status": item["status"], "estoque": item["estoque"], "preco": item["preco"],
        "visitas": visitas, "pedidos": pedidos, "conversao": conversao,
        "causas": [], "par_alargado": None, "tamanho_par": None,
        "receita_bruta_perdida_mes": None,
    }

    if (item["estoque"] or 0) <= 0 and item["status"] == "active":
        resultado["veredito"] = "RUPTURA"
        historico = media_mensal.get(item_id)
        resultado["receita_bruta_perdida_mes"] = historico * preco if historico else None
        resultado["causas"] = [{
            "causa": "sem estoque com anúncio ainda ativo",
            "evidencia": f"média histórica de {historico:.1f} pedidos/mês" if historico else "sem histórico de venda",
        }]
        return resultado

    if item["status"] != "active":
        resultado["veredito"] = "PAUSADO"
        historico = media_mensal.get(item_id)
        resultado["receita_bruta_perdida_mes"] = historico * preco if historico else None
        resultado["causas"] = [{
            "causa": f"status {item['status']}" + (f" ({item['sub_status']})" if item["sub_status"] else ""),
            "evidencia": f"média histórica de {historico:.1f} pedidos/mês" if historico else "sem histórico de venda",
        }]
        return resultado

    sem_conversao_abs = _sem_conversao_absoluta(visitas, pedidos)

    par, alargado = _par_de(item, ativos)
    resultado["par_alargado"] = alargado
    resultado["tamanho_par"] = len(par)

    if len(par) < 2:
        if sem_conversao_abs:
            resultado["veredito"] = "SEM_CONVERSAO"
            resultado["causas"] = _causas_sem_conversao(item, par, frete_por_item, promo_por_item)
            resultado["causas"].insert(0, {
                "causa": "regra absoluta: visita de sobra sem nenhuma venda",
                "evidencia": f"{visitas} visitas na janela de {dias} dias e 0 pedidos — "
                             f"sem outro anúncio na conta pra comparar, mas o volume de "
                             f"visita já torna zero venda um sinal por si só",
            })
            historico = media_mensal.get(item_id)
            resultado["receita_bruta_perdida_mes"] = historico * preco if historico else None
            resultado["causas"].append({
                "causa": "valor estimado pelo histórico do próprio item",
                "evidencia": (f"média histórica de {historico:.1f} pedidos/mês"
                              if historico else "sem histórico de venda — valor não calculado"),
            })
            return resultado
        resultado["veredito"] = "SEM_PAR_SUFICIENTE"
        resultado["causas"] = [{"causa": "sem outro anúncio comparável na conta", "evidencia": "sem dado"}]
        return resultado

    visitas_par = [visitas_por_item.get(p["item_id"]) or 0 for p in par]
    p25_visitas = _percentil25(visitas_par)
    conv_par = [
        (pedidos_por_item.get(p["item_id"], 0) / (visitas_por_item.get(p["item_id"]) or 1))
        for p in par if (visitas_por_item.get(p["item_id"]) or 0) > 0
    ]
    p25_conv = _percentil25(conv_par)

    if visitas == 0 or (p25_visitas is not None and visitas < p25_visitas):
        resultado["veredito"] = "SEM_EXPOSICAO"
        resultado["causas"] = _causas_sem_exposicao(item, par, disputados, promo_por_item, posicoes_por_item)
        # se este anúncio tivesse o volume de visita típico do par (p25) e
        # convertesse na taxa típica do par, faturaria isto a mais por mês.
        if p25_visitas is not None and p25_conv is not None:
            deficit_visitas_mes = max(p25_visitas - visitas, 0) * (30 / dias)
            resultado["receita_bruta_perdida_mes"] = deficit_visitas_mes * p25_conv * preco
        return resultado

    sem_conversao_rel = p25_conv is not None and conversao is not None and conversao < p25_conv

    if sem_conversao_rel or sem_conversao_abs:
        resultado["veredito"] = "SEM_CONVERSAO"
        resultado["causas"] = _causas_sem_conversao(item, par, frete_por_item, promo_por_item)
        if sem_conversao_abs and not sem_conversao_rel:
            # o par existe, mas não discrimina nada (p25 de conversão do par
            # também é 0 ou não calculável) — provável conta/categoria inteira
            # patinando, não só este item. A régua relativa fica cega aqui de
            # propósito; é para isso que a absoluta existe.
            p25_txt = f"{p25_conv:.1%}" if p25_conv is not None else "não calculável"
            resultado["causas"].insert(0, {
                "causa": "regra absoluta: visita de sobra sem nenhuma venda",
                "evidencia": f"{visitas} visitas na janela e 0 pedidos — o p25 de "
                             f"conversão do par é {p25_txt} (não discrimina; "
                             f"provável conta ou categoria inteira sem converter)",
            })
        if sem_conversao_rel:
            visitas_mes = visitas * (30 / dias)
            gap_conv = p25_conv - conversao
            resultado["receita_bruta_perdida_mes"] = gap_conv * visitas_mes * preco
        else:
            # regra absoluta sozinha: não há gap de conversão do par pra medir
            # em cima, então o valor vem do próprio histórico do item — visível
            # como causa, não só escondido dentro do número.
            historico = media_mensal.get(item_id)
            resultado["receita_bruta_perdida_mes"] = historico * preco if historico else None
            resultado["causas"].append({
                "causa": "valor estimado pelo histórico do próprio item",
                "evidencia": (f"média histórica de {historico:.1f} pedidos/mês"
                              if historico else "sem histórico de venda — valor não calculado"),
            })
        return resultado

    receitas_par = [pedidos_por_item.get(p["item_id"], 0) * (p["preco"] or 0) for p in par]
    p25_receita = _percentil25(receitas_par)
    receita_propria = pedidos * preco
    if p25_receita is not None and receita_propria < p25_receita:
        resultado["veredito"] = "TETO_DE_CATEGORIA"
        resultado["causas"] = [{
            "causa": "converte dentro do esperado, mas a categoria/faixa de preço vende pouco",
            "evidencia": f"receita da janela R$ {receita_propria:.2f} abaixo do p25 do par (R$ {p25_receita:.2f})",
        }]
        resultado["receita_bruta_perdida_mes"] = 0.0
        return resultado

    resultado["veredito"] = "SAUDAVEL"
    resultado["receita_bruta_perdida_mes"] = 0.0
    return resultado


def analisar(con: sqlite3.Connection, conta_slug: str, dias: int = JANELA_DIAS_PADRAO,
            item_filtro: str | None = None) -> dict:
    ultimo = db.ultima_coleta(con, "snap_anuncio", conta_slug)
    if not ultimo:
        return {"erro": "sem coleta"}

    todos = con.execute(
        "SELECT * FROM snap_anuncio WHERE conta_slug = ? AND coletado_em = ?",
        (conta_slug, ultimo)).fetchall()
    if not todos:
        return {"erro": "sem coleta"}

    carimbo_visitas, visitas_por_item = _visitas_por_item(con, conta_slug)
    if not carimbo_visitas:
        return {"erro": "sem leitura de visita ainda — a passada larga do vigia roda 1x/dia"}

    pedidos_por_item = _pedidos_por_item(con, conta_slug, dias)
    frete_por_item = _frete_custo_recente(con, conta_slug)
    disputados = _disputados_no_catalogo(con, conta_slug)
    promo_por_item = _promocoes_por_item(con, conta_slug)
    posicoes_por_item = _posicoes_por_item(con, conta_slug)
    media_mensal = _media_mensal_historica(con, conta_slug)
    tarifas = db.tarifas_medidas(con, conta_slug)

    ativos = [a for a in todos if a["status"] == "active"]

    resultados = []
    for item in todos:
        if item_filtro and item["item_id"] != item_filtro:
            continue
        r = _avaliar_item(item, ativos, visitas_por_item, pedidos_por_item, frete_por_item,
                          disputados, promo_por_item, posicoes_por_item, media_mensal, dias)

        # A tarifa REAL medida (não a do conta.yaml) vira margem líquida por
        # cima do bruto, quando existe. Sem ela, o valor bruto fica de pé —
        # é fato (pedidos × preço), não inferência — só marcado como bruto.
        medida = tarifas.get(item["item_id"])
        bruto = r.pop("receita_bruta_perdida_mes")
        if bruto is not None and medida and medida.get("taxa_pct") is not None:
            taxa = float(medida["taxa_pct"])
            taxa = taxa / 100 if taxa > 1 else taxa
            r["receita_perdida_mes"] = bruto * (1 - taxa)
            r["liquido"] = True
        else:
            r["receita_perdida_mes"] = bruto
            r["liquido"] = False
        resultados.append(r)

    resultados.sort(key=lambda r: (r["receita_perdida_mes"] is None, -(r["receita_perdida_mes"] or 0)))
    total_em_jogo = sum(r["receita_perdida_mes"] or 0 for r in resultados)

    return {
        "carimbo": ultimo, "carimbo_visitas": carimbo_visitas, "janela_dias": dias,
        "total_em_jogo": total_em_jogo, "itens": resultados,
    }


def texto_resumo(r: dict, limite: int = 10) -> str:
    if r.get("erro"):
        return f"*Funil* — {r['erro']}."

    L = [f"*Funil — janela de {r['janela_dias']} dias*", ""]
    L.append(f"Total em jogo no mês: R$ {r['total_em_jogo']:.2f}")
    L.append("")

    por_veredito: dict[str, int] = defaultdict(int)
    for i in r["itens"]:
        por_veredito[i["veredito"]] += 1
    L.append(" · ".join(f"{v}: {n}" for v, n in por_veredito.items()))
    L.append("")

    for i in r["itens"][:limite]:
        if (i["receita_perdida_mes"] or 0) <= 0 and i["veredito"] in ("SAUDAVEL", "TETO_DE_CATEGORIA"):
            continue
        if i["receita_perdida_mes"] is not None:
            sufixo = "" if i.get("liquido") else " (bruto, sem tarifa medida)"
            valor = f"R$ {i['receita_perdida_mes']:.2f}/mês{sufixo}"
        else:
            valor = "sem valor calculado"
        L.append(f"🔴 [{i['veredito']}] {i['titulo'][:50]} — {valor}")
        for c in i["causas"][:3]:
            L.append(f"    · {c['causa']}: {c['evidencia']}")
    return "\n".join(L)
