"""Utilidades comuns: tempo, formatação e caminhos."""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Fuso de operação (Brasil). Todo carimbo de tempo salvo no banco é UTC ISO;
# tudo que é EXIBIDO ao operador é convertido para cá.
TZ_BR = timezone(timedelta(hours=-3))

RAIZ = Path(__file__).resolve().parent.parent
DIR_CONFIG = RAIZ / "config"
DIR_CONTAS = RAIZ / "contas"
DIR_DADOS = RAIZ / "data"
DIR_RELATORIOS = RAIZ / "relatorios"


def _cores_suportadas() -> bool:
    """cmd.exe antigo e saída redirecionada não entendem ANSI — melhor não sujar."""
    import sys
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        # Windows Terminal / PowerShell moderno definem WT_SESSION ou aceitam VT
        if os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"):
            return True
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            return True
        except Exception:
            return False
    return True


CORES = _cores_suportadas()


def cor(codigo: str) -> str:
    return codigo if CORES else ""


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def agora_iso() -> str:
    return agora_utc().isoformat(timespec="seconds")


def para_br(iso: str) -> str:
    """Converte um ISO UTC para string legível no fuso de São Paulo."""
    if not iso:
        return "-"
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_BR).strftime("%d/%m/%Y %H:%M")


def brl(valor) -> str:
    """Formata número como moeda brasileira."""
    if valor is None:
        return "-"
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(novo, antigo):
    """Variação percentual entre dois números. None se não der para calcular."""
    try:
        antigo = float(antigo)
        novo = float(novo)
    except (TypeError, ValueError):
        return None
    if antigo == 0:
        return None
    return (novo - antigo) / antigo * 100.0


def garantir_dir(caminho: Path) -> Path:
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def truncar(texto: str, limite: int = 60) -> str:
    """Corta no espaço mais próximo, não no meio da palavra, e normaliza
    espaços duplos — título de marketplace vem cheio deles."""
    texto = " ".join((texto or "").split())
    if len(texto) <= limite:
        return texto
    corte = texto[:limite].rsplit(" ", 1)[0]
    return (corte or texto[:limite]).rstrip(" ,-") + "…"


def preco_real(linha, vitrines: dict | None = None) -> float | None:
    """
    O preço que vale para comparar: o da vitrine quando existe, o de cadastro
    quando não.

    Duas fontes porque o campo `price` da API do item ignora campanha
    promocional. Comparar preço de tabela seu com preço real do concorrente
    inverte a conclusão — foi assim que o sistema anunciou que o SKYIFLEX
    estava 29% abaixo quando os dois estavam empatados na tela.
    """
    try:
        vitrine = linha["preco_vitrine"]
    except (KeyError, IndexError, TypeError):
        vitrine = None
    if isinstance(vitrine, (int, float)) and vitrine > 0:
        return float(vitrine)

    # A vitrine só é medida na passada larga do dia; nos ciclos curtos do vigia
    # a coluna vem NULA. Cair no preço de cadastro nessa hora reintroduz
    # exatamente o erro que esta função existe para evitar — foi o que fez o
    # alerta das 07:36 dizer que o SKYIFLEX estava 29,2% abaixo comparando o
    # preço de tabela do Ênio (R$ 1.932,99) com o preço real do outro, quando
    # na vitrine os dois estavam a R$ 1.380,99 contra R$ 1.369,07.
    #
    # É o mesmo remédio do frete: quem chama traz a última medição NÃO NULA de
    # cada anúncio, e o cadastro fica como último recurso.
    if vitrines:
        try:
            recente = vitrines.get(linha["item_id"])
        except (KeyError, IndexError, TypeError):
            recente = None
        if isinstance(recente, (int, float)) and recente > 0:
            return float(recente)
    try:
        preco = linha["preco"]
    except (KeyError, IndexError, TypeError):
        return None
    return float(preco) if isinstance(preco, (int, float)) else None
