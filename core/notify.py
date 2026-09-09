"""
Envio de alertas para fora — WhatsApp, Telegram ou console.

Três decisões de projeto que importam mais que o código:

1. O alerta é marcado como notificado no banco. Sem isso, uma coleta a cada
   3 horas reenviaria o mesmo alerta 5 vezes por dia e você silenciaria o
   número em uma semana.

2. Existe teto por mensagem. No dia em que algo der errado e gerar 200
   alertas, você recebe uma mensagem útil dizendo "e mais 192", não 200
   mensagens.

3. Existe janela de silêncio. Alerta de concorrente às 3 da manhã não é
   acionável — ele espera a próxima rodada dentro do horário.

4. `Resultado.ok` responde UMA pergunta: quem chamou pode marcar como
   notificado? Por isso ele exige que TODOS os destinos tenham sido atendidos,
   e trata timeout de leitura como atendido — a mensagem já saiu, só a resposta
   se perdeu. As duas metades foram acertadas em 02/09/2026, cada uma por um
   defeito observado: reenviar depois de timeout duplicava no grupo do cliente
   (69 vezes em um dia), e bastar um destino entregar para marcar o lote fazia
   o outro destino perder o alerta em silêncio.

   Quando sobra falha real, a rodada seguinte reenvia para TODOS — inclusive
   para quem já recebeu. É deliberado: repetir incomoda, perder custa dinheiro.
"""
from __future__ import annotations

import json
import os
import re
import time
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests
import yaml

from . import db, humano
from .utils import DIR_CONFIG, RAIZ, TZ_BR, brl, truncar

TEMPO_LIMITE = 30
# (conectar, ler). A leitura é longa de propósito: a api.telegram.org
# às vezes demora a confirmar um envio que já entregou, e cortar cedo
# transforma entrega em "falha" no log.
ESPERA_TELEGRAM = (10, 90)


# ----------------------------------------------------------------------
# configuração
# ----------------------------------------------------------------------
def _carregar_env_raiz() -> dict[str, str]:
    """Lê o .env da raiz (credenciais dos canais), sem tocar nos .env das contas."""
    caminho = RAIZ / ".env"
    valores: dict[str, str] = {}
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, _, v = linha.partition("=")
                valores[k.strip()] = v.strip().strip('"').strip("'")
    return valores


def _expandir(valor, env: dict[str, str]):
    """Troca ${VAR} pelo valor do .env da raiz ou do ambiente."""
    if not isinstance(valor, str):
        return valor
    def troca(m):
        nome = m.group(1)
        return env.get(nome) or os.environ.get(nome, "")
    return re.sub(r"\$\{([A-Z0-9_]+)\}", troca, valor)


def carregar_config() -> dict:
    caminho = DIR_CONFIG / "notificacoes.yaml"
    if not caminho.exists():
        return {"provedor": "console", "regras": {}}
    with caminho.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    env = _carregar_env_raiz()

    def percorrer(no):
        if isinstance(no, dict):
            return {k: percorrer(v) for k, v in no.items()}
        if isinstance(no, list):
            return [percorrer(v) for v in no]
        return _expandir(no, env)

    return percorrer(cfg)


# ----------------------------------------------------------------------
# provedores
# ----------------------------------------------------------------------
@dataclass
class Resultado:
    ok: bool
    detalhe: str


def _enviar_evolution(cfg: dict, destino: str, texto: str) -> Resultado:
    texto = _para_texto_simples(texto)
    p = cfg.get("evolution", {})
    base = (p.get("base_url") or "").rstrip("/")
    if not (base and p.get("instancia") and p.get("api_key")):
        return Resultado(False, "Evolution: base_url, instancia ou api_key em branco")
    r = requests.post(
        f"{base}/message/sendText/{p['instancia']}",
        headers={"apikey": p["api_key"], "Content-Type": "application/json"},
        json={"number": destino, "text": texto},
        timeout=TEMPO_LIMITE,
    )
    ok = r.status_code in (200, 201)
    return Resultado(ok, f"HTTP {r.status_code} {r.text[:200]}")


def _enviar_zapi(cfg: dict, destino: str, texto: str) -> Resultado:
    texto = _para_texto_simples(texto)
    p = cfg.get("zapi", {})
    if not (p.get("instancia") and p.get("token")):
        return Resultado(False, "Z-API: instancia ou token em branco")
    cabecalhos = {"Content-Type": "application/json"}
    if p.get("client_token"):
        cabecalhos["Client-Token"] = p["client_token"]
    r = requests.post(
        f"https://api.z-api.io/instances/{p['instancia']}/token/{p['token']}/send-text",
        headers=cabecalhos,
        json={"phone": destino, "message": texto},
        timeout=TEMPO_LIMITE,
    )
    return Resultado(r.status_code in (200, 201), f"HTTP {r.status_code} {r.text[:200]}")


def _enviar_meta(cfg: dict, destino: str, texto: str) -> Resultado:
    texto = _para_texto_simples(texto)
    p = cfg.get("meta", {})
    if not (p.get("phone_number_id") and p.get("access_token")):
        return Resultado(False, "Meta: phone_number_id ou access_token em branco")
    versao = p.get("versao", "v21.0")
    r = requests.post(
        f"https://graph.facebook.com/{versao}/{p['phone_number_id']}/messages",
        headers={"Authorization": f"Bearer {p['access_token']}",
                 "Content-Type": "application/json"},
        json={"messaging_product": "whatsapp", "to": destino,
              "type": "text", "text": {"preview_url": False, "body": texto}},
        timeout=TEMPO_LIMITE,
    )
    detalhe = f"HTTP {r.status_code} {r.text[:250]}"
    if r.status_code == 400 and "24" in r.text:
        detalhe += ("\nDica: a Cloud API só permite texto livre dentro da janela de 24h "
                    "após a última mensagem sua. Fora dela, exige template aprovado.")
    return Resultado(r.status_code in (200, 201), detalhe)


def _para_html_telegram(texto: str) -> str:
    """
    As mensagens usam *negrito* (sintaxe do WhatsApp). No Telegram isso apareceria
    como asterisco solto. Convertemos para HTML — escapando ANTES, senão um título
    de produto com '&' ou '<' quebra a mensagem inteira.
    """
    import html as _html
    escapado = _html.escape(texto, quote=False)
    negrito = re.sub(r"\*([^*\n]+)\*", r"<b>\1</b>", escapado)
    # [texto](url) vira link de verdade. Sem isso o operador tem que copiar
    # um permalink gigante do meio da mensagem para abrir o anúncio.
    return re.sub(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)",
                  r'<a href="\2">\1</a>', negrito)


def _para_texto_simples(texto: str) -> str:
    """
    WhatsApp e console não entendem [texto](url): viram o endereço cru, que
    ao menos é clicável. O *negrito* fica, porque o WhatsApp usa a mesma
    sintaxe.
    """
    return re.sub(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)", r"\1: \2", texto)


def destinos_telegram(p: dict) -> list[str]:
    """
    Todos os destinos configurados, aceitando as três formas que a gente
    escreveria naturalmente no YAML:

        chat_id: "123"
        chat_id: ["123", "456"]
        chat_ids: ["123", "456"]        (chat_id continua valendo junto)

    Duplicados saem — mandar duas vezes para a mesma pessoa é o tipo de erro
    que ninguém percebe até virar reclamação.
    """
    brutos: list = []
    for chave in ("chat_id", "chat_ids", "destinos"):
        valor = p.get(chave)
        if valor is None:
            continue
        brutos.extend(valor if isinstance(valor, (list, tuple)) else [valor])

    vistos, saida = set(), []
    for bruto in brutos:
        # aceita "123", "123 # Fulano" e {"chat_id": "123", "nome": "Fulano"}
        alvo = bruto.get("chat_id") if isinstance(bruto, dict) else bruto
        alvo = str(alvo or "").split("#")[0].strip()
        if alvo and alvo not in vistos:
            vistos.add(alvo)
            saida.append(alvo)
    return saida


def _enviar_telegram(cfg: dict, destino: str, texto: str) -> Resultado:
    """
    Manda para TODOS os destinos configurados.

    O resultado é o consolidado: se um contato falhar — bloqueou o bot, apagou
    a conversa — os outros ainda recebem, e a mensagem de retorno diz quem
    falhou. Interromper na primeira falha deixaria a equipe inteira sem alerta
    por causa de uma pessoa.
    """
    p = cfg.get("telegram", {})
    alvos = destinos_telegram(p)
    if not (p.get("bot_token") and alvos):
        return Resultado(False, "Telegram: bot_token ou chat_id em branco. "
                                "Rode: python scripts/telegram_setup.py")

    url = f"https://api.telegram.org/bot{p['bot_token']}/sendMessage"
    # 'incertos' são os que deram timeout de LEITURA: a mensagem quase certamente
    # chegou e só a resposta se perdeu. Ficam separados das falhas de verdade
    # porque as duas pedem coisas opostas de quem chama — o incerto NÃO deve ser
    # reenviado (duplica no grupo do cliente), a falha real DEVE.
    entregues, falhas, incertos = 0, [], []

    for alvo in alvos:
        corpo = {
            "chat_id": alvo,
            "text": _para_html_telegram(texto),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        # NUNCA repetir depois de um timeout de LEITURA.
        #
        # Custou uma mensagem duplicada para descobrir: quando a
        # api.telegram.org demora a responder, ela JÁ recebeu e JÁ entregou a
        # mensagem — o que falta é só a resposta HTTP voltar. Repetir nesse
        # caso manda o mesmo texto de novo no grupo do cliente. Enviar não é
        # idempotente: não existe chave que o Telegram use para descartar a
        # segunda cópia.
        #
        # Repetir só faz sentido quando a requisição NÃO chegou a sair —
        # falha de conexão ou timeout de CONEXÃO. Para a leitura, a resposta
        # certa é esperar mais, não tentar de novo.
        ultimo_erro = None
        incerto = None
        for tentativa in range(3):
            if tentativa:
                time.sleep(3 * tentativa)
            try:
                r = requests.post(url, json=corpo, timeout=ESPERA_TELEGRAM)
                if r.status_code != 200:
                    # se o HTML falhar por algum caractere inesperado, manda em
                    # texto puro em vez de perder o alerta
                    corpo.pop("parse_mode", None)
                    corpo["text"] = texto
                    r = requests.post(url, json=corpo, timeout=ESPERA_TELEGRAM)
                if r.status_code == 200:
                    entregues += 1
                    ultimo_erro = None
                else:
                    ultimo_erro = f"{alvo}: HTTP {r.status_code} {r.text[:90]}"
                break            # houve resposta do servidor: não repete
            except requests.ReadTimeout:
                # Provavelmente entregue: o Telegram já recebeu e já repassou,
                # o que se perdeu foi a resposta HTTP. Não repetir aqui, e — o
                # que faltava até 02/09/2026 — não deixar quem chama repetir na
                # rodada seguinte. Conta como destino ATENDIDO.
                incerto = (f"{alvo}: sem confirmação em "
                           f"{ESPERA_TELEGRAM[1]:.0f}s — a mensagem "
                           f"provavelmente FOI entregue; não reenvie sem "
                           f"olhar a conversa")
                break
            except (requests.ConnectTimeout, requests.ConnectionError) as erro:
                # a requisição não chegou a sair: repetir é seguro
                ultimo_erro = f"{alvo}: {str(erro)[:80]}"
            except requests.RequestException as erro:
                ultimo_erro = f"{alvo}: {str(erro)[:80]}"
                break
        if incerto:
            incertos.append(incerto)
        elif ultimo_erro:
            falhas.append(ultimo_erro)

    # 'ok' significa uma coisa só para quem chama: PODE marcar como notificado.
    # Por isso ele exige que TODO destino tenha sido atendido — entregue ou
    # incerto. Antes bastava um destino entregar para o lote inteiro virar
    # "notificado", e o destino que falhou nunca mais via aquele alerta: em
    # 02/09/2026 o resumo foi para o grupo e não para o privado do Neto.
    #
    # Quando sobra falha de verdade, a resposta é ok=False mesmo que outros
    # tenham recebido. A rodada seguinte reenvia para todos, então quem já
    # recebeu vê duas vezes — é o lado certo do erro: alerta crítico repetido
    # incomoda, alerta crítico perdido em silêncio custa dinheiro.
    atendidos = entregues + len(incertos)
    aviso = ("; ".join(incertos)) if incertos else ""

    if falhas:
        partes = [f"{atendidos} de {len(alvos)} atendido(s)",
                  "falhou em → " + " | ".join(falhas)]
        if aviso:
            partes.append("sem confirmação → " + aviso)
        return Resultado(False, "; ".join(partes))

    if incertos:
        return Resultado(True, f"{atendidos} destino(s) atendido(s), "
                               f"{len(incertos)} sem confirmação → {aviso}")
    return Resultado(True, f"enviado para {entregues} destino(s)")


def _enviar_console(cfg: dict, destino: str, texto: str) -> Resultado:
    texto = _para_texto_simples(texto)
    print("\n" + "═" * 60)
    print("NOTIFICAÇÃO — modo console. NADA FOI ENVIADO.")
    print("═" * 60)
    print(texto)
    print("═" * 60)

    # Um canal configurado com provedor em 'console' é quase sempre engano —
    # normalmente o config foi substituído por uma versão de exemplo.
    env = _carregar_env_raiz()
    prontos = []
    if env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"):
        prontos.append("telegram")
    if env.get("ZAPI_INSTANCIA") and env.get("ZAPI_TOKEN"):
        prontos.append("zapi")
    if env.get("EVOLUTION_API_KEY"):
        prontos.append("evolution")
    if env.get("META_ACCESS_TOKEN"):
        prontos.append("meta")

    if prontos:
        print(f"\n>>> Você TEM credencial de {', '.join(prontos)} no .env, mas")
        print(f">>> config/notificacoes.yaml está com 'provedor: console'.")
        print(f">>> Troque para 'provedor: {prontos[0]}' e as mensagens passam a sair.\n")
    else:
        print()
    return Resultado(True, "impresso no console (nada enviado)")


CINZA_TEXTO = ""      # canais de mensagem não têm cor; existe para o texto ficar legível no código


PROVEDORES = {
    "evolution": _enviar_evolution,
    "zapi": _enviar_zapi,
    "meta": _enviar_meta,
    "telegram": _enviar_telegram,
    "console": _enviar_console,
}


def enviar(texto: str, cfg: dict | None = None) -> Resultado:
    cfg = cfg or carregar_config()
    nome = (cfg.get("provedor") or "console").lower()
    funcao = PROVEDORES.get(nome)
    if not funcao:
        return Resultado(False, f"Provedor '{nome}' não existe. "
                                f"Use um de: {', '.join(PROVEDORES)}")
    destino = str(cfg.get("destino", "")).strip()
    if nome not in ("console", "telegram") and (not destino or "DDD" in destino):
        return Resultado(False, "Preencha 'destino' em config/notificacoes.yaml "
                                "(formato 55 + DDD + número, só dígitos).")
    try:
        return funcao(cfg, destino, texto)
    except requests.RequestException as erro:
        return Resultado(False, f"falha de rede: {erro}")


# ----------------------------------------------------------------------
# formatação
# ----------------------------------------------------------------------
def _padrao_do_titulo(titulo: str) -> str:
    """
    Regex que casa QUALQUER prefixo do título, cortado em qualquer palavra e
    com ou sem reticência no fim.

    É preciso ser assim porque cada regra corta o título num tamanho
    diferente — 40, 46, 55 caracteres — e comparar com um recorte fixo deixa
    sobra ("Médio… está pausado"). Casando por palavras, o corte da outra
    ponta não importa.
    """
    palavras = [re.escape(p) for p in (titulo or "").split()[:14]]
    if len(palavras) < 3:
        return ""
    corpo = palavras[0] + "".join(rf"(?:\s+{p}" for p in palavras[1:]) + ")?" * (len(palavras) - 1)
    return rf"{corpo}\s*(?:…|\.\.\.)?"


def _encurtar(texto: str, limite: int = 320) -> str:
    """
    Encurta SEM destruir as quebras de linha.

    O truncar() comum junta tudo numa linha só — é o certo para título de
    anúncio, e foi o errado aqui: o alerta agrupado ("fulano mexeu no preço
    de 21 produtos" seguido dos três maiores, um por linha) chegava como um
    parágrafo com bolinhas no meio, ilegível justo no alerta que mais
    precisa ser lido de relance.
    """
    texto = (texto or "").strip()
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    ultima = max(corte.rfind("\n"), corte.rfind(" "))
    if ultima > limite * 0.6:
        corte = corte[:ultima]
    return corte.rstrip(" ,-") + "…"


def _sem_o_titulo(mensagem: str, titulo: str) -> str:
    """
    Tira o título de dentro da frase quando ele já está no cabeçalho do grupo.

    Só mexe em duas posições seguras: quando a frase COMEÇA com o título e
    quando ela TERMINA com "de/em/: título". No meio, nunca — e só aplica se
    o que sobrar ainda for uma frase de verdade.

    A restrição veio de errar: a primeira versão cortou no meio e "Anúncio
    NOVO no ar: Rampa Pet Puff… a R$ 270,00" virou "Médio… a R$ 270,00".
    Repetição incomoda; frase mutilada faz desconfiar do sistema inteiro.
    """
    padrao = _padrao_do_titulo(titulo)
    if not padrao:
        return mensagem

    inicio = re.match(rf"^{padrao}[\s:,–—-]*", mensagem)
    if inicio and inicio.end() > 10:
        resto = mensagem[inicio.end():].strip()
        if len(resto) >= 8:
            return resto[:1].upper() + resto[1:]

    fim_ = re.search(rf"(?:\s+(?:de|em|do|da)\s+|:\s*){padrao}\s*[.!]?$", mensagem)
    if fim_:
        sobra = mensagem[:fim_.start()].strip(" ,;:-")
        if len(sobra) >= 8:
            return sobra + "."
    return mensagem


def _link(a: sqlite3.Row) -> str:
    """
    Devolve o link só se ele for utilizável.

    A rede de segurança do final não é teórica: o sistema chegou a montar
    "produto.mercadolivre.com.br/MLB4832220309" a partir do ID e mandar no
    Telegram. O endereço de anúncio do Mercado Livre exige hífen e apelido do
    produto, então aquilo abria "esta página não existe". A origem foi
    corrigida; isto aqui garante que um link daquele formato, gravado antes,
    não volte a aparecer. Link quebrado custa mais que link nenhum.
    """
    try:
        dados = json.loads(a["dados"] or "{}")
    except Exception:
        return ""
    url = str(dados.get("permalink") or dados.get("permalink_dele") or "")
    return _url_utilizavel(url)


def _url_utilizavel(url: str) -> str:
    """Passa a mesma rede de segurança em qualquer endereço, venha de onde vier."""
    url = str(url or "")
    if not url.startswith("http"):
        return ""
    if re.search(r"produto\.mercadolivre\.com\.br/ML[A-Z]?\d+$", url):
        return ""
    return url


def _links(a: sqlite3.Row) -> list[tuple[str, str]]:
    """
    Os endereços do alerta, já rotulados: o SEU anúncio e o DELE.

    Mandar um link só obriga a caçar o outro lado na mão — e num alerta de
    preço os dois lados são o assunto. Cada endereço passa pela mesma rede de
    segurança; o que não passar simplesmente não aparece.
    """
    try:
        dados = json.loads(a["dados"] or "{}")
    except Exception:
        return []
    saida = []
    meu = _url_utilizavel(dados.get("permalink"))
    # Alerta gravado antes de 27/08 guardava o link do CONCORRENTE na chave
    # 'permalink'. A marca é 'item_dele' sem 'permalink_dele': nesse caso o
    # endereço é dele, e chamá-lo de "seu anúncio" mandaria a pessoa para a
    # página errada com toda a confiança do mundo.
    if meu and dados.get("item_dele") and not dados.get("permalink_dele"):
        dados = {**dados, "permalink_dele": meu}
        meu = ""
    if meu:
        saida.append(("ver o seu anúncio", meu))
    dele = _url_utilizavel(dados.get("permalink_dele"))
    if dele and dele != meu:
        rotulo = ("ver a ficha do concorrente (todos os vendedores)"
                  if "/p/ML" in dele else "ver o anúncio do concorrente")
        saida.append((rotulo, dele))
    return saida


def _rotulo_do_link(url: str) -> str:
    """Ficha de catálogo e anúncio levam a páginas diferentes; o texto avisa."""
    return "ver a ficha (todos os vendedores)" if "/p/ML" in url else "ver anúncio"


def _agrupar_por_anuncio(alertas: list[sqlite3.Row]) -> list[dict]:
    """Um bloco por anúncio, na ordem em que os alertas chegaram."""
    grupos: dict = {}
    ordem: list = []
    for a in alertas:
        chave = (a["conta_slug"], a["titulo"] or a["item_id"] or "")
        if chave not in grupos:
            grupos[chave] = {"conta": a["conta_slug"], "titulo": a["titulo"],
                             "link": "", "links": [], "itens": []}
            ordem.append(chave)
        g = grupos[chave]
        g["itens"].append(a)
        if not g["link"]:
            g["link"] = _link(a)
        for rotulo, url in _links(a):
            if url not in [u for _, u in g["links"]]:
                g["links"].append((rotulo, url))
    return [grupos[k] for k in ordem]


def _e_mais_avisos(n: int) -> str:
    return f", além de {n} aviso menor" if n == 1 else f", além de {n} avisos menores"


def _quantas_coisas(n: int, criticas: bool) -> str:
    if criticas:
        return "1 coisa importante aconteceu" if n == 1 else f"{n} coisas importantes aconteceram"
    return "1 novidade" if n == 1 else f"{n} novidades"


def montar_mensagem_alertas(alertas: list[sqlite3.Row], teto: int) -> str:
    """
    Monta a mensagem como alguém contaria: quem, o que aconteceu, e o link.

    Antes era uma lista solta de frases, cada uma repetindo o título cortado
    do mesmo anúncio, com o apelido automático da conta no cabeçalho
    ("SV20260519065452"). Chegava no celular e não dava para saber de qual
    cliente era, nem que três das linhas falavam do mesmo produto.
    """
    vistas, unicos = set(), []
    for a in alertas:
        if a["mensagem"] in vistas:
            continue
        vistas.add(a["mensagem"])
        unicos.append(a)
    alertas = unicos
    if not alertas:
        return ""

    criticos = [a for a in alertas if a["critico"]]
    contas = {a["conta_slug"] for a in alertas}
    uma_conta = len(contas) == 1

    if uma_conta:
        cabecalho = f"*{humano.nome_da_conta(list(contas)[0])}*"
    else:
        cabecalho = f"*Zion ML* — {len(contas)} contas"
    cabecalho += "\n" + _quantas_coisas(len(alertas), bool(criticos))

    grupos = _agrupar_por_anuncio(alertas)

    # Dois anúncios cujo título só difere no fim ("…Porte Cinza" e "…Porte
    # Marrom Claro") viram o mesmo cabeçalho e a mensagem parece repetida.
    # Quando isso acontece, o corte passa a guardar as duas pontas.
    cabecalhos = [humano.titulo_curto(g["titulo"] or "", 52) for g in grupos]
    repetidos = {c for c in cabecalhos if cabecalhos.count(c) > 1 and c}
    for g, c in zip(grupos, cabecalhos):
        g["cabecalho"] = humano.titulo_distintivo(g["titulo"] or "", 52) if c in repetidos else c

    blocos, mostrados = [], 0
    for g in grupos:
        if mostrados >= teto:
            break
        titulo = g["cabecalho"]
        topo = f"*{titulo}*" if titulo else ""
        if not uma_conta:
            topo = f"{humano.nome_da_conta(g['conta'])} · {topo}" if topo \
                   else f"*{humano.nome_da_conta(g['conta'])}*"

        linhas = []
        for a in g["itens"]:
            if mostrados >= teto:
                break
            marca = "🔴" if a["critico"] else "🟡"
            texto = _sem_o_titulo(_encurtar(a["mensagem"], 320), g["titulo"] or "")
            linhas.append(f"{marca} {texto}")
            mostrados += 1

        if g["links"]:
            linhas.append(" · ".join(f"[{rotulo}]({url})" for rotulo, url in g["links"]))
        elif g["link"]:
            linhas.append(f"[{_rotulo_do_link(g['link'])}]({g['link']})")
        blocos.append("\n".join(x for x in ([topo] + linhas) if x))

    corpo = "\n\n".join(blocos)
    if len(alertas) > mostrados:
        corpo += f"\n\n… e mais {len(alertas) - mostrados}. O painel tem a lista inteira."
    return cabecalho + "\n\n" + corpo


def limites_do_dia(dia: str | None = None) -> tuple[str, str, str]:
    """
    (inicio, fim, rotulo) do dia — em UTC, que é como os carimbos são gravados.

    O dia é o do BRASIL, não o do relógio UTC. Sem essa conversão, um resumo
    às 6h30 da manhã cortaria o dia às 21h de ontem e perderia toda a noite —
    justamente quando o pessoal mexe nos anúncios.

    Sem argumento, devolve ONTEM: o resumo sai de manhã e fala do dia que
    terminou. Perguntar "quanto vendemos hoje" às 6h30 não tem resposta útil.
    """
    from datetime import timedelta
    agora = datetime.now(TZ_BR)
    alvo = (agora - timedelta(days=1)) if dia is None else datetime.strptime(dia, "%Y-%m-%d").replace(tzinfo=TZ_BR)
    inicio_br = alvo.replace(hour=0, minute=0, second=0, microsecond=0)
    fim_br = inicio_br + timedelta(days=1)
    from datetime import timezone
    return (inicio_br.astimezone(timezone.utc).isoformat(timespec="seconds"),
            fim_br.astimezone(timezone.utc).isoformat(timespec="seconds"),
            inicio_br.strftime("%d/%m"))


def _vendeu_no_dia(con: sqlite3.Connection, slug: str, inicio: str, fim: str) -> tuple[int, float]:
    """
    Quanto a conta vendeu no período, pela diferença do contador de vendidos
    entre a primeira e a última leitura dentro dele.

    Reserva de `vendas_hoje`, que só existe a partir da coleta que introduziu
    a coluna e é sempre do dia corrente.
    """
    linhas = con.execute(
        "WITH d AS (SELECT item_id, preco, vendidos, "
        "       ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY coletado_em) AS pri, "
        "       ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY coletado_em DESC) AS ult "
        "   FROM snap_anuncio WHERE conta_slug = ? AND coletado_em >= ? AND coletado_em < ?) "
        "SELECT a.preco, (b.vendidos - a.vendidos) AS quantas "
        "FROM d a JOIN d b ON a.item_id = b.item_id "
        "WHERE a.pri = 1 AND b.ult = 1 AND (b.vendidos - a.vendidos) > 0",
        (slug, inicio, fim)).fetchall()
    return (sum(l["quantas"] for l in linhas),
            sum((l["preco"] or 0) * l["quantas"] for l in linhas))


def _vendeu_hoje(con: sqlite3.Connection, slug: str, limite: int = 4) -> list[tuple]:
    """
    Quanto vendeu hoje, somando anúncio por anúncio.

    Serve de reserva: a contagem boa vem dos pedidos (coluna vendas_hoje),
    mas ela só existe a partir da primeira coleta depois desta versão. Até
    lá — e sempre que o app não tiver permissão de ler pedidos — este cálculo
    pela diferença do contador de vendidos cobre o buraco sem gastar chamada
    de API, já que os dois retratos do dia estão no banco.
    """
    hoje = datetime.now(TZ_BR).strftime("%Y-%m-%d")
    linhas = con.execute(
        "WITH d AS (SELECT item_id, titulo, preco, vendidos, coletado_em, "
        "       ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY coletado_em) AS pri, "
        "       ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY coletado_em DESC) AS ult "
        "   FROM snap_anuncio WHERE conta_slug = ? AND substr(coletado_em,1,10) >= ?) "
        "SELECT a.titulo, a.preco, (b.vendidos - a.vendidos) AS quantas "
        "FROM d a JOIN d b ON a.item_id = b.item_id "
        "WHERE a.pri = 1 AND b.ult = 1 AND (b.vendidos - a.vendidos) > 0 "
        "ORDER BY quantas DESC", (slug, hoje)).fetchall()
    return [(l["titulo"], l["quantas"], (l["preco"] or 0) * l["quantas"])
            for l in linhas[:limite]]


def _variacao(agora, antes, sufixo: str = "") -> str:
    """
    " (+3)" ou " (−1)" — o que mudou desde ontem.

    Número sozinho é retrato; número com variação é notícia. "13 pausados" não
    diz nada; "13 pausados (+3)" diz que alguém pausou três anúncios ontem.
    """
    if antes is None or agora is None or antes == agora:
        return ""
    d = agora - antes
    return f" ({'+' if d > 0 else '−'}{abs(d)}{sufixo})"


def _retrato_de_ontem(con: sqlite3.Connection, slug: str, agora_carimbo: str) -> dict:
    """A leitura mais recente com pelo menos 20h de diferença da atual."""
    from datetime import timedelta
    try:
        limite = (datetime.fromisoformat(agora_carimbo) - timedelta(hours=20)).isoformat()
    except Exception:
        return {}
    linha = con.execute(
        "SELECT * FROM snap_conta WHERE conta_slug = ? AND coletado_em <= ? "
        "ORDER BY coletado_em DESC LIMIT 1", (slug, limite)).fetchone()
    return dict(linha) if linha else {}


def _pede_atencao(con: sqlite3.Connection, slug: str, quantos: int = 2) -> list[str]:
    """
    As duas coisas que mais valem dinheiro hoje, tiradas do mesmo raio-x que
    o comando `diagnostico` usa.

    O resumo dizia o que MUDOU, e mudança é só metade do trabalho: um campeão
    de vendas pausado há três dias não muda em dia nenhum e continua sendo o
    problema mais caro da conta. Sem isto, o silêncio de um problema parado
    parece ausência de problema.
    """
    try:
        from . import diagnostico
        r = diagnostico.analisar(con, slug)
    except Exception:
        return []
    if not r or r.get("erro"):
        return []

    achados = []
    if r.get("campeao_parado") and r.get("campeao"):
        c = r["campeao"]
        achados.append(f"🔴 {humano.titulo_curto(c['titulo'], 38)} é o que mais vende "
                       f"({c['vendidos']} vendas) e está fora do ar")
    if r.get("secos"):
        n = len(r["secos"])
        achados.append(f"🔴 {n} anúncio{'s' if n != 1 else ''} no ar sem estoque — "
                       f"gasta{'m' if n != 1 else ''} exposição sem poder vender")
    if r.get("canibalizacao"):
        pior = r["canibalizacao"][0]
        achados.append(f"🟡 {len(r['canibalizacao'])} grupos com anúncios seus "
                       f"disputando entre si; no pior ({pior['grupo']}) são "
                       f"{pior['anuncios']}")
    if r.get("parados") and r.get("valor_parado"):
        achados.append(f"🟡 {brl(r['valor_parado'])} parados em {r['parados']} "
                       f"anúncios pausados que ainda têm estoque")
    if not achados:
        return []
    return ["", "*O que pede atenção*"] + achados[:quantos]


def montar_resumo_diario(con: sqlite3.Connection, dia: str | None = None) -> str:
    """
    Resumo do dia que TERMINOU, não do que está começando.

    Sai de manhã cedo, então falar do dia corrente seria falar de nada: às
    6h30 não houve venda nem mudança ainda. O recorte é o dia anterior
    inteiro, no fuso do Brasil.

    É também a prova de vida do sistema: chega todo dia mesmo sem novidade.
    Por isso começa pelo retrato da conta, e não pela lista de alertas — num
    dia calmo, o retrato É a notícia.
    """
    inicio, fim, rotulo = limites_do_dia(dia)
    # A data no topo importa mais que a marca: se a máquina ficar dormindo e o
    # resumo sair com atraso, é a data que denuncia — "Zion ML" não denuncia
    # nada.
    linhas = [f"*Resumo de {rotulo}*", ""]

    # A última leitura DENTRO do dia — não a de agora. O retrato tem que ser
    # de como a conta fechou aquele dia.
    contas = con.execute(
        "SELECT s.* FROM snap_conta s JOIN ("
        "  SELECT conta_slug, MAX(coletado_em) t FROM snap_conta "
        "  WHERE coletado_em >= ? AND coletado_em < ? GROUP BY conta_slug"
        ") u ON s.conta_slug = u.conta_slug AND s.coletado_em = u.t",
        (inicio, fim)).fetchall()
    if not contas:      # dia sem coleta nenhuma: cai para a leitura mais recente
        contas = con.execute(
            "SELECT s.* FROM snap_conta s JOIN ("
            "  SELECT conta_slug, MAX(coletado_em) t FROM snap_conta GROUP BY conta_slug"
            ") u ON s.conta_slug = u.conta_slug AND s.coletado_em = u.t").fetchall()

    for c in contas:
        ativos = c["anuncios_ativos"] or 0
        pausados = c["anuncios_pausados"] or 0
        vendas = c["vendas_7d"] or 0
        receita = c["receita_7d"] or 0
        nome = humano.nome_da_conta(c["conta_slug"])

        ontem = _retrato_de_ontem(con, c["conta_slug"], c["coletado_em"])   # o dia anterior a ESTE
        retrato = f"{ativos} anúncio{'s' if ativos != 1 else ''} no ar"
        retrato += _variacao(ativos, ontem.get("anuncios_ativos"))
        if pausados:
            retrato += (f", {pausados} pausado{'s' if pausados != 1 else ''}"
                        + _variacao(pausados, ontem.get("anuncios_pausados")))

        linhas.append(f"*{nome}*")
        linhas.append(retrato)
        # O dia primeiro, e em negrito: é a pergunta que a pessoa faz de
        # verdade ao abrir a mensagem. A janela de 7 dias vira o pano de
        # fundo, um degrau abaixo.
        # vendas_hoje da ÚLTIMA leitura do dia é o fechamento daquele dia.
        try:
            vendeu_n = c["vendas_hoje"]
            vendeu_r = c["receita_hoje"]
        except (KeyError, IndexError):
            vendeu_n = vendeu_r = None
        if not vendeu_n:
            vendeu_n, vendeu_r = _vendeu_no_dia(con, c["conta_slug"], inicio, fim)

        if vendeu_n:
            item = "item vendido" if vendeu_n == 1 else "itens vendidos"
            linhas.append(f"*{vendeu_n} {item}"
                          + (f" · {brl(vendeu_r)}" if vendeu_r else "") + "*")
        else:
            linhas.append("*Nenhuma venda no dia*")

        if vendas:
            item7 = "item" if vendas == 1 else "itens"
            # A janela vai escrita na mensagem. Sem ela, "7 dias" é ambíguo e
            # qualquer diferença para o painel do Mercado Livre vira mistério
            # — foi o que aconteceu em 26/08.
            try:
                janela = c["janela_vendas"]
            except (KeyError, IndexError):
                janela = None
            linha7 = f"{vendas} {item7} · {brl(receita)}"
            linha7 += f" · {janela}" if janela else " nos últimos 7 dias"
            linha7 += _variacao(vendas, ontem.get("vendas_7d"))
            linhas.append(linha7)

            # Cancelado não entra na receita, mas some da conta se não for
            # dito: o painel do ML soma cancelado em "vendas brutas".
            try:
                canc, canc_r = c["cancelados_7d"], c["receita_cancelada_7d"]
            except (KeyError, IndexError):
                canc = canc_r = None
            if canc:
                linhas.append(f"   {CINZA_TEXTO}+{canc} cancelado"
                              f"{'s' if canc != 1 else ''}"
                              + (f" ({brl(canc_r)})" if canc_r else "")
                              + " — o painel do ML soma isso em vendas brutas"
                              + f"{CINZA_TEXTO}")

        for aviso in _pede_atencao(con, c["conta_slug"]):
            linhas.append(aviso)
        linhas.append("")

    # Os repetidos saem ANTES da contagem. Antes não saíam, e o resumo dizia
    # "7 coisas importantes aconteceram" mostrando 4 linhas — quem lê conta as
    # linhas e conclui que o sistema escondeu três. Número que não bate com o
    # que está na tela destrói a confiança mais rápido que erro nenhum.
    vistos = set()
    alertas = []
    for a in con.execute(
            "SELECT * FROM alerta WHERE criado_em >= ? AND criado_em < ? "
            "ORDER BY critico DESC, criado_em DESC", (inicio, fim)):
        if a["mensagem"] in vistos:
            continue
        vistos.add(a["mensagem"])
        alertas.append(a)
    criticos = [a for a in alertas if a["critico"]]

    if not alertas:
        linhas.append("Nada mudou nesse dia — nenhum anúncio seu nem dos "
                      "concorrentes vigiados.")
        return "\n".join(linhas)

    escolhidos = criticos or alertas
    if criticos:
        linhas.append(f"*No dia* — {_quantas_coisas(len(criticos), True)}"
                      + (_e_mais_avisos(len(alertas) - len(criticos))
                         if len(alertas) > len(criticos) else "") + ":")
    else:
        linhas.append(f"*No dia* — {_quantas_coisas(len(alertas), False)}, "
                      f"nada crítico:")
    linhas.append("")

    corpo = montar_mensagem_alertas(escolhidos, teto=8)
    # o cabeçalho de conta já foi escrito acima
    linhas.append(corpo.split("\n\n", 1)[-1] if "\n\n" in corpo else corpo)
    return "\n".join(linhas)


# ----------------------------------------------------------------------
# orquestração
# ----------------------------------------------------------------------
def _dentro_da_janela(regras: dict, agora: datetime | None = None) -> bool:
    janela = regras.get("janela_ativa") or {}
    inicio, fim = int(janela.get("inicio", 0)), int(janela.get("fim", 24))
    hora = (agora or datetime.now(TZ_BR)).hour
    return inicio <= hora < fim


def notificar_pendentes(con: sqlite3.Connection, forcar: bool = False,
                        agora: datetime | None = None) -> Resultado:
    """Envia os alertas ainda não notificados e os marca no banco."""
    cfg = carregar_config()
    regras = cfg.get("regras") or {}

    if not forcar and not _dentro_da_janela(regras, agora):
        return Resultado(True, "fora da janela ativa — nada enviado")

    so_criticos = regras.get("nao_criticos_so_no_resumo", True)
    sql = "SELECT * FROM alerta WHERE notificado = 0"
    if so_criticos and not forcar:
        sql += " AND critico = 1"
    sql += " ORDER BY critico DESC, criado_em DESC"

    pendentes = con.execute(sql).fetchall()
    if not pendentes:
        return Resultado(True, "nenhum alerta pendente")

    teto = int(regras.get("max_alertas_por_mensagem", 8))
    resultado = enviar(montar_mensagem_alertas(pendentes, teto), cfg)

    if resultado.ok:
        con.executemany("UPDATE alerta SET notificado = 1 WHERE id = ?",
                        [(a["id"],) for a in pendentes])
        con.commit()
        return Resultado(True, f"{len(pendentes)} alerta(s) enviado(s)")
    return resultado


def enviar_resumo(con: sqlite3.Connection, dia: str | None = None) -> Resultado:
    cfg = carregar_config()
    resultado = enviar(montar_resumo_diario(con, dia), cfg)
    if resultado.ok:
        # Marca como notificado só o que o resumo REALMENTE cobriu. A versão
        # anterior usava datetime('now') do SQLite contra carimbo ISO com
        # fuso: a comparação de texto passava qualquer alerta do mesmo dia, e
        # alerta ainda não enviado era silenciado por engano.
        inicio, fim, _ = limites_do_dia(dia)
        con.execute("UPDATE alerta SET notificado = 1 WHERE notificado = 0 "
                    "AND criado_em >= ? AND criado_em < ?", (inicio, fim))
        con.commit()
    return resultado


def _ler_horario(texto, padrao="08:00") -> tuple[int, int]:
    """Aceita '07:30', '7:30', '7' ou 7. Devolve (hora, minuto)."""
    if texto is None:
        texto = padrao
    if isinstance(texto, (int, float)):
        return int(texto), 0
    partes = str(texto).strip().split(":")
    try:
        hora = int(partes[0])
        minuto = int(partes[1]) if len(partes) > 1 else 0
    except ValueError:
        return _ler_horario(padrao)
    return max(0, min(23, hora)), max(0, min(59, minuto))


def horario_do_resumo(cfg: dict | None = None) -> tuple[int, int]:
    cfg = cfg or carregar_config()
    regras = cfg.get("regras") or {}
    return _ler_horario(regras.get("horario_do_resumo",
                                   regras.get("hora_do_resumo")), "08:00")


def horario_do_mapa(cfg: dict | None = None) -> tuple[int, int]:
    cfg = cfg or carregar_config()
    regras = cfg.get("regras") or {}
    return _ler_horario(regras.get("horario_do_mapa",
                                   regras.get("hora_do_mapa")), "04:30")


def na_hora_de(con, chave: str, horario: tuple[int, int],
               agora=None, dia_da_semana: int | None = None) -> bool:
    """
    Verdadeiro na PRIMEIRA rodada do dia igual ou depois do horário — e só uma
    vez por dia. Isso torna o disparo imune ao horário exato da rodada: se a
    rodada das 7h30 não aconteceu porque a máquina estava desligada, a das
    10h30 manda. Melhor tarde do que nunca, e nunca duas vezes.
    """
    from datetime import datetime
    agora = agora or datetime.now(TZ_BR)

    if dia_da_semana is not None and agora.weekday() != dia_da_semana:
        return False

    hora, minuto = horario
    if (agora.hour, agora.minute) < (hora, minuto):
        return False

    hoje = agora.strftime("%Y-%m-%d")
    if db.ler_marcador(con, chave) == hoje:
        return False

    db.gravar_marcador(con, chave, hoje)
    return True
