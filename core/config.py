"""
Carregamento de configuração: registro de clientes, contas e regras.

Regra de ouro desta camada: uma Conta SEMPRE sabe a que Cliente pertence,
e credencial NUNCA vem daqui — vem de core.auth, lendo o .env isolado
da pasta da própria conta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .utils import DIR_CONFIG, DIR_CONTAS


@dataclass
class Conta:
    slug: str
    nome_conta: str
    site_id: str
    user_id: str
    papel: str
    cliente_id: str
    cliente_nome: str
    coordenar_preco: bool = False
    observacoes: str = ""
    palavras_chave: list[dict] = field(default_factory=list)
    concorrentes: list[dict] = field(default_factory=list)
    produtos_vigiados: list[dict] = field(default_factory=list)
    parametros: dict = field(default_factory=dict)

    @property
    def dir(self) -> Path:
        return DIR_CONTAS / self.slug

    @property
    def configurada(self) -> bool:
        return bool(self.user_id) and self.user_id != "SUBSTITUIR"

    def __str__(self) -> str:
        return f"{self.cliente_nome} / {self.nome_conta} ({self.slug})"


@dataclass
class Cliente:
    id: str
    nome: str
    nicho: str
    status: str
    coordenar_preco: bool
    contas: list[Conta]


def _ler_yaml(caminho: Path) -> dict:
    if not caminho.exists():
        return {}
    with caminho.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def carregar_regras() -> dict:
    return _ler_yaml(DIR_CONFIG / "alertas.yaml").get("regras", {})


def _carregar_extras_da_conta(conta: Conta) -> None:
    """Lê os arquivos que moram na pasta da conta (nunca no registro central)."""
    base = conta.dir
    conta.palavras_chave = _ler_yaml(base / "palavras-chave.yaml").get("palavras_chave", [])
    _conc = _ler_yaml(base / "concorrentes.yaml")
    # 'concorrentes' era a lista de anúncios vigiados por ID. O Mercado Livre
    # passou a recusar leitura de anúncio de terceiro (403), então a lista não
    # tem mais efeito. Continua sendo lida para não quebrar arquivo antigo de
    # cliente, e é ignorada pelo resto do sistema.
    conta.concorrentes = _conc.get("concorrentes") or []
    conta.produtos_vigiados = _conc.get("produtos_vigiados") or []
    conta.parametros = _ler_yaml(base / "conta.yaml").get("parametros", {})


def carregar_clientes(apenas_ativos: bool = True) -> list[Cliente]:
    dados = _ler_yaml(DIR_CONFIG / "clientes.yaml")
    clientes: list[Cliente] = []

    for c in dados.get("clientes", []):
        status = c.get("status", "ativo")
        if apenas_ativos and status != "ativo":
            continue

        coordenar = bool(c.get("coordenar_preco", False))
        contas: list[Conta] = []

        for ct in c.get("contas", []):
            contas.append(
                Conta(
                    slug=ct["slug"],
                    nome_conta=ct.get("nome_conta", ct["slug"]),
                    site_id=ct.get("site_id", "MLB"),
                    user_id=str(ct.get("user_id", "")),
                    papel=ct.get("papel", "principal"),
                    cliente_id=c["id"],
                    cliente_nome=c.get("nome", c["id"]),
                    coordenar_preco=coordenar,
                    observacoes=ct.get("observacoes", ""),
                )
            )

        clientes.append(
            Cliente(
                id=c["id"],
                nome=c.get("nome", c["id"]),
                nicho=c.get("nicho", ""),
                status=status,
                coordenar_preco=coordenar,
                contas=contas,
            )
        )

    for cliente in clientes:
        for conta in cliente.contas:
            _carregar_extras_da_conta(conta)

    return clientes


def todas_as_contas(apenas_ativos: bool = True) -> list[Conta]:
    return [ct for cl in carregar_clientes(apenas_ativos) for ct in cl.contas]


def obter_conta(slug: str) -> Conta:
    for conta in todas_as_contas(apenas_ativos=False):
        if conta.slug == slug:
            return conta
    disponiveis = ", ".join(c.slug for c in todas_as_contas(apenas_ativos=False))
    raise KeyError(f"Conta '{slug}' não existe no registro. Disponíveis: {disponiveis}")


def resolver_contas(alvo: str | None, exigir_credencial: bool = True) -> list[Conta]:
    """
    Resolve o alvo de um comando.
      None / 'todas'  -> todas as contas ativas
      '<cliente_id>'  -> todas as contas daquele cliente
      '<slug>'        -> uma conta só

    exigir_credencial=True (padrão) filtra contas sem user_id — é o correto para
    comandos que falam com a API. Comandos de leitura do banco (alertas,
    relatório) passam False, porque dados históricos existem mesmo para uma
    conta que já foi desligada.
    """
    if alvo in (None, "", "todas", "all"):
        contas = todas_as_contas()
        return [c for c in contas if c.configurada] if exigir_credencial else contas

    for cliente in carregar_clientes(apenas_ativos=False):
        if cliente.id == alvo:
            return [c for c in cliente.contas if c.configurada or not exigir_credencial]

    conta = obter_conta(alvo)
    if exigir_credencial and not conta.configurada:
        raise ValueError(
            f"Conta '{alvo}' ainda está sem user_id no registro (config/clientes.yaml)."
        )
    return [conta]
