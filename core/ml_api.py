"""
Cliente da API do Mercado Livre com trava de conta.

A trava: o cliente é instanciado POR CONTA (slug). Toda requisição usa o
token daquela conta e valida que o user_id do token bate com o user_id do
registro. Se não bater, levanta erro em vez de operar na conta errada.
"""
from __future__ import annotations

import time
from typing import Any, Iterator

import requests

from . import auth
from .utils import agora_iso

BASE = "https://api.mercadolibre.com"

# A central de promoções só responde no contrato v2; sem isso vem 400.
VERSAO_PROMO = "v2"


class ContaDivergente(RuntimeError):
    """O token carregado não pertence à conta que o comando pediu."""


# ----------------------------------------------------------------------
# os DOIS 403 do Mercado Livre — e por que confundi-los custa caro
# ----------------------------------------------------------------------
# Até 11/09/2026 este cliente tratava todo 403 como a mesma parede. A
# documentação oficial mostra que são duas paredes, com destinos opostos, e que
# só o CORPO da resposta separa uma da outra:
#
#   pt_br/permissoes-funcionais (21/11/2025) publica o corpo literal de
#   PERMISSÃO FUNCIONAL faltando no nosso próprio app:
#       {"code": "PA_UNAUTHORIZED_RESULT_FROM_POLICIES",
#        "blocked_by": "PolicyAgent",
#        "message": "At least one policy returned UNAUTHORIZED.",
#        "status": 403}
#
#   pt_br/erro-403 (02/04/2025) publica o corpo de POSSE — o recurso é de outro
#   vendedor:
#       {"status": 403, "error": "access_denied",
#        "message": "access to the requested resource is forbidden",
#        "code": "FORBIDDEN"}
#
# O primeiro TEM CONSERTO: marca-se a permissão no DevCenter, de graça, e
# conserta as oito contas de uma vez. O segundo NÃO TEM: nem escopo, nem
# certificação DPP — cuja lista de benefícios, lida inteira, não inclui acesso
# ampliado de API — destravam ler anúncio alheio.
#
# Isto já aconteceu aqui e ninguém soube ler: o arquivo de 403 largado na raiz
# do repo (…origem_5214042583.json) contém EXATAMENTE o corpo do PolicyAgent. A
# sessão que bateu nele anotou "403" e desistiu de uma porta que estava a uma
# caixa de seleção de abrir.
MOTIVO_PERMISSAO = "permissao_funcional"     # DevCenter resolve
MOTIVO_ESCOPO = "escopo_oauth"               # a concessão do vendedor resolve
MOTIVO_POSSE = "posse"                       # nada resolve
MOTIVO_PORTA_FECHADA = "politica_do_ml"      # nada resolve
MOTIVO_INDEFINIDO = "403_nao_classificado"   # corpo fora dos padrões conhecidos

_CONSERTO = {
    MOTIVO_PERMISSAO: (
        "PERMISSÃO FUNCIONAL faltando no NOSSO app (blocked_by=PolicyAgent). "
        "TEM CONSERTO e é de graça: DevCenter > a aplicação > Permissões "
        "funcionais > habilitar a área deste recurso com leitura (e escrita, se "
        "for escrita). Não desista deste endpoint sem antes olhar lá."),
    MOTIVO_ESCOPO: (
        "ESCOPO OAuth faltando na concessão desta conta (read / write / "
        "offline_access). TEM CONSERTO: refazer a autorização do vendedor com o "
        "escopo certo (scripts/autorizar.py)."),
    MOTIVO_POSSE: (
        "POSSE: o recurso pertence a outro vendedor. NÃO TEM CONSERTO — nenhuma "
        "permissão, escopo, plano ou certificação libera. Desista deste caminho "
        "e leia pela ficha de catálogo (/products/{id}/items) ou pelos endpoints "
        "de demanda, que respondem em anúncio de terceiro."),
    MOTIVO_PORTA_FECHADA: (
        "PORTA FECHADA pelo ML: política ou recurso em descontinuação, não "
        "permissão. NÃO TEM CONSERTO — é o caso do /sites/MLB/search, que a doc "
        "pt_br/itens-e-buscas lista como substituído (por seller_id use "
        "/users/{id}/items/search) e, para busca por palavra-chave, com "
        "\"Não haverá substituição\". Ver a tabela de bloqueios do CLAUDE.md "
        "antes de tentar consertar."),
    MOTIVO_INDEFINIDO: (
        "403 com corpo fora dos padrões documentados. NÃO CLASSIFICADO: "
        "leia o corpo antes de concluir que é bloqueio definitivo."),
}


def classificar_403(corpo) -> tuple[str, bool, str]:
    """Lê o CORPO de um 403 e diz se aquilo tem conserto.

    Devolve (motivo, tem_conserto, o_que_fazer). É pública de propósito: o
    `cli.py`, o `scripts/diagnosticar.py` e o `core/cupons.py` também topam com
    403 por caminhos próprios, e precisam dar a MESMA resposta que o cliente dá.
    """
    if isinstance(corpo, dict):
        marcas = " ".join(
            str(corpo.get(campo) or "")
            for campo in ("code", "blocked_by", "error", "message", "cause")
        ).lower()
    else:
        marcas = str(corpo or "").lower()

    # A ordem importa. A tabela de erros de /reviews/item/{id} devolve
    # `error: forbidden` JUNTO com "At least one policy returned UNAUTHORIZED",
    # e aquilo é permissão funcional, não posse. Quem testasse "forbidden"
    # primeiro classificaria como sem conserto justamente o caso que mais
    # interessa acertar.
    if ("policyagent" in marcas
            or "pa_unauthorized_result_from_policies" in marcas
            or "policy returned unauthorized" in marcas):
        return MOTIVO_PERMISSAO, True, _CONSERTO[MOTIVO_PERMISSAO]
    if ("invalid scopes" in marcas or "invalid_scope" in marcas
            or "unauthorized_scopes" in marcas):
        return MOTIVO_ESCOPO, True, _CONSERTO[MOTIVO_ESCOPO]
    codigo = str((corpo.get("code") if isinstance(corpo, dict) else "") or "").lower()
    if "access_denied" in marcas or codigo == "forbidden":
        # Os dois marcadores do corpo de POSSE documentado em pt_br/erro-403.
        return MOTIVO_POSSE, False, _CONSERTO[MOTIVO_POSSE]
    if "forbidden" in marcas:
        # `{"message":"forbidden","error":"forbidden","status":403,"cause":[]}`
        # — medido em 11/09/2026 no /sites/MLB/search desta conta. Não traz
        # `access_denied` nem `code: FORBIDDEN`, e não é posse: ninguém é "dono"
        # de uma busca. É a porta que o ML fechou para todo mundo. O destino é o
        # mesmo (não tem conserto), mas dizer "pertence a outro vendedor" ali
        # mandaria quem lê procurar um dono que não existe.
        return MOTIVO_PORTA_FECHADA, False, _CONSERTO[MOTIVO_PORTA_FECHADA]
    return MOTIVO_INDEFINIDO, False, _CONSERTO[MOTIVO_INDEFINIDO]


class AcessoNegado(requests.HTTPError):
    """Um 403 do ML já classificado em "tem conserto" x "não tem".

    HERDA DE requests.HTTPError DE PROPÓSITO — é a decisão de projeto desta
    mudança. Até aqui o 403 chegava a quem chama como o HTTPError cru do
    `raise_for_status()`, e o repositório inteiro foi escrito em cima disso:
    `core/cupons._erro_legivel` lê `erro.response.status_code`, os coletores
    usam `except Exception`, `link_do_produto` engole tudo. Uma exceção fora
    dessa árvore obrigaria a revisar todo chamador, e o que escapasse viraria
    traceback numa coleta noturna.

    Herdando, nada quebra: quem só capturava continua capturando, quem lia
    `.response` continua lendo — e quem quiser a classificação lê `.motivo`,
    `.tem_conserto` e `.corpo`. Como a mensagem já sai com o destino escrito
    ("vá ao DevCenter" x "desista"), até quem apenas imprime o erro aprende a
    diferença sem mudar uma linha.
    """

    def __init__(self, mensagem, *, response=None, diagnostico=None):
        super().__init__(mensagem, response=response)
        self.diagnostico = diagnostico or {}
        self.motivo = self.diagnostico.get("motivo", MOTIVO_INDEFINIDO)
        self.tem_conserto = bool(self.diagnostico.get("tem_conserto"))
        self.corpo = self.diagnostico.get("corpo")


def status_da_entrada_multiget(entrada: dict):
    """O status de UMA entrada do multiget, nos dois contratos do ML.

    `/items?ids=` chama o campo de `code`; `/items/bulk?ids=` chama de
    `status_code` (doc pt_br/itens-e-buscas, 31/08/2026). Medido nos dois em
    11/09/2026 na facilita-brasil-principal.

    Devolve None quando a entrada não traz NENHUM dos dois — e None aqui quer
    dizer "não sei", nunca "deu certo" nem "falhou". Quem chama é obrigado a
    tratar, porque é exatamente esse silêncio que a migração produz.
    """
    for campo in ("code", "status_code"):
        valor = entrada.get(campo)
        if isinstance(valor, bool):
            continue
        if isinstance(valor, int):
            return valor
        if isinstance(valor, str) and valor.strip().isdigit():
            return int(valor)
    return None


class MLClient:
    def __init__(self, slug: str, user_id_esperado: str | None = None, verificar: bool = True):
        self.slug = slug
        self.cred = auth.token_valido(slug)
        self.user_id = str(self.cred.user_id)
        self._links_de_produto: dict[str, str | None] = {}
        # Último 403 classificado, no mesmo estilo de `ultima_busca_truncou`:
        # quem chama olha depois, sem precisar capturar exceção.
        self.ultimo_403: dict | None = None
        # Qual das rotas de multiget respondeu por último nesta instância, e o
        # que a última chamada devolveu. Ver `detalhes_dos_itens`.
        self._rota_multiget: str | None = None
        self.ultimo_multiget: dict = {}

        if verificar and user_id_esperado and str(user_id_esperado) not in ("", "SUBSTITUIR"):
            if str(user_id_esperado) != self.user_id:
                raise ContaDivergente(
                    f"TRAVA DE SEGURANÇA: a conta '{slug}' está registrada com user_id "
                    f"{user_id_esperado}, mas o .env dessa pasta tem {self.user_id}. "
                    f"Nada foi executado. Corrija antes de continuar."
                )

        self.sessao = requests.Session()
        self.sessao.headers.update({"Accept": "application/json"})

    # ------------------------------------------------------------------
    # transporte
    # ------------------------------------------------------------------
    def _headers(self) -> dict:
        if time.time() >= self.cred.expira_em - auth.MARGEM_SEGURANCA_SEG:
            self.cred = auth.token_valido(self.slug)
        return {"Authorization": f"Bearer {self.cred.access_token}"}

    def _diagnosticar_403(self, corpo, onde: str) -> dict:
        """Classifica o 403, guarda em `ultimo_403` e devolve o diagnóstico."""
        motivo, tem_conserto, o_que_fazer = classificar_403(corpo)
        diagnostico = {
            "quando": agora_iso(),
            "conta": self.slug,
            "onde": onde,
            "motivo": motivo,
            "tem_conserto": tem_conserto,
            "o_que_fazer": o_que_fazer,
            "corpo": corpo,
        }
        self.ultimo_403 = diagnostico
        return diagnostico

    def get(self, caminho: str, **params) -> Any:
        # A central de promoções exige `app_version` em TODO recurso dela, e
        # sem isso devolve `{"message":"Invalid app_version"}` com 400. A regra
        # é do ENDPOINT, não de quem chama — por isso mora aqui, e não repetida
        # em cada método.
        #
        # Entrou em 12/09/2026 por um caso que só apareceu com a caixa de
        # notificações: o ML avisa `public_candidates` e `public_offers` com um
        # `resource` que aponta para /seller-promotions/..., e quem busca esse
        # caminho genericamente não tinha como saber do parâmetro. Eram 44
        # avisos perdidos — inclusive convite de campanha COM PRAZO, que é o
        # tipo de aviso que não adianta receber atrasado.
        if caminho.startswith("/seller-promotions/") and "app_version" not in params:
            params["app_version"] = VERSAO_PROMO

        url = caminho if caminho.startswith("http") else f"{BASE}{caminho}"
        for tentativa in range(5):
            try:
                r = self.sessao.get(url, headers=self._headers(),
                                    params=params or None, timeout=40)
            except (requests.Timeout, requests.ConnectionError) as erro:
                # A rede caindo no meio já era tratada para erro 5xx, mas não
                # para timeout: uma única leitura lenta derrubava o comando
                # inteiro com traceback. Numa varredura de 20 páginas de
                # pedidos, a chance de uma delas passar de 40s não é pequena —
                # e perder as 19 boas por causa dela é o pior desfecho.
                if tentativa == 4:
                    raise
                time.sleep(2 ** tentativa)
                continue

            if r.status_code == 429:                       # rate limit
                espera = int(r.headers.get("Retry-After", 2 ** tentativa))
                time.sleep(min(espera, 30))
                continue
            if r.status_code == 401:                       # token morreu no meio
                self.cred = auth.renovar(auth.carregar(self.slug))
                continue
            if r.status_code >= 500:
                time.sleep(2 ** tentativa)
                continue
            if r.status_code == 409:
                # Transitório, não estado do anúncio. Em 02/09/2026 o
                # /seller-promotions do #7575762246 devolveu 409 e derrubou a
                # revisão da FACILITA no item 131 de 177 — os 46 restantes
                # nunca foram olhados e o CSV não foi gravado. Segundos depois
                # o MESMO endpoint devolveu 200 com as duas campanhas ativas.
                # GET é idempotente: repetir não cadastra nada, ao contrário
                # do `escrever`, que continua não repetindo 4xx de propósito.
                time.sleep(2 ** tentativa)
                continue
            if r.status_code == 404:
                return None
            if r.status_code == 403:
                # O 403 já subia daqui como HTTPError, pelo raise_for_status
                # logo abaixo — só que sem o corpo, que é a única parte que diz
                # se aquilo tem conserto. A exceção continua sendo um
                # HTTPError (ver AcessoNegado), então quem captura hoje captura
                # igual; o que muda é que a mensagem agora termina em "vá ao
                # DevCenter" ou "desista", em vez de um "403 Client Error" seco.
                try:
                    corpo = r.json()
                except ValueError:
                    corpo = (r.text or "")[:500]
                d = self._diagnosticar_403(corpo, f"GET {url}")
                raise AcessoNegado(
                    f"[{self.slug}] 403 em GET {url} — {d['o_que_fazer']} "
                    f"Corpo do ML: {corpo}",
                    response=r, diagnostico=d)
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"[{self.slug}] GET {url} falhou após 5 tentativas.")

    # ------------------------------------------------------------------
    # anúncios próprios
    # ------------------------------------------------------------------
    def ids_dos_meus_anuncios(self, status: str | None = None) -> list[str]:
        """Varre todos os itens da conta usando search_type=scan (sem limite de 1000)."""
        ids: list[str] = []
        scroll = None
        while True:
            params = {"search_type": "scan", "limit": 100}
            if status:
                params["status"] = status
            if scroll:
                params["scroll_id"] = scroll
            dados = self.get(f"/users/{self.user_id}/items/search", **params) or {}
            lote = dados.get("results", [])
            ids.extend(lote)
            scroll = dados.get("scroll_id")
            if not lote or not scroll:
                break
        return ids

    CAMPOS_ITEM = (
        "id,title,price,original_price,available_quantity,sold_quantity,status,"
        "sub_status,permalink,listing_type_id,catalog_listing,catalog_product_id,"
        "category_id,health,shipping,seller_id,thumbnail,last_updated,deal_ids,tags,"
        # O SKU do vendedor. Sem ele, planilha de custo organizada por SKU —
        # que é como quase todo cliente organiza a dele — não casa com anúncio
        # nenhum, e o custo tem que ser reconciliado no olho.
        "seller_custom_field,attributes,variations"
    )


    # ------------------------------------------------------------------
    # multiget: o `/items?ids=` morre em 25/10/2026
    # ------------------------------------------------------------------
    # A doc pt_br/itens-e-buscas (31/08/2026): "Os endpoints de consultas
    # múltiplas /items?ids= e /users?ids= entram em processo de descontinuação.
    # (…) Migre suas integrações até 25/10/2026. Durante esse período, os
    # endpoints atuais e seus substitutos coexistirão."
    #
    # No substituto mudam três coisas: o campo `code` de cada entrada passa a
    # se chamar `status_code`, a entrada ganha `id` na raiz, e a seleção de
    # campos exige prefixo `body.`.
    #
    # A troca do `code` é a parte perigosa, e o CLAUDE.md já avisava por que:
    # "o multiget engana quem só olha o status HTTP" — o HTTP vem 200 e o 403
    # está DENTRO de cada entrada. Com a virada, o filtro antigo
    # (`entrada.get("code") == 200`) passa a ler None em toda entrada e
    # descarta TODOS os anúncios, sem um único erro no log. É o mesmo defeito
    # que já custou um ano de snapshots de promoção vazios aqui. E quem
    # "consertasse" tirando o filtro cairia no oposto: gravar corpo de 403
    # como se fosse anúncio bom.
    #
    # Por isso a rota não é escolhida por data — data depende de alguém
    # lembrar. É escolhida por quem RESPONDE, na ordem abaixo, e a escolha fica
    # guardada na instância (uma sonda por cliente, não por lote). Enquanto o
    # legado responder ele continua valendo, que é a regra da casa de não
    # remover o caminho atual antes do prazo; no dia em que parar, o cliente
    # vira sozinho. Rota que responde num contrato ILEGÍVEL (nenhuma entrada
    # com `code` nem `status_code`) também é descartada e passa a vez.
    PRAZO_MULTIGET = "2026-10-25"
    ROTAS_MULTIGET = ("/items", "/items/bulk")

    @classmethod
    def campos_do_multiget(cls, rota: str) -> str:
        """A seleção de campos que cada contrato entende.

        ARMADILHA MEDIDA em 11/09/2026 na facilita-brasil-principal, e é a
        razão desta função existir: pedir ao `/items/bulk` apenas os campos
        documentados (`attributes=body.id,body.price,…`) devolve a entrada com
        a chave `body` e MAIS NADA — sem `status_code`, sem `id`. A seleção de
        campos corta o próprio campo de status, e aí toda entrada fica
        ilegível. Só voltam quando são pedidos explicitamente:

            attributes=body.…            -> entrada = {'body': {...}}
            attributes=status_code,id,body.…  -> {'status_code': 200, 'id': …, 'body': {...}}

        O legado ignora `status_code` na lista e devolve `code` de qualquer
        jeito, então cada rota leva a sua.
        """
        campos = [c.strip() for c in cls.CAMPOS_ITEM.split(",") if c.strip()]
        if not rota.rstrip("/").endswith("/bulk"):
            return ",".join(campos)
        return "status_code,id," + ",".join("body." + c for c in campos)

    def _multiget_itens(self, lote: list[str]) -> list[dict]:
        """Um lote pelo primeiro contrato que responder de forma LEGÍVEL."""
        # A rota que já respondeu vem PRIMEIRO (é o que evita uma sonda por
        # lote), mas as outras continuam na fila atrás dela. Tratar o cache
        # como lista de uma posição só era um defeito: a rota legada que
        # morresse no meio de uma varredura derrubaria a varredura inteira, em
        # vez de virar para o substituto — exatamente o que esta função existe
        # para impedir, só que com o relógio contra.
        rotas = [r for r in self.ROTAS_MULTIGET if r != self._rota_multiget]
        if self._rota_multiget:
            rotas.insert(0, self._rota_multiget)
        ultimo_erro: Exception | None = None
        for rota in rotas:
            try:
                resposta = self.get(rota, ids=",".join(lote),
                                    attributes=self.campos_do_multiget(rota))
            except requests.HTTPError as erro:
                # 4xx aqui é o endpoint dizendo que não atende mais neste
                # formato. Guarda e tenta o próximo contrato.
                ultimo_erro = erro
                self._rota_multiget = None
                continue
            entradas = [e for e in (resposta or []) if isinstance(e, dict)]
            if not entradas:
                self._rota_multiget = None
                continue
            if all(status_da_entrada_multiget(e) is None for e in entradas):
                # Respondeu, mas num contrato que não sabemos ler. Seguir em
                # frente aqui seria descartar o lote inteiro em silêncio.
                self._rota_multiget = None
                continue
            self._rota_multiget = rota
            return entradas

        if ultimo_erro is not None:
            raise ultimo_erro
        raise RuntimeError(
            f"[{self.slug}] nenhum contrato de multiget respondeu de forma "
            f"legível para {len(lote)} ids (tentadas: {', '.join(self.ROTAS_MULTIGET)}). "
            f"O `/items?ids=` tinha descontinuação marcada para "
            f"{self.PRAZO_MULTIGET} e o `/items/bulk?ids=` usa `status_code` no "
            f"lugar de `code` — se o formato mudou de novo, é aqui que se "
            f"conserta. Nada foi gravado: lote vazio seria pior que erro.")

    def detalhes_dos_itens(self, ids: list[str]) -> list[dict]:
        """multiget de até 20 ids por chamada, nos dois contratos do ML.

        Entrada sem `code` NEM `status_code` não é descartada em silêncio: vira
        anomalia contada em `ultimo_multiget`, e se o lote inteiro for assim o
        `_multiget_itens` já terá trocado de rota antes de chegar aqui.
        """
        saida: list[dict] = []
        contagem = {"pedidos": len(ids), "devolvidos": 0, "negados": 0,
                    "outros": 0, "sem_status": 0, "rota": None}
        for i in range(0, len(ids), 20):
            lote = ids[i : i + 20]
            for entrada in self._multiget_itens(lote):
                status = status_da_entrada_multiget(entrada)
                corpo = entrada.get("body")
                if status is None:
                    contagem["sem_status"] += 1
                    continue
                if status == 200 and corpo:
                    saida.append(corpo)
                    contagem["devolvidos"] += 1
                elif status == 403:
                    # O 403 por entrada é o bloqueio que engana quem olha só o
                    # HTTP. Classificado igual ao 403 de resposta inteira: na
                    # prática é sempre posse (anúncio de terceiro), mas se um
                    # dia vier PolicyAgent aqui, fica registrado em `ultimo_403`
                    # em vez de virar mais um item que "sumiu".
                    contagem["negados"] += 1
                    self._diagnosticar_403(
                        corpo if isinstance(corpo, dict) else entrada,
                        f"multiget {self._rota_multiget} id={entrada.get('id')}")
                else:
                    contagem["outros"] += 1
        contagem["rota"] = self._rota_multiget
        self.ultimo_multiget = contagem
        return saida

    def visitas(self, item_id: str, dias: int = 7) -> int:
        dados = self.get(
            f"/items/{item_id}/visits/time_window", last=dias, unit="day"
        ) or {}
        return int(dados.get("total_visits", 0))

    def visitas_por_dia(self, item_id: str, dias: int = 30) -> dict:
        """Série diária de visitas. Funciona em anúncio de TERCEIRO.

        Medido com controle em 11/09/2026, 5 anúncios de terceiro em 3
        categorias: `/items/{id}` devolve 403 nos cinco, e este endpoint
        devolve 200 com a série completa nos cinco (2.913 a 85.868 visitas
        em 30 dias). Ficha e demanda são portas separadas na API do ML, e a
        segunda nunca tinha sido experimentada aqui.

        Não existe versão em lote: `/visits/items?ids=` recusa mais de um id
        com `maximum amount of items to query is 1`. Custo é uma chamada por
        anúncio, então quem chama precisa de orçamento.

        Devolve {"total": int, "dias": [{"data": "YYYY-MM-DD", "visitas": n}]}.
        Dias sem visita não vêm na resposta do ML — a série é esparsa.
        """
        dados = self.get(
            f"/items/{item_id}/visits/time_window", last=dias, unit="day"
        ) or {}
        serie = []
        for ponto in dados.get("results") or []:
            data = str(ponto.get("date") or "")[:10]
            if data:
                serie.append({"data": data, "visitas": int(ponto.get("total") or 0)})
        return {"total": int(dados.get("total_visits") or 0), "dias": serie}

    def custo_do_envio(self, shipment_id: str) -> dict | None:
        """O frete COBRADO num envio que aconteceu. Não é cotação.

        `GET /shipments/{id}/costs`. A documentação do ML indica este recurso
        para reconciliação e é explícita sobre qual campo vale:

            To find out what was charged to the seller, query senders[].cost

        `receiver.cost` é o que o comprador pagou. Medido em 11/09/2026: existe
        venda em que os DOIS pagam — comprador R$ 39,99 e vendedor R$ 106,85 no
        mesmo envio. Nenhuma cotação mostra isso.

        `promoted_amount` e `save` são informativos e a própria documentação
        avisa para não usá-los como base de cobrança.
        """
        dados = self.get(f"/shipments/{shipment_id}/costs")
        if not dados:
            return None
        remetentes = dados.get("senders") or []
        return {
            "custo_vendedor": (remetentes[0] or {}).get("cost") if remetentes else None,
            "custo_comprador": (dados.get("receiver") or {}).get("cost"),
            "promovido": (dados.get("receiver") or {}).get("promoted_amount"),
        }

    def vendas_recentes(self, dias: int = 7, desde=None, ate=None) -> list[dict]:
        """
        Pedidos dos últimos N dias, SEM filtro de status — quem decide o que
        conta é quem chama.

        A janela começa à MEIA-NOITE do primeiro dia, no fuso do Brasil, e não
        N×24 horas atrás. A diferença não é cosmética: em 26/08 a conta do Ênio
        tinha cinco vendas concentradas no dia 19, e a janela corrida cortava o
        dia 19 no meio — pegava duas e deixava três de fora. O número mudava
        conforme a hora em que era consultado, e nunca batia com o painel.

        Com o corte na meia-noite, "últimos 7 dias" quer dizer sempre os mesmos
        dias de calendário, e a conferência com o painel do Mercado Livre passa
        a ser possível.
        """
        from datetime import datetime, timedelta, timezone as _tz
        from .utils import TZ_BR

        if desde is None:
            inicio_br = (datetime.now(TZ_BR) - timedelta(days=dias)).replace(
                hour=0, minute=0, second=0, microsecond=0)
            desde = inicio_br.astimezone(_tz.utc)

        params = {"order.date_created.from":
                  desde.astimezone(_tz.utc).strftime("%Y-%m-%dT%H:%M:%S.000-00:00")}
        if ate is not None:
            params["order.date_created.to"] = (
                ate.astimezone(_tz.utc).strftime("%Y-%m-%dT%H:%M:%S.000-00:00"))

        pedidos, offset = [], 0
        truncou = False
        while True:
            dados = self.get(
                "/orders/search",
                seller=self.user_id,
                **params,
                offset=offset,
                limit=50,
                sort="date_desc",
            ) or {}
            lote = dados.get("results", [])
            pedidos.extend(lote)
            offset += 50
            if len(lote) < 50:
                break
            if offset >= 1000:
                # O /orders/search não pagina além do offset 1000. Numa conta
                # com muito pedido isso significa que "últimos 60 dias" devolve
                # em silêncio os 1000 mais recentes — que podem ser três dias.
                # Quem chama precisa SABER que foi cortado, senão divide por 60
                # e publica um número que não existe.
                truncou = True
                break
        self.ultima_busca_truncou = truncou
        return pedidos

    # ------------------------------------------------------------------
    # conta
    # ------------------------------------------------------------------
    def reputacao(self) -> dict:
        u = self.get(f"/users/{self.user_id}") or {}
        rep = u.get("seller_reputation", {}) or {}
        metricas = rep.get("metrics", {}) or {}
        return {
            "nickname": u.get("nickname"),
            "nivel": rep.get("level_id"),
            "power_seller": rep.get("power_seller_status"),
            "transacoes": (rep.get("transactions") or {}).get("total"),
            "reclamacoes_pct": ((metricas.get("claims") or {}).get("rate")),
            "cancelamentos_pct": ((metricas.get("cancellations") or {}).get("rate")),
            "atrasos_pct": ((metricas.get("delayed_handling_time") or {}).get("rate")),
        }

    # ------------------------------------------------------------------
    # mercado / concorrência
    # ------------------------------------------------------------------
    # NOTA: /sites/{site}/search (busca pública por termo e por vendedor) foi
    # bloqueado pelo Mercado Livre para aplicações em geral — devolve 403.
    # O que substitui, e continua liberado:
    #   - /highlights  : mais vendidos por categoria (descobre concorrente sozinho)
    #   - /products    : catálogo por termo e todos os vendedores de um produto
    #   - /items?ids=  : acompanhar anúncios específicos por ID
    # Rode scripts/diagnosticar.py para conferir o que o seu app libera hoje.

    def destaques_da_categoria(self, categoria: str, site_id: str = "MLB") -> list[dict]:
        """
        Mais vendidos de uma categoria, em ordem. Devolve entradas com
        'id', 'position' e 'type' (ITEM ou PRODUCT).
        """
        dados = self.get(f"/highlights/{site_id}/category/{categoria}") or {}
        return dados.get("content", []) or []

    def buscar_no_catalogo(self, termo: str, site_id: str = "MLB", limite: int = 10) -> list[dict]:
        """Produtos de catálogo que casam com o termo."""
        dados = self.get("/products/search", site_id=site_id, status="active",
                         q=termo, limit=limite) or {}
        return dados.get("results", []) or []

    def vendedores_do_produto(self, product_id: str, limite: int = 20) -> list[dict]:
        """Todos os anúncios ligados a um produto de catálogo: quem vende e por quanto."""
        dados = self.get(f"/products/{product_id}/items", limit=limite) or {}
        return dados.get("results", []) or []

    def tendencias(self, categoria: str | None = None, site_id: str = "MLB") -> list[dict]:
        caminho = f"/trends/{site_id}/{categoria}" if categoria else f"/trends/{site_id}"
        return self.get(caminho) or []

    def apelido_do_vendedor(self, seller_id: str) -> str | None:
        dados = self.get(f"/users/{seller_id}") or {}
        return dados.get("nickname")

    def perfil_do_vendedor(self, seller_id: str) -> dict:
        u = self.get(f"/users/{seller_id}") or {}
        rep = u.get("seller_reputation", {}) or {}
        return {
            "seller_id": str(seller_id),
            "nickname": u.get("nickname"),
            "nivel": rep.get("level_id"),
            "power_seller": rep.get("power_seller_status"),
            "transacoes": (rep.get("transactions") or {}).get("total"),
            "loja_oficial": bool(u.get("official_store_id")),
            "cidade": ((u.get("address") or {}).get("city")),
            "estado": ((u.get("address") or {}).get("state")),
        }

    def frete_do_item(self, item_id: str, cep: str) -> dict | None:
        """
        Custo e prazo de entrega de um anúncio para um CEP.
        Pode não estar liberado para todo app — o chamador trata None.
        """
        dados = self.get(f"/items/{item_id}/shipping_options",
                         zip_code=cep.replace("-", "")) or {}
        opcoes = dados.get("options") or []
        if not opcoes:
            return None
        barata = min(opcoes, key=lambda o: (o.get("cost") if o.get("cost") is not None else 9e9))
        return {
            "custo": barata.get("cost"),
            "custo_lista": barata.get("list_cost"),
            "prazo_dias": ((barata.get("estimated_delivery_time") or {}).get("shipping")),
            "nome": barata.get("name"),
        }

    def preco_de_vitrine(self, item_id: str) -> float | None:
        """
        O preço que o comprador VÊ, não o que está no cadastro.

        Descoberto em 27/08 abrindo a busca do Mercado Livre no navegador: os
        toldos do Ênio apareciam de 12% a 46% mais baratos do que o campo
        `price` da API dizia. Nenhuma promoção constava em `original_price`
        nem em `deal_ids` — a campanha vive fora do item, e a API do item não
        a reflete.

        Isso não era detalhe: toda comparação com concorrente usava o preço de
        tabela contra o preço real do outro. O alerta chegou a dizer que o
        SKYIFLEX estava 29,2% abaixo quando, na vitrine, os dois estavam
        praticamente empatados — R$ 1.380 contra R$ 1.369.

        /items/{id}/prices devolve as faixas ativas. Pegamos a menor delas,
        porque é a que o comprador enxerga. Sem resposta, devolve None e quem
        chama continua com o preço de cadastro.
        """
        dados = self.get(f"/items/{item_id}/prices") or {}
        candidatos = []
        for faixa in (dados.get("prices") or []):
            valor = faixa.get("amount")
            if not isinstance(valor, (int, float)):
                continue
            condicao = faixa.get("conditions") or {}
            # faixa com data de fim no passado não vale mais
            fim = condicao.get("end_time")
            if isinstance(fim, str) and fim < agora_iso():
                continue
            candidatos.append(float(valor))
        if not candidatos:
            valor = (dados.get("prices") or [{}])[0].get("amount") if dados.get("prices") else None
            return float(valor) if isinstance(valor, (int, float)) else None
        return min(candidatos)

    def preco_para_ganhar(self, item_id: str) -> dict | None:
        """Diz se você tem o buy box do catálogo e a que preço o concorrente está."""
        return self.get(f"/items/{item_id}/price_to_win")

    def produto_do_catalogo(self, product_id: str) -> dict | None:
        return self.get(f"/products/{product_id}")

    def link_do_produto(self, product_id: str) -> str | None:
        """
        O endereço REAL da ficha de catálogo, perguntado à API.

        Existe porque montar endereço na mão não funciona. A oferta que vem em
        /products/{id}/items não traz permalink, e o palpite óbvio —
        produto.mercadolivre.com.br/MLB4832220309 — dá "esta página não
        existe": o endereço de anúncio precisa de hífen e do apelido do
        produto. O bot chegou a mandar um link quebrado desses.

        Como não dá para ler anúncio de terceiro (403), o link honesto é o da
        FICHA: abre a página com todos os vendedores daquele produto, que é o
        que se quer ver de qualquer forma. Sem resposta da API, devolve None —
        e quem chama não põe link nenhum. Link quebrado é pior que link
        nenhum: derruba a confiança na mensagem inteira.
        """
        if product_id in self._links_de_produto:
            return self._links_de_produto[product_id]
        link = None
        try:
            dados = self.get(f"/products/{product_id}") or {}
            bruto = dados.get("permalink")
            if isinstance(bruto, str) and bruto.startswith("http"):
                link = bruto
        except Exception:
            link = None
        self._links_de_produto[product_id] = link
        return link

    # ------------------------------------------------------------------
    # o que o ML tira de cada venda
    # ------------------------------------------------------------------
    def tarifa_de_venda(self, preco: float, categoria: str,
                        tipo_anuncio: str) -> dict | None:
        """
        A tarifa exata daquele preço, naquela categoria, naquele tipo.

        `core/tarifas.py` chama este método desde que foi escrito e ele não
        existia — e lá a chamada NÃO está protegida por except, então
        `python cli.py tarifas <conta>` estourava AttributeError no primeiro
        anúncio. A comissão medida por anúncio, que é a base de toda a
        precificação, nunca saiu por este caminho: os 10,5%–16,5% conhecidos
        foram lidos no braço na Gestão de preços.
        """
        return self.get("/sites/MLB/listing_prices",
                        price=float(preco), category_id=categoria,
                        listing_type_id=tipo_anuncio)

    def custo_do_frete_gratis(self, item_id: str,
                              detalhar: bool = False,
                              com_peso: bool = False):
        """
        Quanto o frete grátis deste anúncio custa AO VENDEDOR.

        Sem este número não existe margem de promoção honesta em estofado: o
        frete não aparece no preço do comprador, sai inteiro do bolso, e na
        linha Mona ele varia de R$ 13 a R$ 191 no mesmo produto.

        O ML não expõe isso num endpoint só. `/shipping_options/free` responde
        em parte das contas e devolve 404 noutras — foi o que aconteceu na
        FACILITA em 02/09/2026. Por isso aqui existem três tentativas, nesta
        ordem, e `detalhar=True` devolve o que cada uma respondeu para dar
        para ver qual funciona nesta conta antes de confiar no número.

        NUNCA devolve 0 por falta de resposta: frete zero infla a margem e é
        exatamente o erro que faz cadastrar promoção no prejuízo. Sem resposta
        é None, e quem chama decide pular o anúncio.

        `com_peso=True` devolve `(custo, billable_weight)` — o peso sobre o qual
        o ML de fato cobrou. Vale a pena pedir porque ele denuncia uma coisa que
        não aparece em lugar nenhum do anúncio: quando o ML IGNORA a medida
        declarada e arbitra a sua. Medido em 12/09/2026, três anúncios que
        declaram 1.673 g são cobrados sobre 18.560 — e o atributo do anúncio
        continua mostrando 1.673. Ver `rules.avaliar_frete_arbitrado`.
        """
        tentativas: list[tuple[str, Any]] = []
        peso: float | None = None

        # A ordem é a medida na FACILITA em 02/09/2026: /users/... respondeu
        # R$ 70,95 no #4701515641, o mesmo número da tela, e /items/... deu
        # null. Primeiro o que funciona — a outra ordem custava um 404 por
        # anúncio numa varredura de mais de cem.
        r1 = self.get(f"/users/{self.user_id}/shipping_options/free",
                      item_id=item_id, verbose="true")
        tentativas.append(("/users/{user}/shipping_options/free", r1))
        cobertura = ((r1 or {}).get("coverage") or {}).get("all_country") or {}
        custo = cobertura.get("list_cost")
        if isinstance(cobertura.get("billable_weight"), (int, float)):
            peso = float(cobertura["billable_weight"])

        if not isinstance(custo, (int, float)):
            r2 = self.get(f"/items/{item_id}/shipping_options/free")
            tentativas.append(("/items/{id}/shipping_options/free", r2))
            custo = (((r2 or {}).get("coverage") or {}).get("all_country") or {}).get("list_cost")

        if not isinstance(custo, (int, float)):
            # Último recurso: a tabela por CEP. Pega o list_cost de um CEP de
            # São Paulo capital — não é a média nacional, é uma aproximação
            # por baixo, então quem usar isto precisa saber.
            r3 = self.frete_do_item(item_id, "01310100")
            tentativas.append(("/items/{id}/shipping_options?zip_code=01310100", r3))
            custo = (r3 or {}).get("custo_lista")

        valor = float(custo) if isinstance(custo, (int, float)) else None
        if detalhar:
            return (valor, tentativas)
        return (valor, peso) if com_peso else valor

    # ------------------------------------------------------------------
    # promoções — leitura e adesão
    # ------------------------------------------------------------------
    def promocoes_do_item(self, item_id: str) -> Any:
        """
        As campanhas que o ML oferece PARA ESTE anúncio, com o preço já feito.

        Existe porque `core/promocoes.py` chamava este método desde sempre e
        ele nunca foi escrito: a chamada morria em AttributeError dentro do
        `except Exception: continue` do coletor, então a coleta de promoções
        nunca quebrou — ela só nunca trouxe nada. Um ano de snapshots vazios
        sem um único erro no log.
        """
        return self.get(f"/seller-promotions/items/{item_id}",
                        app_version=VERSAO_PROMO)

    def escrever(self, metodo: str, caminho: str,
                 corpo: dict | None = None, **params) -> tuple[int, Any]:
        """
        POST/PUT/DELETE na API, devolvendo (status, corpo) em vez de estourar.

        Diferente do `get`: aqui NÃO existe repetição por erro 4xx. Repetir um
        POST que já foi aceito é cadastrar a mesma promoção duas vezes — o
        tipo de erro que só aparece na fatura. Só 429, 5xx e o 401 de token
        vencido são repetidos, e o 401 uma vez só.
        """
        url = caminho if caminho.startswith("http") else f"{BASE}{caminho}"
        renovou = False
        for tentativa in range(4):
            try:
                r = self.sessao.request(metodo, url, headers=self._headers(),
                                        params=params or None, json=corpo,
                                        timeout=40)
            except (requests.Timeout, requests.ConnectionError):
                # Timeout numa escrita é ambíguo: pode ter sido aceito do outro
                # lado. Devolve o ambíguo em vez de repetir às cegas.
                if tentativa == 3:
                    return 0, {"erro": "timeout — confira na tela se entrou"}
                time.sleep(2 ** tentativa)
                continue

            if r.status_code == 429:
                time.sleep(min(int(r.headers.get("Retry-After", 2 ** tentativa)), 30))
                continue
            if r.status_code == 401 and not renovou:
                self.cred = auth.renovar(auth.carregar(self.slug))
                renovou = True
                continue
            if r.status_code >= 500 and tentativa < 3:
                time.sleep(2 ** tentativa)
                continue

            try:
                corpo = r.json()
            except ValueError:
                corpo = (r.text or "")[:500]

            if r.status_code == 403:
                # `escrever` devolve (status, corpo) em vez de levantar, e todo
                # chamador desempacota essa dupla — mexer no contrato quebraria
                # as dez chamadas de core/publicacao.py. Então o diagnóstico
                # entra COMO CHAVE do corpo de erro, e como PRIMEIRA chave: o
                # `resumo["erro"] = str(corpo)[:300]` de publicacao.py corta em
                # 300 caracteres, e o que vem depois do corte não existe para
                # quem lê o terminal. Nenhuma chave do ML é removida.
                d = self._diagnosticar_403(corpo, f"{metodo} {url}")
                if isinstance(corpo, dict):
                    corpo = {"zion_diagnostico": d["o_que_fazer"], **corpo}
                else:
                    corpo = {"zion_diagnostico": d["o_que_fazer"],
                             "resposta": corpo}
            return r.status_code, corpo
        return 0, {"erro": "esgotou as tentativas"}

    def aderir_promocao(self, item_id: str, promocao_id: str, tipo: str,
                        preco: float, preco_meli_mais: float | None = None,
                        offer_id: str | None = None,
                        inicio: str | None = None, fim: str | None = None
                        ) -> tuple[int, Any]:
        """
        Coloca o anúncio na campanha pelo preço informado.

        O CORPO VARIA POR TIPO DE CAMPANHA. Isso saiu do teste de escrita de
        02/09/2026 na FACILITA: um corpo único acertava DEAL e SELLER_CAMPAIGN
        — os dois tipos que já vêm com `finish_date` pronto — e levava HTTP 400
        nos outros três. Os dois defeitos eram:

        - SMART e PRICE_MATCHING: {"message": "Offer id is required"}. O id que
          falta é o `ref_id` que a própria listagem de promoções do item já
          devolve (`OFFER-…` quando o anúncio já aderiu, `CANDIDATE-…` quando
          ainda é proposta). Sem ele o ML não sabe QUAL oferta daquela campanha
          está sendo aceita.
        - PRICE_DISCOUNT: {"message": "Start and finish dates must be in local
          format"}. Esse tipo é desconto do próprio vendedor: vem sem `id` e
          sem vigência, então quem manda as datas é quem chama. Também não
          leva `promotion_id`, que nele não existe.

        Datas em formato local (`2026-09-02T00:00:00`, sem fuso) — é como o
        SELLER_CAMPAIGN, a outra campanha definida pelo vendedor, devolve as
        dela nesta conta.
        """
        corpo: dict = {"promotion_type": tipo,
                       "deal_price": round(float(preco), 2)}
        # PRICE_DISCOUNT não tem promotion_id; mandar vazio é o que quebra.
        if tipo != "PRICE_DISCOUNT" and promocao_id:
            corpo["promotion_id"] = promocao_id
        if offer_id:
            corpo["offer_id"] = offer_id
        if inicio and fim:
            corpo["start_date"] = inicio
            corpo["finish_date"] = fim
        if preco_meli_mais is not None:
            corpo["top_deal_price"] = round(float(preco_meli_mais), 2)
        return self.escrever("POST", f"/seller-promotions/items/{item_id}",
                             corpo, app_version=VERSAO_PROMO)

    def alterar_promocao(self, item_id: str, promocao_id: str, tipo: str,
                         preco: float, preco_meli_mais: float | None = None,
                         offer_id: str | None = None) -> tuple[int, Any]:
        """
        Muda o preço de uma campanha em que o anúncio JÁ está — sem sair dela.

        Existe porque DELETE + POST não é equivalente a editar. Sair de um DEAL
        devolve a vaga ao ML sem garantia de recuperá-la, e depois de sair o ML
        ancora no preço praticado para recusar aumento (medido nesta casa em
        02/09/2026). Enquanto este método não existia, o único caminho de
        escrita era o DELETE — e ele era usado em qualquer tipo.

        QUEM DECIDE se o tipo aceita isto NÃO é este método: é
        `core.promocoes.como_alterar`, régua de versão única, a mesma que o
        resto do sistema lê. Este método é só o braço; mandar um
        PRICE_DISCOUNT por aqui é contornar a régua, não vencê-la.

        Contrato lido na doc em 12/09/2026 (developers, "Deals" → *Modificar
        ítems*): mesmo recurso e MESMOS campos do POST, trocando o verbo —

            curl -X PUT -d '{"deal_price":3900, "top_deal_price":3000,
                             "promotion_id":"P-MLB1806019",
                             "promotion_type":"DEAL"}'
              .../seller-promotions/items/MLB3295112047?app_version=v2
            → 200 {"price":3900,"top_price":3000,"original_price":5000}

        O exemplo publicado é de DEAL. MARKETPLACE_CAMPAIGN e VOLUME entram
        pelo mesmo recurso e estão na lista de `ALTERA_NO_LUGAR`, mas a doc não
        traz exemplo próprio de PUT para eles — se algum recusar, o erro vem do
        ML e não daqui.

        Escrito em 12/09/2026 e NUNCA chamado contra conta de cliente: mexer no
        preço de campanha alheia é decisão com dono na frente, não efeito
        colateral de uma implementação. `ERROR_CREDIBILITY_DISCOUNTED_PRICE` —
        o ML recusando um preço que julga não-crível — é a recusa esperada aqui,
        a mesma que já aparece no POST.
        """
        corpo: dict = {"promotion_type": tipo,
                       "deal_price": round(float(preco), 2)}
        # Sem o ramo `!= PRICE_DISCOUNT` que o POST tem: PRICE_DISCOUNT é o
        # tipo que NÃO altera no lugar (está em `promocoes.SAIR_E_READERIR`),
        # então ele não chega aqui — e escrever o ramo sugeriria que chega.
        if promocao_id:
            corpo["promotion_id"] = promocao_id
        # Mesma exigência de `aderir_promocao`/`sair_da_promocao`: os tipos que
        # trabalham por oferta precisam do `ref_id` da listagem, senão o ML
        # responde "Offer id is required" e nada muda.
        if offer_id:
            corpo["offer_id"] = offer_id
        if preco_meli_mais is not None:
            corpo["top_deal_price"] = round(float(preco_meli_mais), 2)
        return self.escrever("PUT", f"/seller-promotions/items/{item_id}",
                             corpo, app_version=VERSAO_PROMO)

    def sair_da_promocao(self, item_id: str, promocao_id: str, tipo: str,
                         offer_id: str | None = None) -> tuple[int, Any]:
        """
        Tira o anúncio de UMA campanha (não de todas).

        Vale o mesmo que em `aderir_promocao`: SMART e PRICE_MATCHING exigem
        `offer_id` — sem ele o ML responde "Offer id is required" e o anúncio
        CONTINUA na campanha. Descoberto em 02/09/2026 tentando sair de quatro
        promoções: as duas SMART falharam, DEAL e PRICE_DISCOUNT saíram.

        O `offer_id` é o `ref_id` da listagem de promoções do item — nas que
        já estão valendo ele vem como `OFFER-…`.
        """
        extras: dict = {"promotion_type": tipo}
        # PRICE_DISCOUNT não tem promotion_id; mandar vazio quebra.
        if tipo != "PRICE_DISCOUNT" and promocao_id:
            extras["promotion_id"] = promocao_id
        if offer_id:
            extras["offer_id"] = offer_id
        return self.escrever("DELETE", f"/seller-promotions/items/{item_id}",
                             None, app_version=VERSAO_PROMO, **extras)



def sku_do_item(item: dict) -> str | None:
    """
    O SKU que o vendedor deu ao anúncio.

    O Mercado Livre guarda em dois lugares e nem sempre nos dois: o campo
    livre `seller_custom_field` e o atributo SELLER_SKU. Procura nos dois,
    nessa ordem, porque o campo livre é o que aparece na tela do vendedor e é
    onde ele costuma digitar.
    """
    valor = (item.get("seller_custom_field") or "").strip()
    if valor:
        return valor[:60]
    # A ordem aqui é de PREFERÊNCIA, e por isso são laços separados e não um só
    # com a tupla ("SELLER_SKU", "GTIN"): num laço único quem decide é a ordem
    # em que o ML devolveu os atributos, não a nossa. Na FACILITA o GTIN vinha
    # antes, e o #4701515641 — que na tela mostra SKU POLTRONAEROS-CARAMELO —
    # respondia 7891922309806, o código de barras. Custo casado por SKU não
    # encontra nada com um EAN, e o anúncio caía em "sem custo" sem motivo.
    for atr in (item.get("attributes") or []):
        if atr.get("id") == "SELLER_SKU":
            v = (atr.get("value_name") or "").strip()
            if v:
                return v[:60]

    # ANÚNCIO COM VARIAÇÃO guarda o SKU em cada variação, não no anúncio. O
    # #4398500251 (Puff Sofá 1,40) e o #5696570996 (Kit 2 Poltronas) saíam como
    # "sem SKU" por isso, embora o vendedor tenha preenchido. Vale a primeira
    # variação: as variações de um anúncio são cores do MESMO produto e
    # compartilham custo. Se um dia um anúncio misturar produtos diferentes na
    # mesma variação, este atalho erra — e aí o certo é custo por variação.
    for var in (item.get("variations") or []):
        v = (var.get("seller_custom_field") or "").strip()
        if v:
            return v[:60]
        for atr in (var.get("attributes") or []):
            if atr.get("id") == "SELLER_SKU":
                v = (atr.get("value_name") or "").strip()
                if v:
                    return v[:60]

    # O GTIN fica por último de propósito: é código de barras, não SKU. Só
    # serve como identificador de desespero.
    for atr in (item.get("attributes") or []):
        if atr.get("id") == "GTIN":
            v = (atr.get("value_name") or "").strip()
            if v:
                return v[:60]
    return None
