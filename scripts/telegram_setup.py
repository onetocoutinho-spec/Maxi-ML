#!/usr/bin/env python3
"""
Configura o Telegram como canal de alertas — interativo, do zero ao teste.

  python scripts/telegram_setup.py

Ele valida o token, descobre o chat_id sozinho (você só manda uma mensagem
para o bot), grava o .env da raiz, aponta o provedor em notificacoes.yaml
e manda uma mensagem de teste para confirmar.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests

RAIZ = Path(__file__).resolve().parent.parent

try:
    from core.utils import cor
except Exception:
    def cor(c):
        return c if os.name != "nt" or os.environ.get("WT_SESSION") else ""

VERDE, VERM, AMAR, CINZA, FIM = (
    cor("\033[32m"), cor("\033[31m"), cor("\033[33m"), cor("\033[90m"), cor("\033[0m")
)


def instrucoes() -> None:
    print(f"""
{'─' * 68}
  CRIAR O BOT (leva ~2 minutos, é grátis)
{'─' * 68}

  1. No Telegram, procure por  @BotFather  e abra a conversa.
  2. Mande:  /newbot
  3. Escolha um nome  (ex: Zion ML Alertas)
  4. Escolha um usuário terminando em 'bot'  (ex: zion_ml_alertas_bot)
  5. Ele responde com um token parecido com:
       1234567890:AAF-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

  Cole esse token abaixo.
{'─' * 68}
""")


def validar_token(token: str) -> dict | None:
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20)
    except requests.RequestException as erro:
        print(f"{VERM}Sem conexão com o Telegram: {erro}{FIM}")
        return None
    if r.status_code != 200:
        print(f"{VERM}Token recusado ({r.status_code}). Confira se copiou inteiro.{FIM}")
        return None
    return r.json().get("result")


def descobrir_chat_id(token: str, espera_max: int = 120) -> str | None:
    """Aguarda o usuário mandar qualquer mensagem para o bot e captura o chat."""
    print(f"\n{AMAR}Agora abra a conversa com o seu bot no Telegram e mande "
          f"qualquer mensagem{FIM} (um 'oi' basta).")
    print(f"{CINZA}Aguardando… (Ctrl+C para cancelar){FIM}\n")

    inicio = time.time()
    ultimo = 0
    while time.time() - inicio < espera_max:
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates",
                             params={"offset": ultimo, "timeout": 10}, timeout=25)
            dados = r.json()
        except requests.RequestException:
            time.sleep(2)
            continue

        for upd in dados.get("result", []):
            ultimo = max(ultimo, upd.get("update_id", 0) + 1)
            msg = upd.get("message") or upd.get("channel_post") or {}
            chat = msg.get("chat") or {}
            if chat.get("id"):
                nome = chat.get("first_name") or chat.get("title") or chat.get("username") or "?"
                print(f"{VERDE}Recebi de: {nome}{FIM}  (chat_id {chat['id']})")
                return str(chat["id"])

        restante = int(espera_max - (time.time() - inicio))
        print(f"\r{CINZA}aguardando mensagem… {restante}s{FIM}   ", end="", flush=True)

    print(f"\n{VERM}Não chegou mensagem nenhuma.{FIM}")
    return None


def gravar_env(token: str, chat_id: str) -> None:
    caminho = RAIZ / ".env"
    valores: dict[str, str] = {}
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                k, _, v = linha.partition("=")
                valores[k.strip()] = v.strip()

    valores["TELEGRAM_BOT_TOKEN"] = token
    valores["TELEGRAM_CHAT_ID"] = chat_id

    caminho.write_text(
        "# Credenciais dos canais de notificação. Não versionar.\n"
        + "\n".join(f"{k}={v}" for k, v in sorted(valores.items())) + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(caminho, 0o600)
    except OSError:
        pass
    print(f"{VERDE}Gravado: .env{FIM}")


def apontar_provedor() -> None:
    caminho = RAIZ / "config" / "notificacoes.yaml"
    texto = caminho.read_text(encoding="utf-8")
    novo = re.sub(r"^provedor:\s*\S+", "provedor: telegram", texto, count=1, flags=re.M)
    if novo != texto:
        caminho.write_text(novo, encoding="utf-8")
        print(f"{VERDE}provedor: telegram{FIM} em config/notificacoes.yaml")


def main() -> int:
    instrucoes()

    token = input("Token do bot: ").strip()
    if not token:
        print("Cancelado.")
        return 1

    info = validar_token(token)
    if not info:
        return 1
    print(f"{VERDE}Bot válido:{FIM} @{info.get('username')} ({info.get('first_name')})")

    chat_id = descobrir_chat_id(token)
    if not chat_id:
        print(f"\n{CINZA}Se você mandou mensagem e mesmo assim não funcionou, confira")
        print(f"se abriu a conversa com o bot certo — o @username tem que bater.{FIM}")
        return 1

    gravar_env(token, chat_id)
    apontar_provedor()

    print(f"\n{CINZA}Mandando mensagem de teste…{FIM}")
    from core import notify
    r = notify.enviar(
        "*Zion ML* — canal configurado.\n\n"
        "A partir de agora os alertas críticos chegam aqui sozinhos, "
        "e o resumo do dia sai às 8h."
    )
    if r.ok:
        print(f"{VERDE}Chegou? Então está pronto.{FIM}")
        print(f"\nPróximo passo: duplo clique em {AMAR}agendar.bat{FIM} "
              f"para rodar a cada 3 horas.")
        return 0

    print(f"{VERM}A mensagem de teste falhou:{FIM} {r.detalhe}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ncancelado")
        sys.exit(130)
