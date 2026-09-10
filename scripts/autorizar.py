#!/usr/bin/env python3
"""
Autoriza UMA conta do Mercado Livre e grava o .env dela — interativo.

  python scripts/autorizar.py <slug>
  python scripts/autorizar.py <slug> --pkce          # se o app tem PKCE ativado
  python scripts/autorizar.py slug1 slug2 slug3      # várias contas numa sentada

O que ele faz por você:
  1. reaproveita o App ID/Secret de outra conta já configurada (o app é o mesmo)
  2. monta a URL de autorização com 'state' (e PKCE, se pedido)
  3. troca o code por tokens
  4. confirma em qual conta o token caiu ANTES de gravar
  5. grava o .env com permissão 600
  6. escreve o user_id direto no config/clientes.yaml

Com vários slugs, o App ID e a Secret são pedidos uma vez só e ele passa
pelas contas em sequência.

Nada é gravado se o nickname devolvido não for confirmado por você.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import re
import secrets
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows: quando a saída vai para arquivo (log da rotina agendada), o Python
# usa a codificação local (cp1252) e quebra em acento ou símbolo. Forçar UTF-8
# aqui evita UnicodeEncodeError derrubar a coleta no meio.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests

RAIZ = Path(__file__).resolve().parent.parent


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
CONTAS = RAIZ / "contas"
AUTH_BASE = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"

try:
    from core.utils import cor
except Exception:
    def cor(c):
        return c if os.name != "nt" or os.environ.get("WT_SESSION") else ""

VERDE, VERM, AMAR, CINZA, FIM = (
    cor("\033[32m"), cor("\033[31m"), cor("\033[33m"), cor("\033[90m"), cor("\033[0m")
)


def perguntar(rotulo: str, padrao: str = "", secreto: bool = False) -> str:
    """
    Campo secreto não mostra nada enquanto você digita ou cola — nem asterisco.
    Isso confunde muita gente, então avisamos antes e oferecemos modo visível
    se a primeira tentativa vier vazia.
    """
    sufixo = " [Enter mantém o atual]" if padrao else ""

    if not secreto:
        try:
            return input(f"{rotulo}{sufixo}: ").strip() or padrao
        except EOFError:
            return padrao

    print(f"\n{CINZA}A digitação abaixo fica INVISÍVEL (nem asterisco aparece).")
    if os.name == "nt":
        print(f"No console do Windows, cole com o BOTÃO DIREITO do mouse — Ctrl+V")
        print(f"pode não funcionar. Depois aperte Enter mesmo sem ver nada.{FIM}")
    else:
        print(f"Cole e aperte Enter mesmo sem ver nada.{FIM}")

    try:
        valor = getpass.getpass(f"{rotulo}{sufixo}: ").strip()
    except Exception:
        valor = ""

    if valor or padrao:
        return valor or padrao

    print(f"\n{AMAR}Veio vazio. Vamos de novo, agora com o texto VISÍVEL na tela.{FIM}")
    print(f"{CINZA}Só faça isso se ninguém estiver olhando — e limpe a tela depois")
    print(f"com o comando 'cls'.{FIM}")
    try:
        return input(f"{rotulo} (visível): ").strip()
    except EOFError:
        return ""


def app_de_outra_conta() -> tuple[str, str, str]:
    """Procura client_id/secret/redirect já preenchidos em outra conta."""
    for env in sorted(CONTAS.glob("*/.env")):
        valores = {}
        for linha in env.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                k, _, v = linha.partition("=")
                valores[k.strip()] = v.strip().strip('"').strip("'")
        if valores.get("ML_CLIENT_ID") and valores.get("ML_CLIENT_SECRET"):
            return (valores["ML_CLIENT_ID"], valores["ML_CLIENT_SECRET"],
                    valores.get("ML_REDIRECT_URI", ""))
    return ("", "", "")


def gravar_user_id(slug: str, user_id: str) -> bool:
    """
    Troca o user_id da conta em config/clientes.yaml, preservando comentários.
    Localiza a linha 'slug: <slug>' e a primeira 'user_id:' logo abaixo dela.
    """
    caminho = RAIZ / "config" / "clientes.yaml"
    linhas = caminho.read_text(encoding="utf-8").splitlines()

    dentro = False
    for i, linha in enumerate(linhas):
        if re.match(rf"^\s*-?\s*slug:\s*[\"\']?{re.escape(slug)}[\"\']?\s*$", linha):
            dentro = True
            continue
        if dentro:
            # outro slug começou antes de achar o user_id — aborta por segurança
            if re.match(r"^\s*-\s*slug:", linha):
                return False
            m = re.match(r"^(\s*)user_id:\s*.*$", linha)
            if m:
                comentario = ""
                if "#" in linha:
                    comentario = "  # " + linha.split("#", 1)[1].strip()
                linhas[i] = f'{m.group(1)}user_id: "{user_id}"{comentario}'
                caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
                return True
    return False


def extrair_code(entrada: str) -> str:
    """Aceita o code puro ou a URL inteira colada da barra de endereço."""
    entrada = entrada.strip()
    if entrada.startswith("http"):
        query = urllib.parse.urlparse(entrada).query
        params = urllib.parse.parse_qs(query)
        if "code" in params:
            return params["code"][0]
        if "error" in params:
            raise SystemExit(f"{VERM}O Mercado Livre devolveu erro: "
                             f"{params.get('error_description', params['error'])[0]}{FIM}")
        raise SystemExit(
            f"{VERM}Não achei '?code=' nessa URL.{FIM}\n"
            f"Você colou o endereço de redirect puro. O que preciso é a URL da\n"
            f"barra de endereço DEPOIS de aceitar a autorização — a mesma coisa,\n"
            f"mas com '?code=TG-...&state=...' grudado no fim.")
    return entrada



PENDENTES = RAIZ / "data" / "autorizacao_pendente.json"


def _ler_pendentes() -> dict:
    try:
        return json.loads(PENDENTES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _gravar_pendentes(dados: dict) -> None:
    PENDENTES.parent.mkdir(parents=True, exist_ok=True)
    PENDENTES.write_text(json.dumps(dados, indent=1, ensure_ascii=False),
                         encoding="utf-8")


def montar_pedido(slug: str, client_id: str, redirect_uri: str,
                  usar_pkce: bool) -> str:
    """
    Monta o endereço de consentimento e GUARDA o que a troca vai precisar.

    Existe porque a conta nem sempre está na máquina de quem opera. Quando ela
    está com o cliente, o consentimento acontece no navegador DELE — e aí as
    duas metades do fluxo ficam separadas no tempo: o link sai hoje, o code
    volta quando a pessoa puder.

    O 'state' e o 'code_verifier' nascem aqui e são conferidos na volta. Sem
    gravar em disco eles morriam junto com o processo, e a conferência de
    state (que é o que protege contra colar o code de outra conta) viraria
    letra morta. O que fica no arquivo não é credencial: é um número aleatório
    de uso único. Secret nenhuma passa por aqui.
    """
    state = secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    code_verifier = ""
    if usar_pkce:
        code_verifier = base64.urlsafe_b64encode(os.urandom(48)).decode().rstrip("=")
        params["code_challenge"] = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()).decode().rstrip("=")
        params["code_challenge_method"] = "S256"

    pendentes = _ler_pendentes()
    pendentes[slug] = {
        "state": state,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "criado_em": agora_iso(),
    }
    _gravar_pendentes(pendentes)
    return f"{AUTH_BASE}?{urllib.parse.urlencode(params)}"


def autorizar_uma(slug: str, client_id: str, client_secret: str,
                  redirect_uri: str, usar_pkce: bool) -> bool:
    """Autoriza uma conta. Devolve True se gravou o .env."""
    destino = CONTAS / slug / ".env"
    if destino.exists():
        resp = input(f"{AMAR}Já existe .env em contas/{slug}. Sobrescrever? (s/N) {FIM}").strip().lower()
        if resp != "s":
            print(f"{CINZA}Pulando {slug}.{FIM}")
            return False

    state = secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }

    code_verifier = ""
    if usar_pkce:
        code_verifier = base64.urlsafe_b64encode(os.urandom(48)).decode().rstrip("=")
        desafio = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip("=")
        params["code_challenge"] = desafio
        params["code_challenge_method"] = "S256"

    url = f"{AUTH_BASE}?{urllib.parse.urlencode(params)}"

    print(f"\n{'─' * 72}")
    print(f"{AMAR}CONTA: {slug}{FIM}")
    print(f"{AMAR}Abra em JANELA ANÔNIMA, logado NESTA conta:{FIM}\n")
    print(url)
    print(f"\n{CINZA}Janela anônima não é frescura: autorizar estando logado em outra")
    print(f"conta é o jeito mais comum de gravar a credencial errada.{FIM}")
    print(f"{'─' * 72}\n")
    print("Você vai cair numa página de erro ou em branco — isso é esperado.")
    print(f"{AMAR}Copie a BARRA DE ENDEREÇO inteira dessa página.{FIM}")
    print(f"{CINZA}Ela tem que conter '?code=' no final. O endereço sozinho,")
    print(f"sem o code, não serve — é o code que o script precisa.{FIM}\n")

    bruto = input(f"Cole a URL com ?code= [{slug}] (Enter pula): ").strip()
    if not bruto:
        print(f"{CINZA}Pulando {slug}.{FIM}")
        return False

    if bruto.startswith("http") and state not in bruto:
        resp = input(f"{AMAR}O 'state' não bate com o que enviei. Continuar? (s/N) {FIM}").strip().lower()
        if resp != "s":
            return False

    try:
        code = extrair_code(bruto)
    except SystemExit as erro:
        print(erro)
        return False

    dados = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    if code_verifier:
        dados["code_verifier"] = code_verifier

    print(f"{CINZA}Trocando o code por tokens…{FIM}")
    r = requests.post(TOKEN_URL, data=dados, headers={"Accept": "application/json"}, timeout=30)
    if r.status_code != 200:
        print(f"{VERM}Falhou ({r.status_code}): {r.text[:400]}{FIM}")
        corpo = r.text.lower()

        if "invalid_client" in corpo:
            print(f"""
{AMAR}O que isso significa{FIM}
A autorização funcionou (o ML devolveu um code válido), mas o par
App ID + Secret não confere na hora de trocar por token.

{AMAR}O que conferir, nesta ordem{FIM}
 1. A Secret é DESTE app? Se você tem mais de uma aplicação no
    DevCenter, é fácil pegar o App ID de uma e a Secret de outra.
 2. A Secret foi colada inteira? O campo é invisível — dá para colar
    pela metade sem perceber. O script mostra o tamanho dela logo
    depois que você digita; compare com o do DevCenter.
 3. O Redirect URI aponta para um sistema seu em produção? Se sim, o
    seu backend pode ter consumido o code antes (ele vale um uso só).
    Use um app dedicado com https://localhost:8080/callback.""")

        elif "invalid_grant" in corpo:
            print(f"""
{AMAR}O que isso significa{FIM}
O code não vale mais. Ele expira em 10 minutos e só pode ser usado
uma vez.

{AMAR}Causas{FIM}
 - Demorou entre aceitar no navegador e colar aqui.
 - Você já tinha colado esse mesmo code antes.
 - O Redirect URI aponta para um sistema seu, e o backend dele trocou
   o code primeiro. Nesse caso, use um app dedicado apontando para
   https://localhost:8080/callback.""")

        elif "redirect" in corpo:
            print(f"""
{AMAR}O que isso significa{FIM}
O redirect_uri enviado na troca não é idêntico ao cadastrado no app.
Precisa bater caractere por caractere — inclusive http/https, www e
a barra final.

Você informou: {redirect_uri}""")

        else:
            print(f"{CINZA}Causas comuns: code expirado (vale 10 min e um uso só),")
            print(f"redirect_uri diferente do DevCenter, ou app com PKCE sem --pkce.{FIM}")
        return False

    return escrever_env(slug, client_id, client_secret, redirect_uri, r.json())


def ja_usado_por_outra_conta(user_id: str, slug: str) -> str | None:
    """
    Devolve o slug de OUTRA conta que já usa este user_id, se houver.

    Existe por causa de uma armadilha do fluxo em duas etapas: o link de
    consentimento NÃO escolhe a conta. Os três links são iguais salvo o
    'state' — quem decide qual conta autoriza é o login que estiver aberto no
    navegador na hora. Se a mesma pessoa abrir os três sem trocar de login,
    as três autorizações voltam da MESMA conta, cada uma com o state certo, e
    a conferência de state passa lisa nas três.

    O resultado seria o pior tipo de erro: três pastas com credencial válida
    apontando para uma conta só, o sistema coletando os mesmos anúncios três
    vezes e atribuindo a clientes diferentes. Aqui isso vira recusa.
    """
    for pasta in sorted(CONTAS.iterdir()):
        if not pasta.is_dir() or pasta.name == slug:
            continue
        env = pasta / ".env"
        if not env.exists():
            continue
        try:
            for linha in env.read_text(encoding="utf-8").splitlines():
                if linha.startswith("ML_USER_ID=") and linha.split("=", 1)[1].strip() == str(user_id):
                    return pasta.name
        except OSError:
            continue
    return None


def escrever_env(slug: str, client_id: str, client_secret: str,
                 redirect_uri: str, tok: dict) -> bool:
    """
    Grava o .env da conta a partir da resposta de token.

    Separada da autorização porque agora existem dois caminhos até aqui: o
    fluxo direto, quando a conta está nesta máquina, e o fluxo em duas etapas,
    quando ela está com o cliente. A parte que decide em qual PASTA a
    credencial cai é a mesma nos dois — e é justamente a que não pode divergir.
    """
    import time
    destino = CONTAS / slug / ".env"
    access, refresh = tok.get("access_token", ""), tok.get("refresh_token", "")
    user_id = str(tok.get("user_id", ""))
    expira = int(tok.get("expires_in", 21600))

    if not refresh:
        print(f"{VERM}Vieram tokens, mas SEM refresh_token.{FIM}")
        print("Marque 'offline_access' nos escopos do app e refaça — "
              "senão você reautoriza a cada 6 horas.")
        return False

    me = requests.get("https://api.mercadolibre.com/users/me",
                      headers={"Authorization": f"Bearer {access}"}, timeout=30)
    nickname = me.json().get("nickname", "?") if me.status_code == 200 else "?"

    print(f"\n{'─' * 72}")
    print(f"  Conta autorizada:  {VERDE}{nickname}{FIM}")
    print(f"  user_id:           {user_id}")
    print(f"  gravando em:       contas/{slug}/.env")
    print(f"{'─' * 72}")
    outra = ja_usado_por_outra_conta(user_id, slug)
    if outra:
        print(f"\n{VERM}RECUSADO: o user_id {user_id} já é o da conta '{outra}'.{FIM}")
        print(f"{AMAR}Duas pastas com o mesmo user_id significam a MESMA loja")
        print(f"contada como dois clientes.{FIM}")
        print(f"{CINZA}O link de consentimento não escolhe a conta — quem escolhe é o")
        print(f"login aberto no navegador. Provavelmente os dois links foram abertos")
        print(f"no mesmo login. Abra o link de '{slug}' em janela anônima, entre na")
        print(f"conta certa, e refaça.{FIM}")
        return False

    print(f"{CINZA}Confira o apelido: é a última chance de perceber que o{FIM}")
    print(f"{CINZA}consentimento saiu pela conta errada.{FIM}")

    if input(f"\n{AMAR}Esta é a conta certa? (s/N) {FIM}").strip().lower() != "s":
        print(f"{CINZA}Nada gravado.{FIM}")
        return False

    destino.write_text(
        "# Credencial desta conta — NÃO copiar para outra pasta.\n"
        f"ML_CLIENT_ID={client_id}\n"
        f"ML_CLIENT_SECRET={client_secret}\n"
        f"ML_REDIRECT_URI={redirect_uri}\n"
        f"ML_USER_ID={user_id}\n"
        f"ML_REFRESH_TOKEN={refresh}\n"
        f"ML_ACCESS_TOKEN={access}\n"
        f"ML_TOKEN_EXPIRA_EM={int(time.time()) + expira}\n",
        encoding="utf-8",
    )
    try:
        os.chmod(destino, 0o600)
    except OSError:
        pass

    print(f"{VERDE}Gravado: contas/{slug}/.env{FIM}")
    if gravar_user_id(slug, user_id):
        print(f"{VERDE}Registrado no config/clientes.yaml{FIM}")
    else:
        print(f"{AMAR}Não achei a conta '{slug}' no clientes.yaml — "
              f"coloque à mão:  user_id: \"{user_id}\"{FIM}")
    return True


def concluir_uma(slug: str, client_secret: str, bruto: str) -> bool:
    """
    Fecha a autorização de uma conta com o endereço que o cliente devolveu.

    A metade que exige a Secret roda AQUI, na sua máquina. A do cliente só
    abre um link e devolve o endereço da página de erro — ele não precisa do
    projeto, nem de Python, nem de ver credencial nenhuma.
    """
    pendentes = _ler_pendentes()
    pedido = pendentes.get(slug)
    if not pedido:
        print(f"{VERM}Não há pedido aberto para {slug}.{FIM}")
        print(f"{CINZA}Gere o link primeiro: python scripts/autorizar.py {slug} --link{FIM}")
        return False

    if bruto.startswith("http") and pedido["state"] not in bruto:
        print(f"{AMAR}O 'state' deste endereço não é o que eu enviei para {slug}.{FIM}")
        print(f"{CINZA}Quase sempre significa endereço trocado entre duas contas —")
        print(f"e gravar a credencial na pasta errada é o erro mais caro daqui.{FIM}")
        if input("Continuar mesmo assim? (s/N) ").strip().lower() != "s":
            return False

    try:
        code = extrair_code(bruto)
    except SystemExit as erro:
        print(erro)
        return False

    dados = {
        "grant_type": "authorization_code",
        "client_id": pedido["client_id"],
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": pedido["redirect_uri"],
    }
    if pedido.get("code_verifier"):
        dados["code_verifier"] = pedido["code_verifier"]

    print(f"{CINZA}Trocando o code por tokens…{FIM}")
    r = requests.post(TOKEN_URL, data=dados,
                      headers={"Accept": "application/json"}, timeout=30)
    if r.status_code != 200:
        print(f"{VERM}Falhou ({r.status_code}): {r.text[:300]}{FIM}")
        if "invalid_grant" in r.text.lower():
            print(f"{AMAR}O code vale 10 minutos e um uso só.{FIM}")
            print(f"{CINZA}Gere um link novo e peça para a pessoa abrir e devolver na hora.{FIM}")
        return False

    corpo = r.json()
    ok = escrever_env(slug, pedido["client_id"], client_secret,
                      pedido["redirect_uri"], corpo)
    if ok:
        pendentes.pop(slug, None)
        _gravar_pendentes(pendentes)
    return ok


def main() -> int:
    p = argparse.ArgumentParser(
        description="Autoriza uma ou mais contas do Mercado Livre.")
    p.add_argument("slugs", nargs="+", help="um ou mais slugs (as pastas precisam existir)")
    p.add_argument("--pkce", action="store_true",
                   help="use se o app tem PKCE ativado no DevCenter")
    p.add_argument("--link", action="store_true",
                   help="só gera o link de consentimento para enviar ao cliente")
    p.add_argument("--concluir", action="store_true",
                   help="recebe o endereço que o cliente devolveu e grava o .env")
    a = p.parse_args()

    faltando = [s for s in a.slugs if not (CONTAS / s).is_dir()]
    if faltando:
        print(f"{VERM}Estas pastas não existem: {', '.join(faltando)}{FIM}")
        print('Crie antes:  python scripts/nova_conta.py <slug> --cliente <id> --nome "Nome"')
        return 1

    # ---- gerar os links: não precisa da Secret, porque nada é trocado aqui.
    # É o modo para quando a conta está na máquina do cliente.
    if a.link:
        cid_p, _sec, red_p = app_de_outra_conta()
        client_id = perguntar("App ID (client_id)", cid_p)
        redirect_uri = perguntar("Redirect URI (igual ao do DevCenter)", red_p)
        if not (client_id and redirect_uri):
            print(f"{VERM}Preciso do App ID e do Redirect URI.{FIM}")
            return 1
        print(f"\n{'═' * 72}")
        print(f"{VERDE}Envie um link para cada dono de conta.{FIM}")
        print(f"{CINZA}Ele abre, faz login NA CONTA DELE, aceita, e cai numa página")
        print(f"de erro. O que você precisa de volta é a BARRA DE ENDEREÇO dessa")
        print(f"página inteira — ela contém o ?code=.{FIM}")
        print(f"{AMAR}O code vale 10 minutos e um uso só: combine de fazer na hora.{FIM}")
        for slug in a.slugs:
            print(f"\n{'─' * 72}\n{AMAR}{slug}{FIM}\n")
            print(montar_pedido(slug, client_id, redirect_uri, a.pkce))
        print(f"\n{'═' * 72}")
        print(f"Quando o endereço voltar:")
        print(f"  python scripts/autorizar.py <slug> --concluir")
        return 0

    # ---- concluir: aqui sim a Secret é necessária, e ela nunca sai daqui.
    if a.concluir:
        _cid, sec_p, _red = app_de_outra_conta()
        client_secret = perguntar("Secret Key", sec_p, secreto=True)
        if not client_secret:
            print(f"{VERM}Sem a Secret não dá para trocar o code por token.{FIM}")
            return 1
        feitas = []
        for slug in a.slugs:
            print(f"\n{'─' * 72}\n{AMAR}{slug}{FIM}")
            bruto = input("Cole o endereço que o cliente devolveu: ").strip()
            if not bruto:
                print(f"{CINZA}Pulando {slug}.{FIM}")
                continue
            if concluir_uma(slug, client_secret, bruto):
                feitas.append(slug)
        if feitas:
            print(f"\n{VERDE}Autorizadas:{FIM} {', '.join(feitas)}")
            for slug in feitas:
                print(f"  python cli.py checar {slug}")
        return 0 if feitas else 1

    # App ID e Secret são do APP, não da conta — pedidos uma vez só.
    cid_p, sec_p, red_p = app_de_outra_conta()
    if cid_p:
        print(f"{CINZA}Encontrei um app já configurado em outra conta — Enter aceita o mesmo.{FIM}")

    client_id = perguntar("App ID (client_id)", cid_p)
    client_secret = perguntar("Secret Key", sec_p, secreto=True)
    redirect_uri = perguntar("Redirect URI (exatamente como está no DevCenter)", red_p)
    if not redirect_uri:
        print(f"{CINZA}Sem padrão aqui de propósito: o ML não aceita localhost, então")
        print(f"o endereço tem que ser um HTTPS público seu. Cadastre no app e cole igual.{FIM}")

    if not (client_id and client_secret and redirect_uri):
        faltou = [nome for nome, v in (("App ID", client_id),
                                       ("Secret Key", client_secret),
                                       ("Redirect URI", redirect_uri)) if not v]
        print(f"{VERM}Faltou: {', '.join(faltou)}.{FIM}")
        print(f"{CINZA}Rode o autorizar.bat de novo e preencha esse campo.{FIM}")
        return 1

    print(f"\n{VERDE}App recebido{FIM} {CINZA}(id {client_id[:6]}…, "
          f"secret com {len(client_secret)} caracteres){FIM}")

    if len(a.slugs) > 1:
        print(f"\n{CINZA}{len(a.slugs)} contas em sequência. Cada uma precisa de uma")
        print(f"janela anônima própria — feche a anterior antes de abrir a seguinte,")
        print(f"senão você autoriza a mesma conta duas vezes.{FIM}")

    feitas, puladas = [], []
    for slug in a.slugs:
        try:
            (feitas if autorizar_uma(slug, client_id, client_secret,
                                     redirect_uri, a.pkce) else puladas).append(slug)
        except KeyboardInterrupt:
            print(f"\n{AMAR}Interrompido em {slug}.{FIM}")
            puladas.append(slug)
            break

    print(f"\n{'═' * 72}")
    if feitas:
        print(f"{VERDE}Autorizadas ({len(feitas)}):{FIM} {', '.join(feitas)}")
    if puladas:
        print(f"{AMAR}Pendentes ({len(puladas)}):{FIM} {', '.join(puladas)}")
    print(f"{'═' * 72}")

    if feitas:
        print(f"\nValide agora:")
        for slug in feitas:
            print(f"  python cli.py checar {slug}")
    return 0 if feitas else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ncancelado")
        sys.exit(130)
