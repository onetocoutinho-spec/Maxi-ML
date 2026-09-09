"""
Persistência. SQLite único em data/zion_ml.db.

Por que um banco só e não um por conta: você precisa comparar contas do
mesmo cliente e cruzar seus anúncios com concorrentes. Toda tabela carrega
'conta_slug' e 'cliente_id', então a separação lógica é garantida por chave,
enquanto a credencial continua fisicamente isolada por pasta.

Modelo: snapshots imutáveis. Nunca sobrescrevemos o estado anterior —
cada coleta grava uma linha nova. É isso que permite dizer "o que mudou".
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .utils import DIR_DADOS, agora_iso, agora_utc, garantir_dir

CAMINHO_BANCO = DIR_DADOS / "zion_ml.db"

ESQUEMA = """
PRAGMA journal_mode=WAL;

-- Snapshot de um anúncio PRÓPRIO em um instante
CREATE TABLE IF NOT EXISTS snap_anuncio (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    coletado_em       TEXT NOT NULL,
    cliente_id        TEXT NOT NULL,
    conta_slug        TEXT NOT NULL,
    item_id           TEXT NOT NULL,
    titulo            TEXT,
    preco             REAL,
    preco_original    REAL,
    estoque           INTEGER,
    vendidos          INTEGER,
    status            TEXT,
    sub_status        TEXT,
    tipo_anuncio      TEXT,
    catalogo          INTEGER,
    produto_catalogo  TEXT,
    categoria         TEXT,
    saude             REAL,
    frete_gratis      INTEGER,
    visitas_7d        INTEGER,
    permalink         TEXT,
    thumbnail         TEXT,
    descontos         TEXT,
    envio_modo        TEXT
);
CREATE INDEX IF NOT EXISTS ix_snap_anuncio ON snap_anuncio(conta_slug, item_id, coletado_em DESC);

-- Tarifa REAL cobrada pelo Mercado Livre, medida por anúncio.
-- Existe porque a comissão em conta.yaml é um número redondo por tipo de
-- anúncio, e a real varia por CATEGORIA: a mesma conta paga 10,5% num toldo
-- de metal e 16,5% num de madeira. Precificar pelo número redondo erra
-- sempre para o mesmo lado — o de achar que sobra mais do que sobra.
-- Medição nova = linha nova; quem lê pega a mais recente.
CREATE TABLE IF NOT EXISTS tarifa_anuncio (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    medido_em     TEXT NOT NULL,
    conta_slug    TEXT NOT NULL,
    item_id       TEXT NOT NULL,
    categoria     TEXT,
    tipo_anuncio  TEXT,
    preco_base    REAL,
    taxa_pct      REAL,
    taxa_fixa     REAL
);
CREATE INDEX IF NOT EXISTS ix_tarifa ON tarifa_anuncio(conta_slug, item_id, medido_em DESC);

-- Campanha que o Mercado Livre oferece PARA UM ANÚNCIO.
--
-- 'candidate' é a que interessa: liberada, ainda não aceita. É o momento em
-- que existe decisão a tomar — e o momento em que o cliente costuma aceitar
-- no aplicativo sem conferir o custo. A campanha traz o preço que o anúncio
-- passaria a ter; cruzado com o piso, vira veredito em vez de aviso.
--
-- meli_percentage / seller_percentage dizem quem banca o desconto. Não é
-- detalhe: numa campanha em que o ML entra com 3% e o vendedor com 28%, o
-- desconto é praticamente todo do vendedor.
CREATE TABLE IF NOT EXISTS snap_promocao (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    coletado_em       TEXT NOT NULL,
    conta_slug        TEXT NOT NULL,
    item_id           TEXT NOT NULL,
    promocao_id       TEXT,
    tipo              TEXT,
    nome              TEXT,
    status            TEXT,
    preco             REAL,
    preco_original    REAL,
    preco_sugerido    REAL,
    preco_minimo      REAL,
    parte_do_ml       REAL,
    parte_do_vendedor REAL,
    fim               TEXT
);
CREATE INDEX IF NOT EXISTS ix_promo ON snap_promocao(conta_slug, item_id, coletado_em DESC);

-- Campanha de CUPOM do vendedor (SELLER_COUPON_CAMPAIGN).
--
-- Fica separada de snap_promocao de propósito: promoção é por anúncio, cupom
-- é por campanha — o desconto se aplica ao carrinho e não aparece no preço do
-- anúncio. Enfiar as duas na mesma tabela obrigaria metade das colunas a ficar
-- nula em cada linha, e a pergunta "quanto já gastei em cupom" viraria um
-- filtro que alguém um dia esquece de aplicar.
--
-- O que importa aqui é o par used_coupons / remaining_budget. O orçamento é
-- 100% do vendedor: o Mercado Livre não entra com nada em cupom, ao contrário
-- da campanha co-participada. Cada leitura é uma linha nova, e é a diferença
-- entre duas leituras que diz quantos cupons foram usados desde ontem.
CREATE TABLE IF NOT EXISTS snap_cupom (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    coletado_em        TEXT NOT NULL,
    cliente_id         TEXT NOT NULL,
    conta_slug         TEXT NOT NULL,
    promocao_id        TEXT NOT NULL,
    nome               TEXT,
    sub_tipo           TEXT,      -- FIXED_AMOUNT | FIXED_PERCENTAGE
    status             TEXT,      -- pending | started | finished | deleted
    codigo             TEXT,      -- nulo quando o cupom é aberto a todos
    valor_fixo         REAL,
    percentual         REAL,
    compra_minima      REAL,
    compra_maxima      REAL,
    orcamento          REAL,
    orcamento_restante REAL,
    cupons_usados      INTEGER,
    usos_por_comprador INTEGER,
    inicio             TEXT,
    fim                TEXT
);
CREATE INDEX IF NOT EXISTS ix_cupom ON snap_cupom(conta_slug, promocao_id, coletado_em DESC);

-- Anúncio que participa de uma campanha de cupom.
-- Responde "o cupom vale em quê", que não é a mesma pergunta que "o cupom foi
-- usado em quê" — essa a API de promoções não responde, e depende de cruzar
-- com os pedidos.
CREATE TABLE IF NOT EXISTS snap_cupom_item (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    coletado_em    TEXT NOT NULL,
    conta_slug     TEXT NOT NULL,
    promocao_id    TEXT NOT NULL,
    item_id        TEXT NOT NULL,
    status         TEXT,          -- candidate | pending | started | finished
    valor_fixo     REAL,
    percentual     REAL,
    preco_original REAL,
    inicio         TEXT,
    fim            TEXT
);
CREATE INDEX IF NOT EXISTS ix_cupom_item ON snap_cupom_item(conta_slug, promocao_id, coletado_em DESC);

-- Cupom REALMENTE usado numa venda, por anúncio.
--
-- Esta é a única tabela do projeto que NÃO é snapshot: pedido é fato
-- consumado, não estado que muda a cada leitura. Por isso tem chave única e
-- entra com INSERT OR IGNORE — reler os últimos 60 dias não duplica nada.
--
-- Por que 'valor_vendedor' existe separado de 'valor_total': o campo
-- coupon_amount do pedido soma TODOS os cupons, inclusive os que o próprio
-- Mercado Livre banca. Na primeira sonda da conta da Maxi, os 40 pedidos
-- examinados tinham coupon_amount preenchido e 'seller': 0.0 em todos —
-- eram campanhas do ML. Medir custo de cupom por coupon_amount teria
-- cobrado do vendedor um desconto que não foi ele quem pagou.
CREATE TABLE IF NOT EXISTS venda_cupom (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    registrado_em  TEXT NOT NULL,
    cliente_id     TEXT NOT NULL,
    conta_slug     TEXT NOT NULL,
    order_id       TEXT NOT NULL,
    data_pedido    TEXT,
    item_id        TEXT,
    tipo           TEXT,      -- 'coupon' | 'discount' — o /discounts usa os dois
    cupom_id       TEXT,
    campanha_id    TEXT,
    campanha_do_ml TEXT,
    quem_paga      TEXT,      -- vendedor | mercado livre | dividido
    valor_total    REAL,      -- desconto do cupom naquele item
    valor_vendedor REAL,      -- o que saiu do bolso do vendedor
    quantidade     INTEGER,
    total_pedido   REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_venda_cupom
    ON venda_cupom(conta_slug, order_id, IFNULL(item_id,''), IFNULL(cupom_id,''));
CREATE INDEX IF NOT EXISTS ix_venda_cupom ON venda_cupom(conta_slug, item_id, data_pedido DESC);
-- Índice do caminho quente: "quais pedidos usaram cupom do vendedor".
CREATE INDEX IF NOT EXISTS ix_venda_cupom_tipo
    ON venda_cupom(conta_slug, tipo, valor_vendedor);

-- TODA venda da janela, com cupom ou sem.
--
-- Existe por causa do denominador. Sem ela dá para dizer "64 pedidos usaram
-- cupom", que sozinho não informa nada: 64 de 100 é uma campanha que domina a
-- conta, 64 de 1000 é ruído. A tabela venda_cupom só conhece quem teve
-- desconto, então a pergunta "quantas vendas vieram pelo cupom" era
-- literalmente irrespondível com o que estava guardado.
--
-- Custa zero chamada a mais: os pedidos já vêm inteiros na mesma busca que a
-- coleta de cupom faz. Guarda o status porque pedido cancelado não é receita,
-- e entra com chave única — releitura da mesma janela não duplica.
CREATE TABLE IF NOT EXISTS venda (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    registrado_em TEXT NOT NULL,
    cliente_id    TEXT,
    conta_slug    TEXT NOT NULL,
    order_id      TEXT NOT NULL,
    data_pedido   TEXT,
    status        TEXT,
    total         REAL,
    unidades      INTEGER,
    itens         TEXT,
    comprador     TEXT       -- para separar cliente novo de recorrente
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_venda ON venda(conta_slug, order_id);
CREATE INDEX IF NOT EXISTS ix_venda ON venda(conta_slug, data_pedido DESC);




-- Snapshot de um anúncio CONCORRENTE
CREATE TABLE IF NOT EXISTS snap_concorrente (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    coletado_em       TEXT NOT NULL,
    cliente_id        TEXT NOT NULL,
    conta_slug        TEXT NOT NULL,
    origem            TEXT NOT NULL,      -- 'palavra-chave' | 'vendedor'
    referencia        TEXT NOT NULL,      -- o termo ou o seller_id
    item_id           TEXT NOT NULL,
    titulo            TEXT,
    preco             REAL,
    vendidos          INTEGER,
    seller_id         TEXT,
    seller_nickname   TEXT,
    frete_gratis      INTEGER,
    posicao           INTEGER,
    catalogo          INTEGER,
    permalink         TEXT,
    comparar_com      TEXT,
    frete_custo       REAL,
    estoque           INTEGER,
    status            TEXT
);
CREATE INDEX IF NOT EXISTS ix_snap_conc ON snap_concorrente(conta_slug, referencia, coletado_em DESC);

-- Posição dos MEUS anúncios nas palavras-chave monitoradas
CREATE TABLE IF NOT EXISTS snap_posicao (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    coletado_em   TEXT NOT NULL,
    cliente_id    TEXT NOT NULL,
    conta_slug    TEXT NOT NULL,
    termo         TEXT NOT NULL,
    item_id       TEXT NOT NULL,
    posicao       INTEGER,
    preco         REAL,
    preco_topo    REAL,
    total_result  INTEGER
);
CREATE INDEX IF NOT EXISTS ix_snap_pos ON snap_posicao(conta_slug, termo, item_id, coletado_em DESC);

-- Saúde/reputação da conta
CREATE TABLE IF NOT EXISTS snap_conta (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    coletado_em       TEXT NOT NULL,
    cliente_id        TEXT NOT NULL,
    conta_slug        TEXT NOT NULL,
    nickname          TEXT,
    nivel             TEXT,
    power_seller      TEXT,
    transacoes        INTEGER,
    reclamacoes_pct   REAL,
    cancelamentos_pct REAL,
    atrasos_pct       REAL,
    anuncios_ativos   INTEGER,
    anuncios_pausados INTEGER,
    vendas_7d         INTEGER,
    receita_7d        REAL
);

-- Alertas gerados
CREATE TABLE IF NOT EXISTS alerta (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em     TEXT NOT NULL,
    cliente_id    TEXT NOT NULL,
    conta_slug    TEXT NOT NULL,
    regra         TEXT NOT NULL,
    critico       INTEGER NOT NULL DEFAULT 0,
    item_id       TEXT,
    titulo        TEXT,
    mensagem      TEXT NOT NULL,
    dados         TEXT,
    reconhecido   INTEGER NOT NULL DEFAULT 0,
    notificado    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_alerta ON alerta(conta_slug, criado_em DESC);

-- Marcadores de "já rodou": evita mandar o resumo duas vezes no mesmo dia
-- e permite disparar na PRIMEIRA rodada após o horário, em vez de exigir
-- que uma rodada caia exatamente na hora cheia.
CREATE TABLE IF NOT EXISTS marcador (
    chave      TEXT PRIMARY KEY,
    valor      TEXT NOT NULL,
    atualizado TEXT NOT NULL
);

-- Log de execuções (auditoria: o que rodou, em qual conta, com que resultado)
CREATE TABLE IF NOT EXISTS execucao (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    iniciado_em  TEXT NOT NULL,
    terminado_em TEXT,
    comando      TEXT NOT NULL,
    conta_slug   TEXT,
    ok           INTEGER,
    detalhe      TEXT
);
"""



def _migrar(con: sqlite3.Connection) -> None:
    """Colunas acrescentadas depois que já havia banco em produção."""
    colunas_conc = {l["name"] for l in con.execute("PRAGMA table_info(snap_concorrente)")}
    for coluna, tipo in (("comparar_com", "TEXT"), ("frete_custo", "REAL"),
                         ("estoque", "INTEGER"), ("status", "TEXT")):
        if coluna not in colunas_conc:
            con.execute(f"ALTER TABLE snap_concorrente ADD COLUMN {coluna} {tipo}")

    colunas_anuncio = {l["name"] for l in con.execute("PRAGMA table_info(snap_anuncio)")}
    # frete_custo é o que o COMPRADOR paga — em frete grátis isso é sempre 0,
    # e por isso não serve para margem. frete_lista é o valor cheio da mesma
    # opção de envio: a melhor medida disponível do que sai do vendedor.
    #
    # frete_origem diz COMO aquele número foi obtido, e existe porque os dois
    # caminhos não significam a mesma coisa. 'opcao_do_item' é o custo da opção
    # de envio que o anúncio realmente tem. 'cotacao_frete_gratis' é o que o ML
    # cobraria se o anúncio despachasse por ele — usado nos `not_specified`,
    # que entregam por fora e para os quais o primeiro caminho não responde.
    # Sem separar, uma cotação hipotética viraria custo medido na mesma coluna,
    # que é exatamente o tipo de mistura que esta casa não faz.
    for coluna, tipo in (("thumbnail", "TEXT"), ("descontos", "TEXT"),
                         ("envio_modo", "TEXT"), ("frete_custo", "REAL"),
                         ("preco_vitrine", "REAL"), ("sku", "TEXT"),
                         ("frete_lista", "REAL"), ("frete_origem", "TEXT")):
        if coluna not in colunas_anuncio:
            con.execute(f"ALTER TABLE snap_anuncio ADD COLUMN {coluna} {tipo}")
    con.commit()

    colunas_conta = {l["name"] for l in con.execute("PRAGMA table_info(snap_conta)")}
    for coluna, tipo in (("vendas_hoje", "INTEGER"), ("receita_hoje", "REAL"),
                         ("cancelados_7d", "INTEGER"), ("receita_cancelada_7d", "REAL"),
                         ("janela_vendas", "TEXT")):
        if coluna not in colunas_conta:
            con.execute(f"ALTER TABLE snap_conta ADD COLUMN {coluna} {tipo}")
    con.commit()

    colunas_v = {l["name"] for l in con.execute("PRAGMA table_info(venda)")}
    if colunas_v and "comprador" not in colunas_v:
        con.execute("ALTER TABLE venda ADD COLUMN comprador TEXT")
        con.commit()

    colunas_venda = {l["name"] for l in con.execute("PRAGMA table_info(venda_cupom)")}
    if colunas_venda and "tipo" not in colunas_venda:
        con.execute("ALTER TABLE venda_cupom ADD COLUMN tipo TEXT")
        con.commit()

    colunas = {l["name"] for l in con.execute("PRAGMA table_info(alerta)")}
    if "notificado" not in colunas:
        con.execute("ALTER TABLE alerta ADD COLUMN notificado INTEGER NOT NULL DEFAULT 0")
        # alertas antigos entram como já notificados, para não disparar um
        # despejo de histórico na primeira vez que o canal for ligado
        con.execute("UPDATE alerta SET notificado = 1")
        con.commit()


def conectar() -> sqlite3.Connection:
    """
    Abre o banco preparado para DOIS processos ao mesmo tempo.

    O vigia grava de 5 em 5 minutos e a rotina de hora em hora faz a coleta
    completa. Uma hora eles se cruzam — e se cruzaram: às 20:30 o vigia perdeu
    o ciclo inteiro com "database is locked". Uma leitura perdida não parece
    grave, mas o sistema inteiro é comparação entre rodadas, e rodada que não
    existe é buraco na série.

    Duas linhas resolvem:

      WAL          deixa um processo ler enquanto o outro escreve, em vez de
                   um bloquear o outro.
      busy_timeout espera até 60s por um lock em vez de desistir em 5s.
                   Começou em 30s e ainda assim um ciclo se perdeu quando a
                   coleta completa e o vigia se cruzaram — coleta inteira, com
                   destaques e catálogo, passa disso. Esperar é sempre melhor
                   que perder a leitura.
    """
    garantir_dir(DIR_DADOS)
    con = sqlite3.connect(CAMINHO_BANCO, timeout=60)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=60000")
        con.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass                      # banco em disco que não aceita WAL (rede, pendrive)
    con.executescript(ESQUEMA)
    _migrar(con)
    return con


def vitrines_recentes(con: sqlite3.Connection, conta_slug: str) -> dict[str, float]:
    """
    O último preço de vitrine NÃO NULO de cada anúncio — desde que ele ainda
    descreva o preço de hoje.

    Existe porque o preço de vitrine só é medido na passada larga do dia: nos
    ciclos curtos do vigia a coluna fica nula, e quem comparasse com o
    snapshot da vez cairia no preço de cadastro — que é o preço errado, o que
    ignora campanha promocional. Mesmo remédio já aplicado ao frete.

    A GUARDA DE RECÊNCIA veio depois, em 03/09/2026, e é o que impede o
    remédio de virar veneno: a vitrine é um desconto SOBRE o cadastro, então
    quando o cadastro muda a medição antiga deixa de significar qualquer
    coisa. Naquele dia dois anúncios foram corrigidos de R$ 400 para
    R$ 1.133,34 às 11:33; a última vitrine era das 11:13 e valia R$ 400, e por
    horas o sistema seguiu chamando os dois de "abaixo do piso" e "em
    prejuízo" — pelo preço que eles não tinham mais.

    Por isso a medição só entra quando o cadastro daquele snapshot é igual ao
    cadastro de agora. Mudou o preço, a vitrine some da conta e quem chama cai
    no cadastro, que é o valor certo até a próxima passada larga medir de novo.
    """
    linhas = con.execute(
        "WITH atual AS ("
        "  SELECT item_id, preco FROM snap_anuncio"
        "   WHERE conta_slug = :slug AND coletado_em = ("
        "     SELECT MAX(coletado_em) FROM snap_anuncio WHERE conta_slug = :slug)"
        ") "
        "SELECT v.item_id, v.preco_vitrine FROM snap_anuncio v "
        "JOIN atual ON atual.item_id = v.item_id "
        "WHERE v.conta_slug = :slug AND v.preco_vitrine IS NOT NULL "
        "  AND v.preco IS atual.preco "          # cadastro mudou? a vitrine caducou
        "  AND v.coletado_em = ("
        "    SELECT MAX(coletado_em) FROM snap_anuncio "
        "     WHERE conta_slug = v.conta_slug AND item_id = v.item_id "
        "       AND preco_vitrine IS NOT NULL)",
        {"slug": conta_slug}).fetchall()
    return {l["item_id"]: float(l["preco_vitrine"]) for l in linhas}


def fretes_recentes(con: sqlite3.Connection, conta_slug: str) -> dict[str, float]:
    """
    O último frete de LISTA não nulo de cada anúncio.

    Mesmo remédio de vitrines_recentes, e pela mesma razão: o frete é medido
    por rodízio (8 anúncios por ciclo do vigia), então o snapshot da vez tem a
    coluna nula na esmagadora maioria. Quem olhasse só o snapshot concluiria
    que o frete não é conhecido logo depois de medi-lo.

    É o valor cheio da opção de envio — não o que o comprador paga, que em
    frete grátis é sempre zero. Em anúncio com frete grátis, é o que sai do
    vendedor; conferido em 02/09/2026 contra a planilha do Ênio, onde o toldo
    230x100 dá R$ 49,35 na medição e R$ 49,35 no custo informado pelo cliente.
    """
    linhas = con.execute(
        "SELECT item_id, frete_lista FROM snap_anuncio a "
        "WHERE conta_slug = ? AND frete_lista IS NOT NULL AND coletado_em = ("
        "  SELECT MAX(coletado_em) FROM snap_anuncio "
        "  WHERE conta_slug = a.conta_slug AND item_id = a.item_id "
        "    AND frete_lista IS NOT NULL)",
        (conta_slug,)).fetchall()
    return {l["item_id"]: float(l["frete_lista"]) for l in linhas}


def tarifas_medidas(con: sqlite3.Connection, conta_slug: str) -> dict[str, dict]:
    """
    A tarifa mais recente de cada anúncio, por item_id.

    Quem chama usa isto no lugar da comissão fixa do conta.yaml e só cai no
    conta.yaml quando o anúncio nunca foi medido.
    """
    linhas = con.execute(
        "SELECT item_id, taxa_pct, taxa_fixa, medido_em FROM tarifa_anuncio t "
        "WHERE conta_slug = ? AND medido_em = ("
        "  SELECT MAX(medido_em) FROM tarifa_anuncio "
        "  WHERE conta_slug = t.conta_slug AND item_id = t.item_id)",
        (conta_slug,)).fetchall()
    return {l["item_id"]: {"taxa_pct": l["taxa_pct"],
                           "taxa_fixa": l["taxa_fixa"] or 0.0,
                           "medido_em": l["medido_em"]} for l in linhas}


def rebates_ativos(con: sqlite3.Connection, conta_slug: str) -> dict[str, float]:
    """
    Quanto o ML devolve de tarifa, por anúncio, na promoção que manda hoje.

    `parte_do_ml` é a fatia do desconto que o Mercado Livre banca, medida sobre
    o preço ORIGINAL, e chega ao vendedor como redução de tarifa. Conferido
    contra a tela do ML na FACILITA em 02/09/2026: percentual 1,9 sobre R$ 960
    dá R$ 18,24 e a tela mostrou R$ 18,04 — a diferença de centavos vem do
    percentual chegar arredondado numa casa.

    Ignorar isso faz o piso sair alto demais em campanha SMART. Em 02/09/2026
    dois anúncios do Ênio apareceram como "abaixo do piso" tendo 13,8% e 13,1%
    de margem real, e a operação saiu de duas promoções que estavam boas.

    Vale a MAIS BARATA entre as que estão valendo, porque é ela que define o
    preço cobrado — mesma regra que o resto do sistema usa para ler a vitrine.
    """
    linhas = con.execute(
        "SELECT p.item_id, p.preco, p.parte_do_ml, p.preco_original "
        "FROM snap_promocao p JOIN ("
        "  SELECT item_id, MAX(coletado_em) AS t FROM snap_promocao "
        "  WHERE conta_slug = ? GROUP BY item_id) u "
        "  ON u.item_id = p.item_id AND u.t = p.coletado_em "
        "WHERE p.conta_slug = ? AND p.status = 'started'",
        (conta_slug, conta_slug)).fetchall()

    manda: dict[str, sqlite3.Row] = {}
    for l in linhas:
        if l["preco"] is None:
            continue
        atual = manda.get(l["item_id"])
        if atual is None or l["preco"] < atual["preco"]:
            manda[l["item_id"]] = l

    saida: dict[str, float] = {}
    for item_id, l in manda.items():
        pct, base = l["parte_do_ml"], l["preco_original"]
        if pct is None or base is None:
            continue
        # Nunca negativo: o rebate só pode BAIXAR o piso. Assim esta função não
        # consegue inventar um "abaixo do piso" que não existia — no pior caso
        # ela não corrige um que existia.
        saida[item_id] = max(0.0, float(pct) / 100.0 * float(base))
    return saida


def inserir(con: sqlite3.Connection, tabela: str, linha: dict) -> None:
    colunas = ", ".join(linha)
    marcas = ", ".join("?" for _ in linha)
    con.execute(f"INSERT INTO {tabela} ({colunas}) VALUES ({marcas})", list(linha.values()))


def inserir_muitos(con: sqlite3.Connection, tabela: str, linhas: Iterable[dict]) -> int:
    linhas = list(linhas)
    if not linhas:
        return 0
    colunas = list(linhas[0])
    marcas = ", ".join("?" for _ in colunas)
    con.executemany(
        f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({marcas})",
        [[l.get(c) for c in colunas] for l in linhas],
    )
    return len(linhas)


def ultima_coleta(con: sqlite3.Connection, tabela: str, conta_slug: str, antes_de: str | None = None) -> str | None:
    """Carimbo da coleta mais recente (opcionalmente anterior a um carimbo)."""
    sql = f"SELECT MAX(coletado_em) AS t FROM {tabela} WHERE conta_slug = ?"
    args: list[Any] = [conta_slug]
    if antes_de:
        sql += " AND coletado_em < ?"
        args.append(antes_de)
    linha = con.execute(sql, args).fetchone()
    return linha["t"] if linha else None


def snapshot_por_item(con: sqlite3.Connection, tabela: str, conta_slug: str, carimbo: str) -> dict[str, sqlite3.Row]:
    if not carimbo:
        return {}
    linhas = con.execute(
        f"SELECT * FROM {tabela} WHERE conta_slug = ? AND coletado_em = ?",
        (conta_slug, carimbo),
    ).fetchall()
    return {l["item_id"]: l for l in linhas}


def registrar_alerta(
    con: sqlite3.Connection,
    *,
    cliente_id: str,
    conta_slug: str,
    regra: str,
    critico: bool,
    mensagem: str,
    item_id: str | None = None,
    titulo: str | None = None,
    dados: dict | None = None,
    janela_horas: int = 6,
    por_item: bool = False,
) -> bool:
    """
    Grava o alerta e devolve se ele foi mesmo gravado.

    Mensagem idêntica, na mesma conta, dentro da janela, não entra de novo.
    Sem isso o alerta de estado — "o concorrente está mais barato que você" —
    é regravado a cada coleta, porque a condição continua verdadeira. É estado,
    não acontecimento: repetir a mesma frase oito vezes por dia não informa
    nada e treina o operador a não ler a lista.
    """
    # Ponto único onde toda mensagem passa antes de virar alerta. É aqui que
    # a pontuação dobrada morre, em vez de em cada uma das dezenas de frases.
    from .humano import limpar_pontuacao
    mensagem = limpar_pontuacao(mensagem)

    # Todo alerta que fala de um anúncio leva o endereço dele. Aqui, e não em
    # cada regra: são dezenas de frases espalhadas por rules.py, e a que
    # esquecesse de anexar o link produziria uma mensagem que obriga a caçar o
    # anúncio na conta para conferir. Sendo o ponto único por onde toda
    # mensagem passa, este é o lugar certo — o mesmo motivo pelo qual a
    # limpeza de pontuação também mora aqui.
    #
    # Quem já trouxe o link no 'dados' manda nele: a regra pode conhecer um
    # endereço melhor que o do cadastro (a ficha de catálogo, por exemplo).
    dados = dict(dados or {})
    if item_id and not dados.get("permalink"):
        link = permalink_do_anuncio(con, conta_slug, item_id)
        if link:
            dados["permalink"] = link

    # 'por_item' viaja dentro de 'dados' porque as regras chamam esta função
    # por closures que só repassam esse dicionário. Sai daqui antes de gravar:
    # é instrução de deduplicação, não dado do alerta.
    por_item = bool(dados.pop("por_item", por_item))

    if janela_horas > 0:
        # O corte é calculado em Python, no MESMO formato de agora_iso(). Com
        # datetime('now') do SQLite a comparação seria entre "2026-08-26T20:21:07+00:00"
        # e "2026-08-26 14:21:07": o 'T' é maior que o espaço na ordem de texto,
        # e qualquer alerta do mesmo dia passaria como se estivesse na janela.
        from datetime import timedelta
        corte = (agora_utc() - timedelta(hours=int(janela_horas))).isoformat(timespec="seconds")
        # A chave inclui o item: três anúncios NOVOS com títulos parecidos
        # geram três mensagens que, truncadas, viram texto idêntico — e são
        # três acontecimentos diferentes. Deduplicar só pelo texto apagaria
        # dois deles. Por item, o que some é só a repetição verdadeira.
        if por_item and item_id:
            # Alerta de ESTADO ("o concorrente está mais barato que você").
            # Aqui a chave ignora o texto: basta um número mudar dentro da
            # frase — o piso recalculado, por exemplo — para a comparação por
            # mensagem achar que é acontecimento novo e mandar de novo. Foi o
            # que encheu o resumo de 26/08 com duas linhas do SKYIFLEX, uma
            # dizendo piso R$ 766,18 e outra R$ 728,67, para o mesmo fato.
            ja_existe = con.execute(
                "SELECT 1 FROM alerta WHERE conta_slug = ? AND regra = ? "
                "AND IFNULL(item_id, '') = IFNULL(?, '') AND criado_em >= ? LIMIT 1",
                (conta_slug, regra, item_id, corte),
            ).fetchone()
        else:
            ja_existe = con.execute(
                "SELECT 1 FROM alerta WHERE conta_slug = ? AND mensagem = ? "
                "AND IFNULL(item_id, '') = IFNULL(?, '') AND criado_em >= ? LIMIT 1",
                (conta_slug, mensagem, item_id, corte),
            ).fetchone()
        if ja_existe:
            return False

    inserir(
        con,
        "alerta",
        {
            "criado_em": agora_iso(),
            "cliente_id": cliente_id,
            "conta_slug": conta_slug,
            "regra": regra,
            "critico": int(bool(critico)),
            "item_id": item_id,
            "titulo": titulo,
            "mensagem": mensagem,
            "dados": json.dumps(dados, ensure_ascii=False),
        },
    )
    return True


def permalink_do_anuncio(con: sqlite3.Connection, conta_slug: str,
                         item_id: str) -> str | None:
    """
    O endereço mais recente conhecido de um anúncio.

    Busca a última coleta em que o permalink não veio nulo, e não a última
    coleta em geral: anúncio que saiu do ar ainda tem endereço válido para
    conferir, e é justamente nele que o alerta de "sumiu da conta" precisa
    apontar.

    Nunca monta endereço a partir do ID. O sistema já mandou um link inventado
    no Telegram uma vez, e ele abria "esta página não existe" — link quebrado
    custa mais caro que link nenhum.
    """
    linha = con.execute(
        "SELECT permalink FROM snap_anuncio WHERE conta_slug = ? AND item_id = ? "
        "AND permalink IS NOT NULL AND permalink <> '' "
        "ORDER BY coletado_em DESC LIMIT 1",
        (conta_slug, item_id)).fetchone()
    return linha["permalink"] if linha else None


def ler_marcador(con: sqlite3.Connection, chave: str) -> str | None:
    linha = con.execute("SELECT valor FROM marcador WHERE chave = ?", (chave,)).fetchone()
    return linha["valor"] if linha else None


def gravar_marcador(con: sqlite3.Connection, chave: str, valor: str) -> None:
    con.execute(
        "INSERT INTO marcador (chave, valor, atualizado) VALUES (?, ?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, "
        "atualizado = excluded.atualizado",
        (chave, valor, agora_iso()),
    )
    con.commit()


def alertas_recentes(con: sqlite3.Connection, horas: int = 24, conta_slug: str | None = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM alerta WHERE criado_em >= datetime('now', ?) "
    args: list[Any] = [f"-{horas} hours"]
    if conta_slug:
        sql += "AND conta_slug = ? "
        args.append(conta_slug)
    sql += "ORDER BY critico DESC, criado_em DESC"
    return con.execute(sql, args).fetchall()
