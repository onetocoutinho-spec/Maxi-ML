"""
Foto de capa ambientada de um anúncio, via API de imagens da OpenAI.

Por que mora aqui e não em mcp_zion.py: o servidor MCP tem duas regras que
não negociam — só lê, e só fala com rede na ferramenta `checar_credencial`.
Gerar imagem custa dinheiro por chamada e fala com a OpenAI, então corre pela
MESMA fila que `coletar`/`mapear` já usam (scripts/fila.py -> cli.py), nunca
direto do processo do MCP. Ver `encomendar` em mcp_zion.py.

A referência do produto é a própria thumbnail já coletada em snap_anuncio —
não pedimos foto nova a ninguém, só ambientamos a que já existe no anúncio.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

import requests

from .utils import RAIZ

DIR_SAIDA = RAIZ / "imagens_geradas"
MODELO = "gpt-image-1"
ENDPOINT_EDITS = "https://api.openai.com/v1/images/edits"
TAMANHO = "1024x1024"
TEMPO_LIMITE = 120


def _env_raiz() -> dict[str, str]:
    """Mesmo parser do .env da raiz usado em core/notify.py — sem dependência nova."""
    caminho = RAIZ / ".env"
    valores: dict[str, str] = {}
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, _, v = linha.partition("=")
                valores[k.strip()] = v.strip().strip('"').strip("'")
    return valores


def _chave_openai() -> str:
    import os
    chave = _env_raiz().get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not chave:
        raise RuntimeError(
            "OPENAI_API_KEY não configurada em .env (raiz). "
            "Adicione a linha OPENAI_API_KEY=... sem apagar o resto do arquivo."
        )
    return chave


def _prompt_padrao(titulo: str) -> str:
    return (
        f"Gere uma foto de capa ambientada para anúncio de e-commerce, a partir do "
        f"produto '{titulo}' mostrado na imagem anexada. Coloque-o num ambiente "
        f"residencial moderno e aconchegante coerente com o produto (sala de estar, "
        f"quarto ou espaço correspondente), com luz natural suave lateral e "
        f"decoração discreta ao fundo (tapete, planta, quadro). O produto em "
        f"destaque, levemente angulado para a câmera, mantendo fielmente a cor e o "
        f"material reais mostrados na referência. Estilo fotografia profissional de "
        f"decoração, sem texto, sem marca d'água, sem logotipo."
    )


def _buscar_anuncio(con, conta_slug: str, item_id: str) -> dict | None:
    carimbo = con.execute(
        "SELECT MAX(coletado_em) FROM snap_anuncio WHERE conta_slug = ?",
        (conta_slug,),
    ).fetchone()[0]
    if not carimbo:
        return None
    linha = con.execute(
        "SELECT item_id, titulo, sku, thumbnail, permalink FROM snap_anuncio "
        "WHERE conta_slug = ? AND coletado_em = ? AND item_id = ?",
        (conta_slug, carimbo, item_id),
    ).fetchone()
    return dict(linha) if linha else None


def gerar_imagem_ambientada(con, conta_slug: str, item_id: str,
                            prompt: str | None = None) -> dict:
    """
    Busca o anúncio no snapshot mais recente da conta, baixa a thumbnail atual
    como referência, pede à OpenAI uma versão ambientada e salva o PNG em
    imagens_gerados/<slug>/<item_id>.png. Cada chamada tem custo real na
    OpenAI — não simula.
    """
    anuncio = _buscar_anuncio(con, conta_slug, item_id)
    if not anuncio:
        return {"item_id": item_id, "erro": "anúncio não encontrado no snapshot "
                 "mais recente desta conta — rode uma coleta antes"}
    if not anuncio.get("thumbnail"):
        return {"item_id": item_id, "titulo": anuncio.get("titulo"),
                "erro": "anúncio sem thumbnail no snapshot"}

    referencia = requests.get(anuncio["thumbnail"], timeout=30)
    referencia.raise_for_status()

    prompt_final = prompt or _prompt_padrao(anuncio["titulo"] or item_id)

    resposta = requests.post(
        ENDPOINT_EDITS,
        headers={"Authorization": f"Bearer {_chave_openai()}"},
        files={"image": ("referencia.jpg", referencia.content, "image/jpeg")},
        data={"model": MODELO, "prompt": prompt_final, "size": TAMANHO, "n": "1"},
        timeout=TEMPO_LIMITE,
    )
    if resposta.status_code >= 400:
        return {"item_id": item_id, "titulo": anuncio["titulo"],
                "erro": f"OpenAI recusou (HTTP {resposta.status_code}): "
                        f"{resposta.text[:500]}"}

    corpo = resposta.json()
    dados = (corpo.get("data") or [{}])[0]
    b64 = dados.get("b64_json")
    if not b64:
        return {"item_id": item_id, "titulo": anuncio["titulo"],
                "erro": "OpenAI não devolveu imagem (resposta sem b64_json)"}

    pasta = DIR_SAIDA / re.sub(r"[^a-z0-9\-]+", "-", conta_slug.lower())
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{item_id}.png"
    destino.write_bytes(base64.b64decode(b64))

    return {
        "item_id": item_id,
        "titulo": anuncio["titulo"],
        "sku": anuncio.get("sku"),
        "permalink": anuncio.get("permalink"),
        "arquivo": str(destino),
        "prompt_usado": prompt_final,
    }
