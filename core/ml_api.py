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


class MLClient:
    def __init__(self, slug: str, user_id_esperado: str | None = None, verificar: bool = True):
        self.slug = slug
        self.cred = auth.token_valido(slug)
        self.user_id = str(self.cred.user_id)
        self._links_de_produto: dict[str, str | None] = {}

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

    def get(self, caminho: str, **params) -> Any:
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


    def detalhes_dos_itens(self, ids: list[str]) -> list[dict]:
        """multiget de até 20 ids por chamada."""
        saida: list[dict] = []
        for i in range(0, len(ids), 20):
            lote = ids[i : i + 20]
            resposta = self.get("/items", ids=",".join(lote), attributes=self.CAMPOS_ITEM) or []
            for entrada in resposta:
                if entrada.get("code") == 200 and entrada.get("body"):
                    saida.append(entrada["body"])
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
                              detalhar: bool = False):
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
        """
        tentativas: list[tuple[str, Any]] = []

        # A ordem é a medida na FACILITA em 02/09/2026: /users/... respondeu
        # R$ 70,95 no #4701515641, o mesmo número da tela, e /items/... deu
        # null. Primeiro o que funciona — a outra ordem custava um 404 por
        # anúncio numa varredura de mais de cem.
        r1 = self.get(f"/users/{self.user_id}/shipping_options/free",
                      item_id=item_id, verbose="true")
        tentativas.append(("/users/{user}/shipping_options/free", r1))
        custo = (((r1 or {}).get("coverage") or {}).get("all_country") or {}).get("list_cost")

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
        return (valor, tentativas) if detalhar else valor

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
                return r.status_code, r.json()
            except ValueError:
                return r.status_code, (r.text or "")[:500]
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
