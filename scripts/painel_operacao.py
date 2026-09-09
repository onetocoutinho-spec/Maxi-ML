"""
Painel de operação — o que está acontecendo por trás da fila e das credenciais,
numa tela só. Os outros painéis respondem "como vão as contas" (painel_metricas)
e "o que fazer nesta loja hoje" (painel_loja). Este responde uma pergunta
diferente: "o que a operação em si está fazendo, e onde ela pode estar
falhando em silêncio" — conta cadastrada mas nunca conectada, coleta que parou
de rodar, pedido recusado que ninguém viu, autorização OAuth pendente há dias.

Só lê o banco, o registro de clientes e os arquivos da fila de pedidos. Não
chama a API do ML e não abre nenhum .env — nenhuma credencial é lida ou
mostrada aqui.

    .venv\\Scripts\\python.exe scripts\\painel_operacao.py

Sai em relatorios/painel-operacao.html.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core import db  # noqa: E402
from core.config import obter_conta, todas_as_contas  # noqa: E402
from core.painel_visual import TZ, chip, e, pagina, vazio  # noqa: E402

PEDIDOS = RAIZ / "pedidos"
AUTORIZACAO_PENDENTE = RAIZ / "data" / "autorizacao_pendente.json"

# Frescor da coleta: até este limite é normal ficar sem coletar (fim de
# semana, conta secundária). Além disso é sinal de que a rotina parou.
DIAS_ATENCAO = 2
DIAS_CRITICO = 5

# Idem para uma autorização OAuth aberta e nunca concluída.
DIAS_AUTORIZACAO_ATENCAO = 1
DIAS_AUTORIZACAO_CRITICO = 3

TABELAS_COLETA = ["snap_anuncio", "snap_conta"]


# ----------------------------------------------------------------------
# Coleta
# ----------------------------------------------------------------------
def _dias_desde(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        momento = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - momento).total_seconds() / 86400


def _situacao_contas() -> list[dict]:
    con = db.conectar()
    linhas = []
    for conta in todas_as_contas(apenas_ativos=True):
        ultima = None
        for tabela in TABELAS_COLETA:
            carimbo = db.ultima_coleta(con, tabela, conta.slug)
            if carimbo and (ultima is None or carimbo > ultima):
                ultima = carimbo
        linhas.append({
            "cliente": conta.cliente_nome,
            "slug": conta.slug,
            "nome_conta": conta.nome_conta,
            "configurada": conta.configurada,
            "ultima_coleta": ultima,
            "dias": _dias_desde(ultima),
        })
    linhas.sort(key=lambda r: (r["configurada"], -(r["dias"] or 9999)))
    return linhas


_PRIMEIRA_LINHA = re.compile(r"^\[([^\]]+)]\s+(\w+(?:\s\w+)?):")


def _status_log(caminho: Path) -> tuple[str, str]:
    """(quando, rótulo do estado) a partir da primeira linha do log."""
    try:
        primeira = caminho.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
    except OSError:
        return "—", "ilegível"
    m = _PRIMEIRA_LINHA.match(primeira)
    if not m:
        return "—", "formato desconhecido"
    return m.group(1), m.group(2)


def _tom_execucao(estado: str, corpo_tem_erro_grave: bool) -> str:
    if estado == "EXECUTADO":
        return "critico" if corpo_tem_erro_grave else "bom"
    if estado == "RECUSADO":
        return "atencao"
    return "critico"  # FALHOU, TEMPO ESGOTADO, ou desconhecido


def _fila() -> dict:
    entrada = sorted(p for p in PEDIDOS.glob("*.pedido"))
    feitos_dir = PEDIDOS / "feitos"
    logs = sorted(feitos_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)

    executados = []
    for log in logs[:15]:
        quando, estado = _status_log(log)
        corpo = log.read_text(encoding="utf-8", errors="replace")
        erro_grave = "código de saída: 0" not in corpo and estado == "EXECUTADO"
        executados.append({
            "arquivo": log.stem,
            "quando": quando,
            "estado": estado,
            "tom": _tom_execucao(estado, erro_grave),
        })
    return {"pendentes": [p.stem for p in entrada], "executados": executados}


def _ja_conectada(slug: str) -> bool:
    try:
        return obter_conta(slug).configurada
    except KeyError:
        return False


def _autorizacoes_pendentes() -> list[dict]:
    if not AUTORIZACAO_PENDENTE.exists():
        return []
    try:
        dados = json.loads(AUTORIZACAO_PENDENTE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    linhas = []
    for slug, info in dados.items():
        linhas.append({
            "slug": slug,
            "dias": _dias_desde(info.get("criado_em")),
            # a conta já pode ter concluído a conexão por outro caminho depois
            # de gerar este link — aqui é sobra de arquivo, não bloqueio.
            "ja_conectada": _ja_conectada(slug),
        })
    linhas.sort(key=lambda r: (r["ja_conectada"], -(r["dias"] or 0)))
    return linhas


# ----------------------------------------------------------------------
# Desenho
# ----------------------------------------------------------------------
def _tom_frescor(linha: dict) -> str:
    if not linha["configurada"]:
        return "critico"
    if linha["dias"] is None:
        return "critico"
    if linha["dias"] > DIAS_CRITICO:
        return "critico"
    if linha["dias"] > DIAS_ATENCAO:
        return "atencao"
    return "bom"


def _texto_frescor(linha: dict) -> str:
    if not linha["configurada"]:
        return "user_id pendente — nunca conectada"
    if linha["dias"] is None:
        return "nenhuma coleta registrada"
    if linha["dias"] < 1:
        horas = linha["dias"] * 24
        return f"há {horas:.0f}h"
    return f"há {linha['dias']:.0f} dia(s)"


def _linhas_contas(contas: list[dict]) -> str:
    if not contas:
        return f'<tr><td colspan="3">{vazio("nenhuma conta ativa no registro.")}</td></tr>'
    out = []
    for c in contas:
        out.append(
            "<tr>"
            f"<th>{e(c['cliente'])}<br><small>{e(c['nome_conta'])} · {e(c['slug'])}</small></th>"
            f"<td>{chip(_texto_frescor(c), _tom_frescor(c))}</td>"
            "</tr>"
        )
    return "\n".join(out)


def _linhas_fila(executados: list[dict]) -> str:
    if not executados:
        return f'<tr><td colspan="3">{vazio("nenhum pedido executado ainda.")}</td></tr>'
    out = []
    for it in executados:
        out.append(
            "<tr>"
            f"<td class='mono'>{e(it['quando'])}</td>"
            f"<th>{e(it['arquivo'])}</th>"
            f"<td>{chip(it['estado'].lower(), it['tom'])}</td>"
            "</tr>"
        )
    return "\n".join(out)


def _linhas_autorizacao(pendentes: list[dict]) -> str:
    if not pendentes:
        return vazio("nenhuma autorização OAuth em aberto.")
    out = ['<table class="tabela"><thead><tr><th>conta</th><th>aberta há</th></tr></thead><tbody>']
    for p in pendentes:
        dias = p["dias"]
        idade = "data de abertura ilegível" if dias is None else (
            f"{dias * 24:.0f}h" if dias < 1 else f"{dias:.0f} dia(s)"
        )
        if p["ja_conectada"]:
            tom, texto = "neutro", f"{idade} — conta já conectada, arquivo sobrou"
        elif dias is None:
            tom, texto = "atencao", idade
        elif dias > DIAS_AUTORIZACAO_CRITICO:
            tom, texto = "critico", f"{idade} — sem conexão, provavelmente esquecida"
        elif dias > DIAS_AUTORIZACAO_ATENCAO:
            tom, texto = "atencao", idade
        else:
            tom, texto = "bom", idade
        out.append(f"<tr><th>{e(p['slug'])}</th><td>{chip(texto, tom)}</td></tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def montar(contas: list[dict], fila: dict, autorizacoes: list[dict]) -> str:
    agora = datetime.now(TZ).strftime("%d/%m/%Y %H:%M")
    pendentes = fila["pendentes"]

    corpo = f"""
  <header class="cabeca">
    <p class="eyebrow">zion-ml · operação</p>
    <h1>Painel de operação</h1>
    <p class="resumo">
      Não é sobre as contas — é sobre a máquina que cuida delas: quem está
      conectado de verdade, se a coleta ainda está rodando, e o que ficou
      pendente sem ninguém perceber.
    </p>
    <div class="carimbo"><span>gerado em <b>{e(agora)}</b></span></div>
  </header>

  <section class="secao">
    <h2>Contas — registro x conexão</h2>
    <p class="intro">
      Toda conta em <code>config/clientes.yaml</code>, cruzada com a última
      coleta salva no banco. "user_id pendente" é conta cadastrada que nunca
      passou por <code>scripts/autorizar.py</code> — existe no papel, não na
      operação.
    </p>
    <div class="rolagem">
      <table class="tabela">
        <thead><tr><th>cliente / conta</th><th>última coleta</th></tr></thead>
        <tbody>{_linhas_contas(contas)}</tbody>
      </table>
    </div>
  </section>

  <section class="secao">
    <h2>Fila de pedidos</h2>
    <p class="intro">
      {len(pendentes)} pedido(s) esperando o vigia rodar
      {"— " + ", ".join(e(p) for p in pendentes) if pendentes else ""}.
      Abaixo, os últimos executados: <span class="chip chip--bom">executado</span>
      terminou com código de saída 0, <span class="chip chip--atencao">recusado</span>
      foi barrado pela lista de comandos permitidos antes de rodar nada, e
      <span class="chip chip--critico">falhou / tempo esgotado</span> exige
      olhar o arquivo em <code>pedidos/feitos/</code>.
    </p>
    <div class="rolagem">
      <table class="tabela">
        <thead><tr><th>quando</th><th>pedido</th><th>resultado</th></tr></thead>
        <tbody>{_linhas_fila(fila["executados"])}</tbody>
      </table>
    </div>
  </section>

  <section class="secao">
    <h2>Autorizações OAuth em aberto</h2>
    <p class="intro">
      Uma conta entra aqui quando <code>scripts/autorizar.py</code> gera o link
      de login e ninguém volta com o código — a credencial nunca é gravada e a
      conta fica com "user_id pendente" acima, sem que isso apareça em nenhum
      alerta.
    </p>
    {_linhas_autorizacao(autorizacoes)}
  </section>

  <p class="creditos">
    Gerado por scripts/painel_operacao.py a partir de config/clientes.yaml,
    data/zion_ml.db e pedidos/ · somente leitura, nenhuma credencial exibida.
  </p>
"""
    return pagina("Painel de operação — zion-ml", corpo)


# ----------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(description="Painel de operação da esteira zion-ml.")
    p.add_argument("--saida", default=str(RAIZ / "relatorios" / "painel-operacao.html"))
    args = p.parse_args()

    contas = _situacao_contas()
    fila = _fila()
    autorizacoes = _autorizacoes_pendentes()

    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(montar(contas, fila, autorizacoes), encoding="utf-8")
    print(f"  painel: {destino}")

    criticas = [c for c in contas if _tom_frescor(c) == "critico"]
    if criticas:
        print(f"  aviso: {len(criticas)} conta(s) em estado crítico de frescor/conexão.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
