"""
Uma página por loja: o que sobra, o que as campanhas fazem com isso, e o frete.

O painel comparativo (scripts/painel_metricas.py) responde "como vão as
contas". Este responde "o que fazer nesta conta hoje", e por isso é um arquivo
por loja — o operador abre a da loja em que está trabalhando.

Só lê o banco e a planilha de custo da conta. Não chama a API do ML.

    .venv\\Scripts\\python.exe scripts\\painel_loja.py                     # todas
    .venv\\Scripts\\python.exe scripts\\painel_loja.py enio-toldos-principal

Sai em relatorios/loja-<slug>.html.

As réguas NÃO moram aqui: piso e margem vêm de core/precificacao.py, o
veredito de campanha vem de core/promocoes.py. Esta página só desenha.
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import statistics
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core import db, precificacao, promocoes  # noqa: E402
from core.config import obter_conta  # noqa: E402
from core.painel_visual import (  # noqa: E402
    TZ, barra, chip, data_curta, dias_ate, e, pagina, pct, rs, vazio,
)
from datetime import datetime  # noqa: E402

PADRAO = ["enio-toldos-principal", "facilita-brasil-principal", "facilita-decoralli"]

# O painel comparativo publicado. Fica como URL e não como caminho relativo
# porque a página é lida nos dois lugares — aberta do disco pelo .bat e como
# artifact — e a URL funciona nos dois; o caminho relativo, só num.
VITRINE = "https://claude.ai/code/artifact/c79f1632-8802-461d-a19d-8f37c4372992"

# Modo de envio como o vendedor conhece. 'not_specified' não é um modo: é a
# ausência de um, e num anúncio ativo isso costuma ser cadastro pela metade.
MODOS = {
    "me2": "Mercado Envios",
    "xd_drop_off": "Envios · agência",
    "cross_docking": "Envios · coleta",
    "drop_off": "Envios · postagem",
    "fulfillment": "Full",
    "custom": "Combinar com o comprador",
    "not_specified": "Sem modo definido",
}


# ----------------------------------------------------------------------
# Coleta
# ----------------------------------------------------------------------
def _margem_efetiva(r: dict) -> float | None:
    """
    Margem que sobra no preço de hoje, na MESMA fórmula do piso.

        piso = (custo + frete - rebate) / (1 - comissao - imposto - margem)
      =>  margem(P) = 1 - comissao - imposto - (custo + frete - rebate)/P

    Derivar daqui, e não recalcular por fora, é o que garante que a margem
    mostrada e o 'abaixo do piso' nunca discordem.
    """
    preco = r.get("preco")
    if not preco:
        return None
    liquido = r["custo_total"] + r["frete_absorvido"] - r["rebate"]
    return (1 - r["comissao"] - r["imposto"] - liquido / preco) * 100


def dados(con: sqlite3.Connection, slug: str) -> dict:
    con.row_factory = sqlite3.Row
    conta = obter_conta(slug)
    d: dict = {"slug": slug, "nome": conta.nome_conta or slug, "conta": conta}

    linha = con.execute(
        "SELECT * FROM snap_conta WHERE conta_slug = ? ORDER BY coletado_em DESC LIMIT 1",
        (slug,)).fetchone()
    d["saude"] = dict(linha) if linha else {}

    carimbo = db.ultima_coleta(con, "snap_anuncio", slug)
    d["carimbo"] = carimbo
    ativos = {
        r["item_id"]: r for r in con.execute(
            "SELECT * FROM snap_anuncio WHERE conta_slug = ? AND coletado_em = ? "
            "AND status = 'active'", (slug, carimbo))
    } if carimbo else {}
    d["ativos"] = ativos

    # Todos os status (ativo, pausado, em revisão...) da última coleta — usado
    # pela seção "Todos os produtos", que não é sobre o que está vendendo agora
    # e sim sobre o catálogo inteiro.
    d["todos"] = {
        r["item_id"]: r for r in con.execute(
            "SELECT * FROM snap_anuncio WHERE conta_slug = ? AND coletado_em = ? "
            "AND status != 'closed'", (slug, carimbo))
    } if carimbo else {}

    # --- lucro ---
    caminho = precificacao.caminho_da_planilha(conta)
    d["planilha"] = caminho.name if caminho else None
    d["idade_planilha"] = precificacao.idade_da_planilha(caminho) if caminho else None
    margens_todas = precificacao.carregar(con, conta)
    for r in margens_todas:
        r["margem"] = _margem_efetiva(r)
        r["lucro"] = (r["margem"] / 100 * r["preco"]) if r["margem"] is not None and r["preco"] else None
    d["margens_por_item"] = {r["item_id"]: r for r in margens_todas}
    margens = [r for r in margens_todas if r["item_id"] in ativos]
    d["margens"] = margens
    d["piso_por_item"] = {r["item_id"]: r["piso"] for r in margens}
    d["alvo"] = margens[0]["margem_alvo"] * 100 if margens else None
    d["abaixo"] = sorted((r for r in margens if r["abaixo_do_piso"]),
                         key=lambda r: r["margem"] if r["margem"] is not None else 0)
    folgas = [r["margem"] for r in margens if r["margem"] is not None]
    d["margem_mediana"] = statistics.median(folgas) if folgas else None
    d["sem_frete_medido"] = sum(1 for r in margens if not r["frete_absorvido"])

    # SKU ativo que a planilha não cobre. Vira pedido ao cliente, não estimativa:
    # sem custo o piso não existe, e sem piso a campanha entra às cegas.
    com_custo = {r["item_id"] for r in margens}
    faltantes: dict[str, str] = {}
    for item_id, r in ativos.items():
        if item_id in com_custo:
            continue
        faltantes.setdefault((r["sku"] or "").strip() or f"(sem SKU) {item_id}", r["titulo"])
    d["sem_custo"] = faltantes

    # --- campanhas ---
    # A leitura de campanha é por RODÍZIO, igual à do frete: o carimbo mais
    # recente da tabela é uma passada PARCIAL. Filtrar por ele mostrava "3
    # abertas, 11 rodando" numa conta com 260 e 354 (FACILITA, 03/09/2026).
    por_item = promocoes.ultimas_por_item(con, slug)
    promos = [p for lista in por_item.values() for p in lista]
    d["por_item"] = por_item
    abertas, rodando = [], []
    for p in promos:
        anuncio = ativos.get(p["item_id"])
        preco_hoje = anuncio["preco"] if anuncio else None
        v = promocoes.veredito(p, d["piso_por_item"].get(p["item_id"]), preco_hoje)
        registro = {
            "item_id": p["item_id"],
            "titulo": anuncio["titulo"] if anuncio else p["item_id"],
            "campanha": promocoes.nome_legivel(p),
            "tipo": p["tipo"], "status": p["status"], "fim": p["fim"],
            "preco_hoje": preco_hoje, "piso": d["piso_por_item"].get(p["item_id"]),
            "minimo": p["preco_minimo"], **v,
        }
        (abertas if p["status"] == "candidate" else rodando).append(registro)
    d["abertas"] = sorted(abertas, key=lambda r: (r["cabe"] is not False, r["fim"] or "9"))
    d["rodando"] = sorted(rodando, key=lambda r: (r["cabe"] is not False, r["fim"] or "9"))

    # Uma campanha por anúncio: quem fica e quem sai. A régra mora em
    # core/promocoes.consolidar — aqui só se junta com título e venda.
    consolidacao = []
    for item_id, lista in por_item.items():
        anuncio = ativos.get(item_id)
        if not anuncio:
            continue
        plano = promocoes.consolidar(lista, d["piso_por_item"].get(item_id))
        if not plano:
            continue
        plano.update({"item_id": item_id, "titulo": anuncio["titulo"],
                      "vendidos": anuncio["vendidos"] or 0,
                      "cheio": anuncio["preco"],
                      "piso": d["piso_por_item"].get(item_id)})
        consolidacao.append(plano)
    d["consolidacao"] = consolidacao

    # --- frete ---
    modos: dict[str, int] = {}
    for r in ativos.values():
        modos[r["envio_modo"] or "not_specified"] = modos.get(r["envio_modo"] or "not_specified", 0) + 1
    d["modos"] = sorted(modos.items(), key=lambda kv: -kv[1])
    # A medição vem do rodízio, então tem de vir da última leitura não nula de
    # cada anúncio — não da coluna do snapshot da vez, que é nula na maioria.
    medidos = db.fretes_recentes(con, slug)
    d["frete_por_item"] = medidos
    d["paga_frete"] = [r for r in ativos.values() if r["frete_gratis"]]
    d["frete_medido"] = [r for r in d["paga_frete"] if medidos.get(r["item_id"])]
    d["sem_modo"] = [r for r in ativos.values() if (r["envio_modo"] or "not_specified") == "not_specified"]

    # --- família (agrupamento cosmético, não é regra de piso) ---
    # A planilha de custo desta conta guarda o nome da família na coluna de
    # observação ("custo facilitaa.xlsx — Poltrona Benny"). Não é schema
    # formal, é best-effort: produto sem essa coluna preenchida fica sem
    # família, e isso não afeta piso nem margem.
    familias_por_sku = _familias_da_planilha(caminho) if caminho else {}
    d["familia_por_item"] = {
        item_id: familias_por_sku.get(_normalizar_sku(r["sku"] or ""))
        for item_id, r in d["todos"].items() if r["sku"]
    }
    return d


def _normalizar_sku(texto: str) -> str:
    """Mesma normalização de core.precificacao._so_alfanumerico, para casar
    SKU com a família lida da planilha (hífen/acento/caixa não distinguem)."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", str(texto or ""))
        if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]", "", sem_acento).upper()


def _familias_da_planilha(caminho: Path) -> dict[str, str]:
    """SKU normalizado -> família, lida da coluna de observação da planilha.

    Só CSV; XLSX devolve vazio (a família fica em branco na tabela, não é
    erro). O texto esperado é "qualquer coisa — Nome Da Família"; sem "—",
    a linha não tem família reconhecível.
    """
    if caminho.suffix.lower() != ".csv":
        return {}
    texto = caminho.read_text(encoding="utf-8-sig", errors="replace")
    amostra = texto[:2000]
    separador = ";" if amostra.count(";") > amostra.count(",") else ","
    leitor = csv.DictReader(texto.splitlines(), delimiter=separador)
    saida: dict[str, str] = {}
    for linha in leitor:
        sku = obs = None
        for k, v in linha.items():
            chave = (k or "").strip().lower()
            if chave == "sku":
                sku = v
            elif "observ" in chave:
                obs = v
        if not sku or not obs or "—" not in obs:
            continue
        familia = obs.split("—")[-1].strip()
        if not familia or familia.upper().startswith("SEM CUSTO"):
            continue
        saida[_normalizar_sku(sku)] = familia
    return saida


# ----------------------------------------------------------------------
# Blocos
# ----------------------------------------------------------------------
def _kpi(valor: str, rotulo: str, tom: str = "", nota: str = "") -> str:
    classe = f" kpi__n--{tom}" if tom else ""
    extra = f'<span class="kpi__nota">{e(nota)}</span>' if nota else ""
    return (f'<div class="kpi"><span class="kpi__n{classe}">{valor}</span>'
            f'<span class="kpi__r">{e(rotulo)}</span>{extra}</div>')


def bloco_lucro(d: dict) -> str:
    if not d["margens"]:
        return ('<section class="secao"><h2>O que sobra</h2>'
                + vazio("Nenhum anúncio ativo com custo cadastrado. "
                        "Rode `cli.py precos <slug>` para gerar a lista a pedir ao cliente.")
                + "</section>")

    n, ativos = len(d["margens"]), len(d["ativos"])
    cobertura = n / ativos * 100 if ativos else 0
    abaixo = d["abaixo"]
    tom_abaixo = "critico" if abaixo else "bom"

    # A ressalva que muda a leitura de tudo: sem frete medido, o que aparece
    # como margem é o melhor caso, não o resultado.
    teto = d["sem_frete_medido"] == n
    aviso = ""
    if teto:
        aviso = ('<p class="aviso aviso--atencao"><b>Toda margem desta página é teto.</b> '
                 'Nenhum dos anúncios tem o frete que a loja absorve medido, e móvel '
                 'volumoso com frete grátis tira isso da margem. O número real é menor — '
                 'quanto menor, ainda não dá para dizer.</p>')
    elif d["sem_frete_medido"]:
        aviso = (f'<p class="aviso aviso--atencao">{d["sem_frete_medido"]} dos {n} anúncios '
                 f'entram na conta sem frete medido: nesses, a margem é teto.</p>')

    if d["sem_custo"]:
        amostra = "".join(
            f'<li><span class="mono">{e(sku)}</span> <small>{e(titulo[:58])}</small></li>'
            for sku, titulo in list(d["sem_custo"].items())[:8])
        resto = (f'<p class="micro">e mais {len(d["sem_custo"]) - 8} SKU(s).</p>'
                 if len(d["sem_custo"]) > 8 else "")
        aviso += (f'<div class="aviso aviso--atencao">'
                  f'<b>{len(d["sem_custo"])} SKU(s) ativos fora da planilha de custo.</b> '
                  f'Sem custo não há piso, e sem piso a campanha desses anúncios entra às cegas. '
                  f'Peça estes ao cliente:<ul class="lista-sku">{amostra}</ul>{resto}</div>')

    idade = d["idade_planilha"]
    if idade is not None and idade > precificacao.IDADE_MAXIMA_DIAS:
        aviso += (f'<p class="aviso aviso--critico"><b>A planilha de custo tem {idade} dias.</b> '
                  f'Acima de {precificacao.IDADE_MAXIMA_DIAS} dias o custo não vale como base '
                  f'de decisão — peça a atualizada antes de mexer em preço.</p>')

    linhas = "".join(f"""
<tr>
  <td class="titulo">{e(r['titulo'])}<br><small class="mono">{e(r['item_id'])}</small></td>
  <td class="num">R$ {rs(r['preco'], 2)}</td>
  <td class="num">R$ {rs(r['piso'], 2)}</td>
  <td class="num"><span class="tom-critico">{pct(r['margem'], 1, sinal=True)}</span></td>
  <td class="num tom-critico">R$ {rs(r['lucro'], 2)}</td>
  <td class="num">R$ {rs(r['piso'] - r['preco'], 2)}</td>
</tr>""" for r in abaixo[:12])

    tabela = f"""
    <h3>Vendendo abaixo do piso</h3>
    <p class="intro">Cada venda aqui sai com menos margem do que a conta exige — na
    última coluna, quanto o preço teria de subir para encostar no piso.</p>
    <div class="rolagem"><table class="tabela">
      <thead><tr><th>Anúncio</th><th>Preço hoje</th><th>Piso</th>
      <th>Margem</th><th>Lucro/venda</th><th>Falta subir</th></tr></thead>
      <tbody>{linhas}</tbody>
    </table></div>
    {f'<p class="micro">e mais {len(abaixo) - 12} anúncios abaixo do piso.</p>' if len(abaixo) > 12 else ''}
    """ if abaixo else (
        '<h3>Nenhum anúncio abaixo do piso</h3>'
        '<p class="intro">Todos os anúncios com custo cadastrado estão vendendo '
        'acima do piso de margem da conta.</p>')

    return f"""
<section class="secao">
  <h2>O que sobra</h2>
  <p class="intro">Piso, margem e lucro saem do mesmo motor que o
  <code>cli.py precos</code> usa, com a comissão <b>medida</b> por anúncio —
  não a estimada do conta.yaml.</p>
  <div class="kpis">
    {_kpi(f"{n}<small>/{ativos}</small>", "com custo cadastrado", nota=f"{cobertura:.0f}% dos ativos")}
    {_kpi(str(len(abaixo)), "abaixo do piso", tom=tom_abaixo)}
    {_kpi(pct(d['margem_mediana']), "margem mediana", nota=f"alvo da conta: {pct(d['alvo'], 0)}")}
    {_kpi(f"R$ {rs(statistics.median([r['lucro'] for r in d['margens'] if r['lucro'] is not None]), 0)}"
          if any(r['lucro'] is not None for r in d['margens']) else "—", "lucro mediano por venda")}
  </div>
  {aviso}
  {tabela}
</section>"""


# Teto de linhas nas tabelas longas. A leitura por anúncio (e não pelo carimbo
# parcial do rodízio) trouxe a conta inteira: a FACILITA saltou de 11 para 366
# campanhas rodando, e a página de 40 KB para 406 KB. Tabela de 366 linhas não
# se lê — o que importa é o topo, ordenado por quem fura o piso primeiro.
TETO_LINHAS = 24


def bloco_campanhas(d: dict) -> str:
    def tabela(registros: list[dict], rodando: bool) -> str:
        if not registros:
            return vazio("Nenhuma campanha nesta situação na última coleta.")
        total = len(registros)
        registros = registros[:TETO_LINHAS]
        linhas = []
        for r in registros:
            # Esta linha vem de snap_promocao, lida por rodízio — pode ser uma
            # campanha que já saiu ou nunca foi a mais barata. Se o preço dela
            # não bate com o preço de hoje do anúncio (snap_anuncio, sempre
            # fresco), o veredito não reflete a realidade: não é "fura o
            # piso" nem "cabe no piso" agora, é leitura velha.
            desatualizada = (rodando and r["preco_hoje"] is not None and r["preco"] is not None
                             and abs(r["preco_hoje"] - r["preco"]) > 0.02)
            if desatualizada:
                selo, tom = chip("leitura desatualizada", "neutro"), "neutro"
            elif r["cabe"] is True:
                selo, tom = chip("cabe no piso", "bom"), "bom"
            elif r["cabe"] is False:
                selo, tom = chip("fura o piso", "critico"), "critico"
            else:
                selo, tom = chip(r["conclusao"], "neutro"), "neutro"

            prazo = dias_ate(r["fim"])
            if prazo is None:
                col_prazo = '<span class="tom-fraco">sem prazo</span>'
            elif prazo < 0:
                col_prazo = chip("vencida", "neutro")
            else:
                col_prazo = (f'{data_curta(r["fim"])} '
                             f'<small>{"hoje" if prazo == 0 else f"em {prazo}d"}</small>')
                if prazo <= 2:
                    col_prazo = f'<span class="tom-atencao">{col_prazo}</span>'

            queda = r.get("queda_pct")
            linhas.append(f"""
<tr>
  <td class="titulo">{e(r['titulo'])}<br><small class="mono">{e(r['item_id'])}</small></td>
  <td>{e(r['campanha'])}<br><small>{e(r['tipo'])}</small></td>
  <td class="num">R$ {rs(r['preco_hoje'], 2)}</td>
  <td class="num"><b>R$ {rs(r['preco'], 2)}</b>{f'<br><small>−{pct(queda, 0)}</small>' if queda else ''}</td>
  <td class="num">R$ {rs(r['piso'], 2)}</td>
  <td class="num tom-{tom}">{f"R$ {rs(r['sobra'], 2)}" if r['sobra'] is not None else '—'}</td>
  <td>{selo}</td>
  <td>{col_prazo}</td>
</tr>""")
        resto = (f'<p class="micro">e mais {total - TETO_LINHAS} campanha(s) nesta '
                 f'situação — a ordem põe quem fura o piso primeiro.</p>'
                 if total > TETO_LINHAS else '')
        return f"""<div class="rolagem"><table class="tabela">
      <thead><tr><th>Anúncio</th><th>Campanha</th><th>Preço hoje</th>
      <th>{'Preço na campanha' if rodando else 'Preço proposto'}</th>
      <th>Piso</th><th>Sobra</th><th>Veredito</th><th>Termina</th></tr></thead>
      <tbody>{''.join(linhas)}</tbody></table></div>{resto}"""

    # Só conta como "fura o piso de verdade" quem tem o preço da campanha
    # batendo com o preço de hoje do anúncio — senão é leitura desatualizada
    # do rodízio, não um problema real (ver 'desatualizada' dentro de tabela()).
    def _valendo_e_fura(r) -> bool:
        return (r["cabe"] is False and r["preco_hoje"] is not None and r["preco"] is not None
               and abs(r["preco_hoje"] - r["preco"]) <= 0.02)

    furam_total = sum(1 for r in d["rodando"] if r["cabe"] is False)
    furam = sum(1 for r in d["rodando"] if _valendo_e_fura(r))
    itens_furam = len({r["item_id"] for r in d["rodando"] if _valendo_e_fura(r)})
    desatualizadas = furam_total - furam
    aviso = ""
    if furam:
        aviso = (f'<p class="aviso aviso--critico"><b>{furam} campanha(s) rodando furam o piso '
                 f'agora, de verdade, em {itens_furam} anúncio(s)</b> — um anúncio com mais de uma '
                 f'campanha ativa aparece mais de uma vez aqui. Isso não se resolve cadastrando '
                 f'preço: resolve-se <b>saindo</b> da campanha, que é decisão humana. E sair não '
                 f'tem volta garantida — o ML ancora no preço praticado e recusa subir depois.</p>')
    if desatualizadas:
        aviso += (f'<p class="aviso aviso--atencao"><b>{desatualizadas} linha(s) marcadas '
                 f'"leitura desatualizada"</b> — o preço dessa campanha não bate mais com o '
                 f'preço de hoje do anúncio. Esta tabela é lida por rodízio (só uma fatia dos '
                 f'anúncios é reconferida a cada coleta), então uma campanha que você acabou de '
                 f'sair pode aparecer aqui ainda por um tempo, com dado velho. O preço de '
                 f'"O que sobra" (acima) vem de <code>snap_anuncio</code>, lido inteiro em toda '
                 f'coleta — esse é o que vale como preço de agora.</p>')

    return f"""
<section class="secao">
  <h2>Campanhas</h2>
  <p class="intro">O veredito é o do motor: pega o preço que a campanha impõe e
  compara com o piso daquele anúncio. Sem custo cadastrado não há veredito —
  o preço aparece assim mesmo, para decidir na mão.</p>
  <div class="kpis">
    {_kpi(str(len(d['abertas'])), "abertas", nota="liberadas, ainda não aceitas")}
    {_kpi(str(len(d['rodando'])), "rodando agora")}
    {_kpi(str(furam), "rodando abaixo do piso, de verdade", tom="critico" if furam else "bom")}
    {_kpi(str(desatualizadas), "leitura desatualizada", tom="atencao" if desatualizadas else "bom")}
  </div>
  {aviso}
  <h3>Abertas — decisão de entrar</h3>
  {tabela(d['abertas'], rodando=False)}
  <h3>Rodando — o preço que está valendo</h3>
  {tabela(d['rodando'], rodando=True)}
</section>"""


def bloco_uma_campanha(d: dict) -> str:
    """Qual campanha fica em cada anúncio, se a conta for para uma só."""
    plano = d.get("consolidacao") or []
    if not plano:
        return ""

    neutro = [p for p in plano if p["ramo"] == "mantem o preco"]
    sobe = [p for p in plano if p["ramo"] == "sobe para o piso"]
    nada = [p for p in plano if p["ramo"] == "nenhuma cabe no piso"]
    saem = sum(len(p["saem"]) for p in plano)
    ganho = sum(p["depois"] - p["hoje"] for p in sobe)
    com_rebate = sum(1 for p in neutro if float(p["fica"]["parte_do_ml"] or 0) > 0)
    # Dos que nenhuma campanha salva, quantos já têm o CHEIO acima do piso.
    # A distinção decide o remédio, e é fácil de errar: em 03/09/2026 os 29
    # desta conta estavam todos nessa situação — o cadastro estava sadio e o
    # que furava era só a profundidade do desconto. Subir o cheio ali não
    # conserta nada, e o ML recusa o aumento enquanto a campanha está ativa.
    cheio_ok = sum(1 for p in nada if p["cheio"] and p["piso"] and p["cheio"] >= p["piso"])

    def linhas(itens, mostrar_salto: bool, teto: int = 999) -> str:
        if not itens:
            return '<p class="nada">nenhum anúncio neste caso.</p>'
        total, saida = len(itens), []
        ordenado = sorted(itens, key=lambda x: -(x["depois"] - x["hoje"]) if mostrar_salto else -x["vendidos"])
        for p in ordenado[:teto]:
            fica, rebate = p["fica"], float(p["fica"]["parte_do_ml"] or 0)
            fim = str(fica["fim"])[:10] if fica["fim"] else None
            salto = ((p["depois"] / p["hoje"] - 1) * 100) if p["hoje"] else 0
            nomes_saem = ", ".join(
                f'{e(promocoes.nome_legivel(x) or x["tipo"])} ({rs(x['preco'], 2)})' for x in p["saem"]) or "—"
            saida.append(f"""<tr>
  <td class="titulo">{e((p['titulo'] or '')[:66])}<br><small class="mono">{e(p['item_id'])}</small></td>
  <td class="num">{p['vendidos']}</td>
  <td>{e(promocoes.nome_legivel(fica) or fica['tipo'])}<br>
      <small>{e(fica['tipo'] or '')}{' · rebate ' + pct(rebate, 1) if rebate else ''}{' · sem prazo' if not fim else ' · até ' + fim}</small></td>
  <td class="num">{rs(p['hoje'], 2)}</td>
  <td class="num">{'<b>' + rs(p['depois'], 2) + '</b><br><small class="tom-atencao">+' + f'{salto:.0f}' + '%</small>' if salto > 0.5 else '<span class="tom-fraco">sem mudança</span>'}</td>
  <td class="num">{rs(p['piso'], 2) if p['piso'] else '—'}</td>
  <td><small class="tom-fraco">{nomes_saem}</small></td>
</tr>""")
        cab = ('<thead><tr><th>Anúncio</th><th>Vd</th><th>Fica com</th><th>Preço hoje</th>'
               '<th>Preço depois</th><th>Piso</th><th>Saem</th></tr></thead>')
        resto = (f'<p class="micro">e mais {total - teto} anúncio(s) neste caso, '
                 f'ordenados por venda.</p>' if total > teto else '')
        return (f'<div class="rolagem"><table class="tabela">{cab}'
                f'<tbody>{"".join(saida)}</tbody></table></div>{resto}')

    return f"""
<section class="secao">
  <h2>Uma campanha por anúncio</h2>
  <p class="intro">Hoje há <b>{len(plano)}</b> anúncios em campanha e
  <b>{sum(p['quantas'] for p in plano)}</b> campanhas rodando sobre eles — em média
  {sum(p['quantas'] for p in plano) / len(plano):.1f} por anúncio. Com várias ao mesmo tempo, quem manda
  no preço é sempre a mais barata, e sair de uma não muda nada porque a seguinte
  assume. Abaixo, qual fica em cada caso.</p>
  <div class="kpis">
    {_kpi(str(saem), "campanhas saem", nota=f"de {sum(p['quantas'] for p in plano)} rodando")}
    {_kpi(str(len(neutro)), "sem mexer no preço", tom="bom", nota=f"{com_rebate} ficam com rebate do ML")}
    {_kpi(str(len(sobe)), "o preço sobe", tom="atencao", nota=f"+{rs(ganho)} por rodada")}
    {_kpi(str(len(nada)), "nenhuma cabe no piso", tom="critico",
          nota=f"{cheio_ok} já têm cheio sadio")}
  </div>
  <p class="aviso"><b>A régua.</b> Se a campanha mais barata já respeita o piso, ela
  fica — e sair das outras é <b>neutro para o comprador</b>, porque o preço que valia
  já era o dela. Entre empatadas no menor preço, fica a de maior rebate do Mercado
  Livre. Se a mais barata fura o piso, fica a mais barata que não fura: aí o preço
  sobe, e é esse o conserto.</p>

  <h3>Sem mexer no preço — {len(neutro)} anúncios</h3>
  <p class="intro">Aqui sair das outras campanhas não altera o que o comprador paga.
  É o grupo seguro, e o mais numeroso.</p>
  {linhas(neutro, False, teto=24)}

  <h3>O preço sobe — {len(sobe)} anúncios</h3>
  <p class="intro">A campanha mais barata furava o piso. Sair dela devolve
  <b>{rs(ganho)}</b> por rodada de vendas, com o salto na coluna de preço.</p>
  {linhas(sobe, True)}

  <h3>Nenhuma campanha cabe no piso — {len(nada)} anúncios</h3>
  <p class="intro">Nem a mais cara alcança o piso, então aqui trocar de campanha só
  escolhe o menos ruim. <b>Mas em {cheio_ok} destes {len(nada)} o preço de cadastro já
  cobre o piso</b> — o cadastro está sadio e o que fura é a profundidade do desconto.
  Nesses, o remédio é <b>sair da campanha</b>, não subir o preço: ao expirar, o anúncio
  volta ao cheio e fica saudável sozinho. E enquanto a campanha está ativa o Mercado
  Livre recusa o aumento de preço de qualquer forma.</p>
  {linhas(nada, False)}
</section>"""


STATUS_LEGIVEL = {
    "active": "ativo", "paused": "pausado", "under_review": "em revisão",
    "not_yet_active": "não ativado",
}


def bloco_todos_produtos(d: dict) -> str:
    """A lista simples: um item por linha — SKU, preço de venda, preço de
    promoção, frete e lucro líquido. É a primeira pergunta de qualquer
    conversa sobre a conta ('quantos itens temos, quanto cada um dá de
    lucro'), por isso mora logo no topo da página, antes de qualquer
    diagnóstico. Sem coluna de campanha, sem família, sem status — quem
    quiser esse detalhe encontra nas seções de baixo.
    """
    todos = d["todos"]
    if not todos:
        return ""
    por_margem = d.get("margens_por_item") or {}
    promos_por_item = d.get("por_item") or {}

    linhas_dados = []
    for item_id, anuncio in todos.items():
        r = por_margem.get(item_id)
        rodando = [p for p in promos_por_item.get(item_id, []) if p["status"] == "started"]
        barata = min(rodando, key=lambda p: p["preco"]) if rodando else None
        preco_venda = (barata["preco_original"] if barata and barata["preco_original"]
                      else anuncio["preco"])
        preco_promo = barata["preco"] if barata else None
        linhas_dados.append({
            "item_id": item_id, "titulo": anuncio["titulo"],
            "sku": (anuncio["sku"] or "").strip(), "status": anuncio["status"],
            "frete": r["frete_absorvido"] if r else None,
            "margem": r["margem"] if r else None,
            "lucro": r["lucro"] if r else None,
            "preco_venda": preco_venda, "preco_promo": preco_promo,
        })
    # Sem custo primeiro (é o que bloqueia qualquer leitura), depois pior
    # margem primeiro — é a mesma prioridade que 'O que sobra' usa.
    linhas_dados.sort(key=lambda x: (x["margem"] is not None,
                                     x["margem"] if x["margem"] is not None else 0))

    def linha(x: dict) -> str:
        if x["margem"] is None:
            lucro_col = '<span class="tom-fraco">sem custo</span>'
        else:
            tom = "critico" if x["lucro"] is not None and x["lucro"] < 0 else (
                "atencao" if x["margem"] < (d["alvo"] or 0) else "bom")
            lucro_col = (f'<span class="tom-{tom}">R$ {rs(x["lucro"], 2)}'
                        f' <small>({pct(x["margem"], 1, sinal=True)})</small></span>')
        promo_col = (f'R$ {rs(x["preco_promo"], 2)}' if x["preco_promo"] is not None
                    else '<span class="tom-fraco">—</span>')
        if x["frete"] is None:
            frete_col = '<span class="tom-fraco">—</span>'
        elif x["frete"] > 0:
            frete_col = f'R$ {rs(x["frete"], 2)}'
        else:
            frete_col = '<span class="tom-fraco">comprador paga / não medido</span>'
        status_col = (f' <span class="tom-atencao">({e(STATUS_LEGIVEL.get(x["status"], x["status"]))})</span>'
                     if x["status"] != "active" else "")
        return f"""
<tr>
  <td class="mono">{e(x['sku']) if x['sku'] else '<span class="tom-fraco">sem SKU</span>'}</td>
  <td class="titulo">{e(x['titulo'])}{status_col}<br><small class="mono">{e(x['item_id'])}</small></td>
  <td class="num">R$ {rs(x['preco_venda'], 2)}</td>
  <td class="num">{promo_col}</td>
  <td class="num">{frete_col}</td>
  <td class="num">{lucro_col}</td>
</tr>"""

    com_promo = sum(1 for x in linhas_dados if x["preco_promo"] is not None)
    sem_custo = sum(1 for x in linhas_dados if x["margem"] is None)

    return f"""
<section class="secao">
  <h2>Itens cadastrados</h2>
  <p class="intro">Todos os <b>{len(linhas_dados)}</b> itens do catálogo desta
  conta (ativo, pausado, em revisão — não conta o encerrado), um por linha:
  SKU, preço de venda, preço de promoção (quando há campanha rodando), frete
  que a loja absorve, e lucro líquido por venda no preço de hoje. Ordenado
  por quem está sem custo cadastrado primeiro, depois por pior lucro.</p>
  <div class="kpis">
    {_kpi(str(len(linhas_dados)), "itens cadastrados")}
    {_kpi(str(com_promo), "em promoção agora")}
    {_kpi(str(sem_custo), "sem custo cadastrado", tom="atencao" if sem_custo else "bom")}
  </div>
  <div class="rolagem"><table class="tabela">
    <thead><tr><th>SKU</th><th>Anúncio</th><th>Preço de venda</th>
    <th>Preço de promoção</th><th>Frete</th><th>Lucro líquido</th></tr></thead>
    <tbody>{"".join(linha(x) for x in linhas_dados)}</tbody>
  </table></div>
</section>"""


def bloco_frete(d: dict) -> str:
    ativos = len(d["ativos"])
    paga, medido = len(d["paga_frete"]), len(d["frete_medido"])
    sem_modo = len(d["sem_modo"])

    linhas_modo = "".join(f"""
<tr>
  <th scope="row">{e(MODOS.get(m, m))}<br><small class="mono">{e(m)}</small></th>
  <td class="num">{n}</td>
  <td>{barra(n / ativos if ativos else 0, "atencao" if m == "not_specified" else "acento")}</td>
</tr>""" for m, n in d["modos"])

    # Quanto o frete pesa: em reais e como fatia do preço do anúncio.
    pesos = []
    for r in d["frete_medido"]:
        valor = d["frete_por_item"][r["item_id"]]
        if r["preco"]:
            pesos.append((valor / r["preco"] * 100, valor, r["preco"], r["titulo"]))
    pesos.sort(reverse=True)

    if pesos:
        mediana_frete = statistics.median([p[1] for p in pesos])
        mediana_peso = statistics.median([p[0] for p in pesos])
        linhas_peso = "".join(f"""
<tr>
  <td class="titulo">{e(t)}</td>
  <td class="num">R$ {rs(preco, 2)}</td>
  <td class="num">R$ {rs(valor, 2)}</td>
  <td class="num tom-{'critico' if peso >= 15 else 'atencao' if peso >= 8 else 'neutro'}">{pct(peso)}</td>
  <td>{barra(peso / 30, 'critico' if peso >= 15 else 'atencao')}</td>
</tr>""" for peso, valor, preco, t in pesos[:8])
        tabela_peso = f"""
    <h3>Onde o frete mais pesa</h3>
    <p class="intro">Frete grátis medido contra o preço do anúncio. Este valor sai
    inteiro da margem — mediana de <b>R$ {rs(mediana_frete, 2)}</b> por peça,
    <b>{pct(mediana_peso)}</b> do preço.</p>
    <div class="rolagem"><table class="tabela">
      <thead><tr><th>Anúncio</th><th>Preço</th><th>Frete</th><th>Peso</th><th></th></tr></thead>
      <tbody>{linhas_peso}</tbody>
    </table></div>"""
    else:
        tabela_peso = ""

    aviso = (f'<p class="aviso aviso--atencao"><b>{medido} de {paga} anúncios com frete grátis '
             f'já têm o frete medido.</b> O restante entra na fila do rodízio — o vigia mede '
             f'8 por rodada, então a cobertura sobe sozinha. Enquanto um anúncio não for medido, '
             f'a margem dele é teto.</p>') if medido < paga else ""

    aviso_modo = (f'<p class="aviso aviso--atencao"><b>{sem_modo} anúncios ativos sem modo de '
                  f'envio definido.</b> Anúncio ativo sem modo costuma ser cadastro pela metade: '
                  f'vale conferir se está mesmo entregável.</p>') if sem_modo else ""

    return f"""
<section class="secao">
  <h2>Frete</h2>
  <p class="intro">Quem paga o frete, por qual modo e quanto isso custa. O valor
  medido é o do frete cheio da opção de envio — não o que o comprador paga, que
  em frete grátis é sempre zero. É este valor que entra no piso de margem.</p>
  <div class="kpis">
    {_kpi(f"{paga}<small>/{ativos}</small>", "com frete grátis", nota="a loja paga")}
    {_kpi(f"{medido}", "com custo medido", tom="critico" if medido < paga else "bom")}
    {_kpi(str(sem_modo), "sem modo de envio", tom="atencao" if sem_modo else "bom")}
  </div>
  {aviso}{aviso_modo}
  {tabela_peso}
  <h3>Modo de envio dos ativos</h3>
  <div class="rolagem"><table class="tabela">
    <thead><tr><th>Modo</th><th>Anúncios</th><th>Fatia</th></tr></thead>
    <tbody>{linhas_modo}</tbody>
  </table></div>
</section>"""


CSS = """
.kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; margin:20px 0 18px; }
.kpi {
  background:var(--superficie); border:1px solid var(--linha); border-radius:4px;
  padding:14px 16px; box-shadow:var(--sombra); display:flex; flex-direction:column; gap:3px;
}
.kpi__n {
  font-family:"Bricolage Grotesque",sans-serif; font-size:28px; font-weight:700;
  letter-spacing:-.03em; line-height:1.05; font-variant-numeric:tabular-nums;
}
.kpi__n small { font-size:15px; font-weight:500; color:var(--tinta-fraca); letter-spacing:0; }
.kpi__n--bom { color:var(--bom); }
.kpi__n--atencao { color:var(--atencao); }
.kpi__n--critico { color:var(--critico); }
.kpi__r { font-size:12.5px; color:var(--tinta-fraca); }
.kpi__nota { font-family:"IBM Plex Mono",monospace; font-size:10.5px; color:var(--tinta-fraca); }

.secao h3 { font-size:15px; font-weight:700; margin:26px 0 2px; }
.secao h3 + .intro { margin-top:6px; }
.micro { margin:10px 0 0; font-family:"IBM Plex Mono",monospace; font-size:11.5px; color:var(--tinta-fraca); }

.aviso {
  margin:16px 0; padding:12px 16px; border-radius:3px; font-size:13.5px;
  line-height:1.5; max-width:76ch; background:var(--superficie); border:1px solid var(--linha);
}
.aviso--atencao { border-left:3px solid var(--atencao); }
.aviso--critico { border-left:3px solid var(--critico); }
.lista-sku { margin:10px 0 0; padding-left:18px; display:flex; flex-direction:column; gap:4px; }
.lista-sku li { font-size:12.5px; }
.lista-sku small { color:var(--tinta-fraca); }

.tom-bom { color:var(--bom); } .tom-critico { color:var(--critico); }
.tom-atencao { color:var(--atencao); } .tom-neutro, .tom-fraco { color:var(--tinta-fraca); }
code { font-family:"IBM Plex Mono",monospace; font-size:.9em; background:var(--acento-fraco);
       color:var(--acento); padding:1px 5px; border-radius:2px; }

.atalhos { display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; }
.atalhos a {
  font-family:"IBM Plex Mono",monospace; font-size:11.5px; text-decoration:none;
  border:1px solid var(--linha); border-radius:2px; padding:5px 10px; color:var(--tinta-fraca);
}
.atalhos a:hover { border-color:var(--acento); color:var(--acento); }
"""


def montar(d: dict, vitrine: str = "painel-metricas.html") -> str:
    s, agora = d["saude"], datetime.now(TZ)
    nome = d["nome"]
    corpo = f"""
  <header class="cabeca">
    <p class="eyebrow">Zion · página da loja</p>
    <h1>{e(nome)}</h1>
    <p class="resumo">O que sobra em cada anúncio, o que as campanhas fazem com
    isso, e quem está pagando o frete. Uma página por loja — os números abaixo
    são só desta conta.</p>
    <div class="carimbo">
      <span>Coleta <b>{agora:%d/%m/%Y às %H:%M}</b></span>
      <span>Conta <b>{e(s.get('nickname') or d['slug'])}</b></span>
      <span>Ativos <b>{len(d['ativos'])}</b></span>
      <span>Custo <b>{e(d['planilha'] or 'sem planilha')}</b></span>
      <span>Margem alvo <b>{pct(d['alvo'], 0)}</b></span>
    </div>
    <div class="atalhos">
      <a href="{e(vitrine)}">← as três contas lado a lado</a>
    </div>
  </header>
  {bloco_todos_produtos(d)}
  {bloco_lucro(d)}
  {bloco_campanhas(d)}
  {bloco_uma_campanha(d)}
  {bloco_frete(d)}
  <p class="creditos">
    Gerado por scripts/painel_loja.py a partir de data/zion_ml.db e
    contas/{e(d['slug'])}/{e(d['planilha'] or '—')} · somente leitura,
    nenhuma chamada à API do Mercado Livre.
  </p>"""
    return pagina(nome, corpo, CSS)


# ----------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(description="Página de acompanhamento por loja.")
    p.add_argument("contas", nargs="*", default=None,
                   help="slugs; sem argumento faz as três de sempre")
    p.add_argument("--dir", default=str(RAIZ / "relatorios"))
    p.add_argument("--vitrine", default=VITRINE,
                   help="para onde aponta o link do painel comparativo; "
                        "passe painel-metricas.html para usar o arquivo local")
    args = p.parse_args()

    slugs = args.contas or PADRAO
    con = db.conectar()
    destino_dir = Path(args.dir)
    destino_dir.mkdir(parents=True, exist_ok=True)

    codigo = 0
    for slug in slugs:
        try:
            d = dados(con, slug)
        except Exception as erro:
            print(f"  [X] {slug}: {erro}")
            codigo = 1
            continue
        if not d["ativos"]:
            print(f"  aviso: {slug} sem anúncios na última coleta — rode uma coleta antes.")
            codigo = 1
            continue
        destino = destino_dir / f"loja-{slug}.html"
        destino.write_text(montar(d, args.vitrine), encoding="utf-8")
        print(f"  {slug}: {destino}")
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
