"""
Gerenciamento de credenciais multi-conta.

Princípio de segurança desta operação:
  - Cada conta tem UM arquivo .env, dentro da pasta da própria conta.
  - O token só é carregado quando você pede explicitamente pelo slug.
  - Não existe token "global" ou "padrão". Se o slug estiver errado,
    a chamada falha em vez de acertar a conta errada.
  - O refresh_token do ML é de USO ÚNICO: ao renovar, o novo par é
    gravado de volta no .env imediatamente.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import requests

OAUTH_URL = "https://api.mercadolibre.com/oauth/token"
MARGEM_SEGURANCA_SEG = 600  # renova 10 min antes de expirar


@dataclass
class Credencial:
    slug: str
    client_id: str
    client_secret: str
    access_token: str
    refresh_token: str
    user_id: str
    expira_em: float  # epoch


def _caminho_env(slug: str) -> Path:
    from .utils import DIR_CONTAS
    return DIR_CONTAS / slug / ".env"


def _ler_env(caminho: Path) -> dict[str, str]:
    if not caminho.exists():
        raise FileNotFoundError(
            f"Credencial não encontrada: {caminho}\n"
            f"Copie contas/_template/.env.example para essa pasta e preencha."
        )
    valores: dict[str, str] = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def _gravar_env(caminho: Path, atualizacoes: dict[str, str]) -> None:
    """Reescreve apenas as chaves informadas, preservando comentários."""
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    pendentes = dict(atualizacoes)
    saida: list[str] = []
    for linha in linhas:
        m = re.match(r"^(\s*)([A-Z0-9_]+)(\s*)=", linha)
        if m and m.group(2) in pendentes:
            chave = m.group(2)
            saida.append(f"{chave}={pendentes.pop(chave)}")
        else:
            saida.append(linha)
    for chave, valor in pendentes.items():
        saida.append(f"{chave}={valor}")
    caminho.write_text("\n".join(saida) + "\n", encoding="utf-8")
    try:
        os.chmod(caminho, 0o600)
    except OSError:
        pass


def carregar(slug: str) -> Credencial:
    caminho = _caminho_env(slug)
    env = _ler_env(caminho)

    faltando = [
        k for k in ("ML_CLIENT_ID", "ML_CLIENT_SECRET", "ML_REFRESH_TOKEN", "ML_USER_ID")
        if not env.get(k)
    ]
    if faltando:
        raise ValueError(f"[{slug}] faltam chaves no .env: {', '.join(faltando)}")

    return Credencial(
        slug=slug,
        client_id=env["ML_CLIENT_ID"],
        client_secret=env["ML_CLIENT_SECRET"],
        access_token=env.get("ML_ACCESS_TOKEN", ""),
        refresh_token=env["ML_REFRESH_TOKEN"],
        user_id=str(env["ML_USER_ID"]),
        expira_em=float(env.get("ML_TOKEN_EXPIRA_EM", 0) or 0),
    )


def renovar(cred: Credencial) -> Credencial:
    """Troca o refresh_token por um novo access_token e persiste o novo par."""
    resposta = requests.post(
        OAUTH_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": cred.client_id,
            "client_secret": cred.client_secret,
            "refresh_token": cred.refresh_token,
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if resposta.status_code != 200:
        raise RuntimeError(
            f"[{cred.slug}] falha ao renovar token ({resposta.status_code}): {resposta.text[:400]}\n"
            f"Se for 'invalid_grant', o refresh_token já foi usado ou expirou (6 meses). "
            f"Refaça o consentimento — veja docs/SETUP.md."
        )
    dados = resposta.json()

    cred.access_token = dados["access_token"]
    cred.refresh_token = dados.get("refresh_token", cred.refresh_token)
    cred.expira_em = time.time() + float(dados.get("expires_in", 21600))

    _gravar_env(
        _caminho_env(cred.slug),
        {
            "ML_ACCESS_TOKEN": cred.access_token,
            "ML_REFRESH_TOKEN": cred.refresh_token,
            "ML_TOKEN_EXPIRA_EM": str(int(cred.expira_em)),
        },
    )
    return cred


def token_valido(slug: str) -> Credencial:
    """Ponto de entrada único: devolve credencial com access_token utilizável."""
    cred = carregar(slug)
    if not cred.access_token or time.time() >= cred.expira_em - MARGEM_SEGURANCA_SEG:
        cred = renovar(cred)
    return cred
