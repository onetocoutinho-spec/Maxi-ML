#!/usr/bin/env python3
"""
Fila de pedidos — permite que uma tarefa seja encomendada por ARQUIVO e
executada pela rotina, sem ninguém clicar em nada.

Existe por um motivo prático: o Claude escreve arquivos nesta pasta, mas não
tem terminal nesta máquina. Deixando um pedido aqui, a rotina da próxima hora
executa e devolve o resultado em pedidos/feitos/ — que o Claude consegue ler.

SEGURANÇA: nada aqui executa texto livre. Só comandos de uma lista fixa, com
argumentos validados por formato. Um pedido malformado é recusado e arquivado,
nunca interpretado. Isto NÃO é um terminal remoto, e não deve virar um.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PEDIDOS = RAIZ / "pedidos"
FEITOS = PEDIDOS / "feitos"

# Cada comando declara quais opções aceita e o formato de cada valor.
# O que não estiver aqui não roda.
PERMITIDOS: dict[str, dict] = {
    "coletar":      {"alvo": r"^[a-z0-9\-]{2,40}|todas$",
                     "flags": {"--sem-visitas"}},
    "mapear":       {"alvo": r"^[a-z0-9\-]{2,40}|todas$",
                     "opcoes": {"--cep": r"^\d{8}$"},
                     "flags": {"--sem-frete", "--detalhado"}},
    "diagnostico":  {"alvo": r"^[a-z0-9\-]{2,40}|todas$",
                     "flags": {"--enviar", "--detalhado"}},
    "relatorio":    {"alvo": r"^[a-z0-9\-]{2,40}$"},
    "notificar":    {"alvo": r"^[a-z0-9\-]{2,40}|todas$",
                     "flags": {"--resumo", "--semanal"}},
    "alertas":      {"alvo": r"^[a-z0-9\-]{2,40}|todas$",
                     "opcoes": {"--horas": r"^\d{1,4}$"}},
    "contas":       {},
    "contatos":     {},
    # Sem argumento nenhum: só lê o estado da máquina e imprime. É a forma
    # de diagnosticar o ambiente à distância sem abrir um terminal aqui.
    "maquina":      {},
    "precos":       {"alvo": r"^[a-z0-9\-]{2,40}|todas$",
                     "flags": {"--modelo"}},
    # Só lê e imprime: consulta a tabela de tarifas do ML para os anúncios
    # já coletados. Não altera nada na conta.
    "tarifas":      {"alvo": r"^[a-z0-9\-]{2,40}$"},
    # Sonda de leitura: pergunta ao ML quais campanhas estão abertas.
    # Não aceita nem entra em promoção nenhuma — só lê e imprime.
    "promocoes":    {"alvo": r"^[a-z0-9\-]{2,40}$",
                     "flags": {"--usar-cache"}},
    # Campanhas de cupom do vendedor. Também só lê: pergunta quantos cupons
    # foram usados e quanto do orçamento já queimou. --sondar-vendas varre os
    # pedidos atrás dos campos de cupom e não grava nada.
    "cupons":       {"alvo": r"^([a-z0-9\-]{2,40}|todas)$",
                     "opcoes": {"--horas": r"^\d{1,4}$", "--dias": r"^\d{1,3}$",
                                "--desde": r"^\d{4}-\d{2}-\d{2}$",
                                # sem isto a coleta pela fila para em 500
                                # pedidos, que numa conta de ~470/dia é menos
                                # de dois dias — e o resumo sai pela metade.
                                "--limite": r"^\d{1,6}$"},
                     "flags": {"--usar-cache", "--sondar-vendas", "--vendas", "--refazer",
                               "--resumo", "--pagina", "--enviar"}},
    # Apaga alerta de UMA regra nomeada, numa janela de horas. Existe para
    # descartar uma leva errada antes que ela chegue no canal. Não aceita
    # apagar tudo: --regra é obrigatório aqui, ainda que o comando permita.
    "limpar-alertas": {"opcoes": {"--horas": r"^\d{1,3}$",
                                  "--regra": r"^[a-z_]{3,40}$"},
                       "flags": {"--sim"},
                       "obrigatorias": {"--regra", "--sim"}},
    # Sem argumento: lê o que estiver em pedidos/entrada/ e arquiva.
    "posicoes":     {},
    "vendas":       {"alvo": r"^[a-z0-9\-]{2,40}$",
                     "opcoes": {"--dias": r"^\d{1,3}$"}},
    "compactar":    {"opcoes": {"--dias": r"^\d{1,4}$"},
                     "flags": {"--simular"}},
    "checar":       {"alvo": r"^[a-z0-9\-]{2,40}$"},
    # Foto de capa ambientada via API da OpenAI. Custa dinheiro real por
    # chamada — por isso NÃO aceita --prompt por arquivo (texto livre viria
    # de quem quer que consiga escrever em pedidos/, e o prompt entraria
    # direto numa chamada paga). Só o par slug+MLB, sempre com o prompt
    # padrão do core/imagens.py.
    "imagem-ambientada": {"posicionais": [r"^[a-z0-9\-]{2,40}$",
                                          r"^ML[A-Z]?\d{6,}$"]},
    "vigiar":       {"posicionais": [r"^[a-z0-9\-]{2,40}$",
                                     r"^https?://[\w\.\-/%?=&]{10,400}$|^ML[A-Z]?\d{6,}$"],
                     "opcoes": {"--comparar-com": r"^ML[A-Z]?\d{6,}$",
                                "--apelido": r"^[\w \-\.,ãáàâçéêíóôõúü×x]{1,60}$"}},
}

LIMITE_SEGUNDOS = 900


def _python() -> str:
    venv = RAIZ / ".venv" / "Scripts" / "python.exe"
    if venv.exists():
        return str(venv)
    venv = RAIZ / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def montar_argumentos(pedido: dict) -> list[str] | str:
    """Devolve a lista de argumentos, ou uma string explicando a recusa."""
    comando = str(pedido.get("comando", "")).strip()
    regras = PERMITIDOS.get(comando)
    if regras is None:
        return f"comando '{comando}' não está na lista de permitidos"

    args = [comando]

    for i, formato in enumerate(regras.get("posicionais", [])):
        valores = pedido.get("posicionais") or []
        if i >= len(valores):
            return f"faltou o argumento {i + 1} de '{comando}'"
        valor = str(valores[i])
        if not re.match(formato, valor):
            return f"argumento {i + 1} de '{comando}' tem formato inválido"
        args.append(valor)

    if "alvo" in regras:
        alvo = str(pedido.get("alvo", "todas"))
        if not re.match(regras["alvo"], alvo):
            return f"alvo '{alvo}' tem formato inválido"
        args.append(alvo)

    for opcao, valor in (pedido.get("opcoes") or {}).items():
        formato = (regras.get("opcoes") or {}).get(opcao)
        if not formato:
            return f"opção '{opcao}' não é aceita em '{comando}'"
        if not re.match(formato, str(valor)):
            return f"valor de '{opcao}' tem formato inválido"
        args.extend([opcao, str(valor)])

    for flag in (pedido.get("flags") or []):
        if flag not in (regras.get("flags") or set()):
            return f"flag '{flag}' não é aceita em '{comando}'"
        args.append(flag)

    # Alguns comandos só são seguros com um recorte explícito. 'limpar-alertas'
    # sem --regra apagaria a fila inteira; pela fila de pedidos, que roda sem
    # ninguém olhando, isso não pode ser um esquecimento.
    faltando = [o for o in (regras.get("obrigatorias") or set()) if o not in args]
    if faltando:
        return (f"'{comando}' exige {', '.join(sorted(faltando))} quando pedido "
                f"por arquivo")

    return args


def executar(caminho: Path) -> None:
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    destino = FEITOS / f"{caminho.stem}.log"
    FEITOS.mkdir(parents=True, exist_ok=True)

    try:
        pedido = json.loads(caminho.read_text(encoding="utf-8"))
    except Exception as erro:
        destino.write_text(f"[{agora}] RECUSADO: arquivo não é JSON válido — {erro}\n",
                           encoding="utf-8")
        caminho.unlink(missing_ok=True)
        return

    args = montar_argumentos(pedido)
    if isinstance(args, str):
        destino.write_text(f"[{agora}] RECUSADO: {args}\n\npedido:\n"
                           f"{json.dumps(pedido, ensure_ascii=False, indent=2)}\n",
                           encoding="utf-8")
        caminho.unlink(missing_ok=True)
        return

    linha = " ".join(args)
    try:
        saida = subprocess.run(
            [_python(), str(RAIZ / "cli.py"), *args],
            cwd=str(RAIZ), capture_output=True, text=True,
            timeout=LIMITE_SEGUNDOS, encoding="utf-8", errors="replace",
        )
        corpo = (f"[{agora}] EXECUTADO: cli.py {linha}\n"
                 f"código de saída: {saida.returncode}\n"
                 f"{'-' * 60}\n{saida.stdout}\n")
        if saida.stderr.strip():
            corpo += f"{'-' * 60}\nerros:\n{saida.stderr}\n"
    except subprocess.TimeoutExpired:
        corpo = (f"[{agora}] TEMPO ESGOTADO: cli.py {linha}\n"
                 f"passou de {LIMITE_SEGUNDOS}s e foi interrompido.\n")
    except Exception as erro:
        corpo = f"[{agora}] FALHOU: cli.py {linha}\n{erro}\n"

    destino.write_text(corpo, encoding="utf-8")
    caminho.unlink(missing_ok=True)


def main() -> int:
    PEDIDOS.mkdir(parents=True, exist_ok=True)
    FEITOS.mkdir(parents=True, exist_ok=True)

    pendentes = sorted(PEDIDOS.glob("*.pedido"))
    if not pendentes:
        return 0

    print(f"fila: {len(pendentes)} pedido(s)")
    for caminho in pendentes:
        print(f"  executando {caminho.name}")
        executar(caminho)

    # não deixa o histórico crescer para sempre
    logs = sorted(FEITOS.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for antigo in logs[60:]:
        antigo.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
