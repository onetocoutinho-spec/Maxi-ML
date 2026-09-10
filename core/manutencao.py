"""
Manutenção do banco: condensa o histórico velho em vez de deixá-lo crescer
para sempre.

O sistema grava um retrato novo a cada rodada e nunca sobrescreve — é isso que
permite dizer "o preço dele era X ontem e é Y hoje". O custo é volume: com o
vigia de 5 em 5 minutos são cerca de 11 mil linhas por dia por conta. Uma
conta no HD de casa aguenta; dez contas num servidor pequeno, não.

A saída não é apagar o passado, é mudar a resolução dele. Detalhe de 5 em 5
minutos importa nos últimos meses, quando ainda se pergunta "que horas ele
baixou o preço?". Passado disso, o que sobra de útil é a curva: quanto custava,
quanto vendia, se estava no ar. Isso cabe em uma linha por anúncio por dia.

Guardamos, de cada dia condensado: o menor e o maior preço (que preserva a
oscilação), e o valor da ÚLTIMA leitura do dia para preço, vendas, estoque e
status (que preserva o fechamento). Média não serve — esconde justamente o
movimento que interessa.
"""
from __future__ import annotations

import sqlite3
from datetime import timedelta

from .utils import agora_utc

DIAS_DETALHADOS_PADRAO = 90

ESQUEMA = """
CREATE TABLE IF NOT EXISTS resumo_anuncio_dia (
    dia           TEXT NOT NULL,
    cliente_id    TEXT,
    conta_slug    TEXT NOT NULL,
    item_id       TEXT NOT NULL,
    titulo        TEXT,
    preco_min     REAL,
    preco_max     REAL,
    preco_fim     REAL,
    vendidos_fim  INTEGER,
    estoque_fim   INTEGER,
    status_fim    TEXT,
    visitas_7d    INTEGER,
    leituras      INTEGER,
    PRIMARY KEY (conta_slug, item_id, dia)
);

CREATE TABLE IF NOT EXISTS resumo_concorrente_dia (
    dia             TEXT NOT NULL,
    cliente_id      TEXT,
    conta_slug      TEXT NOT NULL,
    item_id         TEXT NOT NULL,
    origem          TEXT,
    referencia      TEXT,
    comparar_com    TEXT,
    seller_nickname TEXT,
    preco_min       REAL,
    preco_max       REAL,
    preco_fim       REAL,
    vendidos_fim    INTEGER,
    frete_gratis    INTEGER,
    leituras        INTEGER,
    PRIMARY KEY (conta_slug, item_id, dia)
);
"""

# substr em vez de date(): o carimbo é ISO com fuso ("...T20:19:35+00:00") e
# nem toda build do SQLite interpreta isso igual. Os 10 primeiros caracteres
# são a data, sempre.
_SQL_ANUNCIO = """
WITH base AS (
  SELECT *,
         substr(coletado_em, 1, 10) AS dia,
         ROW_NUMBER() OVER (PARTITION BY conta_slug, item_id, substr(coletado_em,1,10)
                            ORDER BY coletado_em DESC) AS ordem,
         MIN(preco)  OVER (PARTITION BY conta_slug, item_id, substr(coletado_em,1,10)) AS pmin,
         MAX(preco)  OVER (PARTITION BY conta_slug, item_id, substr(coletado_em,1,10)) AS pmax,
         COUNT(*)    OVER (PARTITION BY conta_slug, item_id, substr(coletado_em,1,10)) AS quantas
  FROM snap_anuncio
  WHERE coletado_em < :corte
)
INSERT OR REPLACE INTO resumo_anuncio_dia
  (dia, cliente_id, conta_slug, item_id, titulo, preco_min, preco_max,
   preco_fim, vendidos_fim, estoque_fim, status_fim, visitas_7d, leituras)
SELECT dia, cliente_id, conta_slug, item_id, titulo, pmin, pmax,
       preco, vendidos, estoque, status, visitas_7d, quantas
FROM base WHERE ordem = 1
"""

_SQL_CONCORRENTE = """
WITH base AS (
  SELECT *,
         substr(coletado_em, 1, 10) AS dia,
         ROW_NUMBER() OVER (PARTITION BY conta_slug, item_id, substr(coletado_em,1,10)
                            ORDER BY coletado_em DESC) AS ordem,
         MIN(preco) OVER (PARTITION BY conta_slug, item_id, substr(coletado_em,1,10)) AS pmin,
         MAX(preco) OVER (PARTITION BY conta_slug, item_id, substr(coletado_em,1,10)) AS pmax,
         COUNT(*)   OVER (PARTITION BY conta_slug, item_id, substr(coletado_em,1,10)) AS quantas
  FROM snap_concorrente
  WHERE coletado_em < :corte
)
INSERT OR REPLACE INTO resumo_concorrente_dia
  (dia, cliente_id, conta_slug, item_id, origem, referencia, comparar_com,
   seller_nickname, preco_min, preco_max, preco_fim, vendidos_fim,
   frete_gratis, leituras)
SELECT dia, cliente_id, conta_slug, item_id, origem, referencia, comparar_com,
       seller_nickname, pmin, pmax, preco, vendidos, frete_gratis, quantas
FROM base WHERE ordem = 1
"""


def garantir_esquema(con: sqlite3.Connection) -> None:
    con.executescript(ESQUEMA)


def compactar(con: sqlite3.Connection, dias: int = DIAS_DETALHADOS_PADRAO,
              simular: bool = False) -> dict:
    """
    Condensa tudo que for mais velho que `dias` e apaga o detalhe.

    Tudo dentro de uma transação: ou o resumo entra E o detalhe sai, ou nada
    acontece. Apagar detalhe sem ter gravado o resumo seria perder história de
    verdade, e não há como desfazer.
    """
    garantir_esquema(con)

    # Piso de 7 dias. A janela é configurável e um dedo errado no arquivo de
    # configuração não pode apagar o retrato que as regras usam para comparar:
    # sem o retrato anterior não há "mudou", e o sistema fica mudo achando que
    # está calmo.
    dias = max(7, int(dias))
    corte = (agora_utc() - timedelta(days=dias)).isoformat(timespec="seconds")

    # Cinto e suspensório: aconteça o que acontecer com a data, as três
    # últimas rodadas ficam. É o mínimo para comparar e para diagnosticar.
    guardadas = [l[0] for l in con.execute(
        "SELECT DISTINCT coletado_em FROM snap_anuncio "
        "ORDER BY coletado_em DESC LIMIT 3")]
    if guardadas:
        corte = min(corte, guardadas[-1])

    antes = {
        "anuncios": con.execute("SELECT COUNT(*) FROM snap_anuncio "
                                "WHERE coletado_em < ?", (corte,)).fetchone()[0],
        "concorrentes": con.execute("SELECT COUNT(*) FROM snap_concorrente "
                                    "WHERE coletado_em < ?", (corte,)).fetchone()[0],
    }
    resultado = {"corte": corte, "dias": dias, **antes,
                 "linhas_de_resumo": 0, "simulado": bool(simular)}

    if not (antes["anuncios"] or antes["concorrentes"]):
        return resultado

    if simular:
        return resultado

    try:
        con.execute("BEGIN")
        con.execute(_SQL_ANUNCIO, {"corte": corte})
        con.execute(_SQL_CONCORRENTE, {"corte": corte})
        con.execute("DELETE FROM snap_anuncio WHERE coletado_em < ?", (corte,))
        con.execute("DELETE FROM snap_concorrente WHERE coletado_em < ?", (corte,))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    resultado["linhas_de_resumo"] = (
        con.execute("SELECT COUNT(*) FROM resumo_anuncio_dia").fetchone()[0]
        + con.execute("SELECT COUNT(*) FROM resumo_concorrente_dia").fetchone()[0])
    return resultado


def recuperar_espaco(con: sqlite3.Connection) -> None:
    """
    O SQLite não devolve espaço ao disco sozinho depois de um DELETE grande.
    Sem isto o arquivo continua do tamanho de antes — o que, num servidor
    pequeno, faz a limpeza parecer que não funcionou.
    """
    con.commit()          # VACUUM não roda dentro de transação aberta
    con.execute("VACUUM")
