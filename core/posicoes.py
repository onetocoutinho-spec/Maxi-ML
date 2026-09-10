"""
Posição na busca: importa medições feitas de fora e acorda duas regras dormentes.

Por que de fora
---------------
`/sites/MLB/search` devolve 403. Sem ele, o sistema não sabe em que lugar o
anúncio aparece quando alguém digita um termo — e essa é a primeira pergunta de
qualquer reunião de resultado. Também não sabe quem vende o mesmo produto FORA
do catálogo, porque ler anúncio de terceiro por ID também está bloqueado.

As duas respostas existem numa única fonte: a página de busca do Mercado Livre,
lida por um navegador de verdade. Este módulo não faz a leitura — ele RECEBE o
resultado num arquivo e o transforma em histórico, para que o resto do sistema
funcione como se o endpoint nunca tivesse sido bloqueado.

O que isso reativa
------------------
Duas máquinas que já existiam e estavam paradas desde o bloqueio:

  snap_posicao        + regra `queda_de_posicao`
  origem palavra-chave + regra `concorrente_novo_no_topo`

Nenhuma delas precisou ser reescrita. Faltava só o dado.

Formato do arquivo (JSON, em pedidos/entrada/)
----------------------------------------------
    {
      "conta": "enio-toldos-principal",
      "medido_em": "2026-08-27T12:00:00+00:00",
      "termos": [
        {"termo": "toldo policarbonato pergolado",
         "total_resultados": 1240,
         "meus": [{"item_id": "MLB6920349886", "posicao": 7, "preco": 1932.99}],
         "concorrentes": [{"posicao": 1, "titulo": "...", "preco": 899.0,
                           "vendedor": "Fulano", "item_id": "MLB...",
                           "link": "https://..."}]}
      ]
    }

Só `termo` é obrigatório em cada bloco. Falta de campo vira ausência, nunca
erro: medição parcial é melhor que medição nenhuma, e um arquivo torto não pode
derrubar a rotina.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from . import db
from .utils import agora_iso

PASTA_ENTRADA = "entrada"
PASTA_LIDOS = "lidos"


def _texto(valor, limite: int = 240) -> str | None:
    if valor is None:
        return None
    return str(valor).strip()[:limite] or None


def _inteiro(valor) -> int | None:
    try:
        return int(float(str(valor).strip()))
    except (TypeError, ValueError):
        return None


def _decimal(valor) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).replace("R$", "").replace(" ", "").strip()
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(re.sub(r"[^\d.\-]", "", texto) or "nan")
    except ValueError:
        return None


def _mlb(valor) -> str | None:
    m = re.search(r"(ML[A-Z]?\d{6,})", str(valor or "").upper().replace("-", ""))
    return m.group(1) if m else None


def importar(con: sqlite3.Connection, conta, dados: dict, carimbo: str | None = None) -> dict:
    """
    Grava uma medição. Devolve o que entrou, para quem chamou poder mostrar.

    Tudo com o MESMO carimbo, porque as regras comparam rodada contra rodada:
    duas medições do mesmo dia com carimbos diferentes virariam uma "queda de
    posição" imaginária entre elas.
    """
    carimbo = carimbo or _texto(dados.get("medido_em")) or agora_iso()
    blocos = dados.get("termos") or []

    linhas_pos, linhas_conc = [], []
    termos_lidos = 0

    for bloco in blocos:
        termo = _texto((bloco or {}).get("termo"), 120)
        if not termo:
            continue
        termos_lidos += 1
        total = _inteiro(bloco.get("total_resultados"))

        # preço do 1º colocado: serve de régua para o alerta de posição
        preco_topo = _decimal(bloco.get("preco_topo"))
        concorrentes = bloco.get("concorrentes") or []
        if preco_topo is None:
            primeiros = [c for c in concorrentes if _inteiro((c or {}).get("posicao")) == 1]
            if primeiros:
                preco_topo = _decimal(primeiros[0].get("preco"))

        for meu in bloco.get("meus") or []:
            item_id = _mlb((meu or {}).get("item_id"))
            if not item_id:
                continue
            linhas_pos.append({
                "coletado_em": carimbo, "cliente_id": conta.cliente_id,
                "conta_slug": conta.slug, "termo": termo, "item_id": item_id,
                "posicao": _inteiro(meu.get("posicao")),
                "preco": _decimal(meu.get("preco")),
                "preco_topo": preco_topo, "total_result": total,
            })

        for rival in concorrentes:
            rival = rival or {}
            vendedor = _texto(rival.get("vendedor") or rival.get("seller_nickname"), 80)
            item_id = _mlb(rival.get("item_id") or rival.get("link"))
            if not (vendedor or item_id):
                continue
            linhas_conc.append({
                "coletado_em": carimbo, "cliente_id": conta.cliente_id,
                "conta_slug": conta.slug,
                # 'palavra-chave' é a origem que a regra de concorrente novo no
                # topo já procurava antes do bloqueio da busca. Reusar o nome
                # acorda a regra sem tocar nela.
                "origem": "palavra-chave", "referencia": termo,
                "item_id": item_id or f"busca:{vendedor}",
                "titulo": _texto(rival.get("titulo")),
                "preco": _decimal(rival.get("preco")),
                "vendidos": _inteiro(rival.get("vendidos")),
                # sem id numérico de vendedor na página, o apelido faz as vezes
                "seller_id": _texto(rival.get("seller_id")) or vendedor,
                "seller_nickname": vendedor,
                "frete_gratis": int(bool(rival.get("frete_gratis"))),
                "posicao": _inteiro(rival.get("posicao")),
                "catalogo": int(bool(rival.get("catalogo"))),
                "permalink": _texto(rival.get("link"), 500),
                "status": "active",
            })

    db.inserir_muitos(con, "snap_posicao", linhas_pos)
    db.inserir_muitos(con, "snap_concorrente", linhas_conc)
    con.commit()
    return {"carimbo": carimbo, "termos": termos_lidos,
            "posicoes": len(linhas_pos), "concorrentes": len(linhas_conc)}


def arquivos_pendentes(raiz: Path) -> list[Path]:
    pasta = raiz / "pedidos" / PASTA_ENTRADA
    if not pasta.exists():
        return []
    return sorted(p for p in pasta.glob("*.json") if p.is_file())


def arquivar(caminho: Path) -> None:
    """Move para lidos/. Reimportar o mesmo arquivo duplicaria a medição."""
    destino = caminho.parent.parent / PASTA_LIDOS
    destino.mkdir(parents=True, exist_ok=True)
    alvo = destino / caminho.name
    n = 1
    while alvo.exists():
        alvo = destino / f"{caminho.stem}-{n}{caminho.suffix}"
        n += 1
    caminho.rename(alvo)


def ler_arquivo(caminho: Path) -> dict | None:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        return None
