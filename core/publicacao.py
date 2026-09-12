"""
Recadastro de anúncio: monta o payload a partir de um anúncio que já existe.

Existe por um motivo específico e medido: na conta facilita-decoralli o
formulário do ML não oferece Mercado Envios na criação — só "combinar com o
comprador" e "por sua conta". Pela API a forma de entrega é DECLARADA, não
escolhida numa lista que o site resolve mostrar. Se o ML aceitar `me2` aqui,
os anúncios órfãos saem; se recusar, a resposta traz o código do erro, que é
justamente o que a tela não conta.

Também está provado que editar não resolve: em 53 coletas e 844 anúncios com
histórico, NENHUM passou de not_specified para Mercado Envios. Recadastrar é
o único caminho.

Este módulo NÃO publica sozinho. `montar` lê e devolve o payload; `publicar`
só escreve quando recebe simular=False, e quem chama é responsável por ter
confirmado a conta antes.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from .ml_api import MLClient

# Nunca copiados de um anúncio para outro. Medido em 02/09/2026: na
# facilita-brasil-principal, 8 de 40 anúncios declaram peso de embalagem menor
# que o peso do produto (sofá de 23 kg como caixa de 2 kg), e 22 de 54 SKUs se
# contradizem entre anúncios. Foi por declaração de medida divergente que o ML
# tirou daquela conta o direito de alterar dimensão. Medida entra aqui só se
# vier de fora, conferida, nunca herdada.
ATRIBUTOS_PROIBIDOS = {
    "PACKAGE_LENGTH", "PACKAGE_WIDTH", "PACKAGE_HEIGHT", "PACKAGE_WEIGHT",
    "SELLER_PACKAGE_LENGTH", "SELLER_PACKAGE_WIDTH",
    "SELLER_PACKAGE_HEIGHT", "SELLER_PACKAGE_WEIGHT",
}

# Campos que o ML preenche sozinho e recusa se vierem no corpo.
# PACKAGE_DATA_SOURCE e SYI_PYMES_ID entraram em 02/09/2026: o primeiro declara
# QUEM informou a medida de embalagem, e copiá-lo como "SELLER" num anúncio que
# (por regra desta casa) não manda medida nenhuma é declarar uma origem que não
# existe. O segundo é o identificador que o fluxo de criação do ML gera para si
# mesmo — carregá-lo de um anúncio para outro é colar a identidade do irmão.
#
# PRODUCT_FEATURES entrou em 11/09/2026, e entrou como seguro, não como
# correção: num GET completo de 12 anúncios da Facilita ele aparece em 0 —
# nesta conta não há o que filtrar hoje. Está aqui porque uma implementação
# independente (gabrielPedron/criacao-anuncio) o encontrou sendo recusado com
# `ignored because it is not modifiable` noutra categoria, e herdar de um
# anúncio de origem que o tenha custaria uma recusa silenciosa.
ATRIBUTOS_DO_SISTEMA = {"ITEM_CONDITION", "PACKAGE_DATA_SOURCE", "SYI_PYMES_ID",
                        "PRODUCT_FEATURES"}

# Códigos de erro do ML que já foram vistos com controle, e o que cada um quer
# dizer em português. Existe porque a resposta crua do ML sai como um dicionário
# aninhado dentro de `cause`, e quem publica pelo terminal lê "status 400" e
# não lê o motivo — que às vezes é a informação mais cara da rodada.
DIAGNOSTICO_DE_ERRO = {
    "shipping.free_shipping.cost_exceeded":
        "o frete grátis OBRIGATÓRIO desta categoria custa mais que a venda. "
        "O ML está avisando que o anúncio nasce no prejuízo — confira o preço "
        "antes de insistir",
    "item.attributes.not_modifiable":
        "atributo travado. Em anúncio fechado (`closed`) o ML recusa edição de "
        "atributo, e não é bug do sistema",
    "item.user_product.repeated.conflict":
        "já existe um User Product idêntico nesta família. A família agrupa "
        "produtos DIFERENTES (cores), não cópias — para o mesmo produto em "
        "vários anúncios, use --sincronizar",
    "item.with_family_name.not_allowed_variations":
        "item com family_name não aceita variações. É classificação da CONTA "
        "como 'user product seller', não da categoria — não adianta trocar",
    "lost_me2_by_dimensions":
        "o ML derrubou o Mercado Envios pela dimensão. Em família NOVA ele "
        "julga a caixa do zero; família herdada pula esse julgamento",
}

# Peso do produto também não se herda, e por medida, não por princípio: em
# 02/09/2026 os anúncios do Sofá Yara declaravam 10 kg e 20 kg para o mesmo
# produto que o cliente pesou em 25 kg. Herdar isso é propagar erro de medida,
# que é a infração que já custou caro na conta irmã. Entra só por --peso.
# Não declarar peso é melhor que declarar peso errado.
ATRIBUTOS_NAO_HERDADOS = {"WEIGHT"}

MODOS_DE_ENVIO = ("me2", "not_specified", "custom")


def _familia(nome: str | None) -> str | None:
    """Normaliza o nome da família: o ML recusa acima de 60 caracteres.

    `item.family_name.length_invalid` — medido em 02/09/2026 em anúncios
    antigos cuja família tem 132 caracteres, herdada de um título
    quilométrico. Cortamos na palavra: o nome encurta, não vira outro.
    """
    if not nome:
        return None
    limpo = " ".join(str(nome).split())
    if len(limpo) <= 60:
        return limpo
    return limpo[:60].rsplit(" ", 1)[0].rstrip(" ,-")


def _atributos(item: dict, extras: dict[str, str] | None = None,
               herdar_peso: bool = False) -> list[dict]:
    """Copia os atributos do anúncio de origem, menos os de medida.

    `extras` sobrescreve ou acrescenta — é por onde entra uma medida real,
    conferida com o cliente, sem que ela venha herdada de outro anúncio.
    """
    bloqueados = set(ATRIBUTOS_PROIBIDOS) | set(ATRIBUTOS_DO_SISTEMA)
    if not herdar_peso:
        bloqueados |= ATRIBUTOS_NAO_HERDADOS

    saida = []
    vistos = set()
    for a in item.get("attributes") or []:
        aid = a.get("id")
        if not aid or aid in bloqueados:
            continue
        valor = a.get("value_name")
        if valor in (None, ""):
            continue
        vistos.add(aid)
        saida.append({"id": aid, "value_name": str(valor)})

    for aid, valor in (extras or {}).items():
        if valor in (None, ""):
            continue
        saida = [a for a in saida if a["id"] != aid]
        valor = str(valor)
        if valor.startswith("id:"):
            saida.append({"id": aid, "value_id": valor[3:]})
        else:
            saida.append({"id": aid, "value_name": valor})
        vistos.add(aid)
    return saida


def subir_foto(cli: MLClient, caminho: str) -> str:
    """Sobe um arquivo local para o banco de imagens do ML e devolve o id.

    Existe porque `montar` só sabe copiar as fotos do anúncio de origem, e o
    que está no ML nem sempre é o melhor que se tem: no Sofá Yara 140 as fotos
    publicadas estavam em 500x500 e os arquivos do fornecedor em 1254x1254 — o
    ML só liga o zoom a partir de 1200px. Foto boa entra por aqui, do disco.

    O ML devolve `{"id": ...}`; no corpo do item a foto entra como
    `{"id": <esse id>}`, não como URL.
    """
    caminho = str(caminho)
    with open(caminho, "rb") as arquivo:
        resposta = cli.sessao.post(
            "https://api.mercadolibre.com/pictures/items/upload",
            headers=cli._headers(),
            files={"file": (os.path.basename(caminho), arquivo)},
            timeout=180,
        )
    if resposta.status_code not in (200, 201):
        raise RuntimeError(
            f"upload de {os.path.basename(caminho)} falhou: "
            f"HTTP {resposta.status_code} — {resposta.text[:300]}"
        )
    foto_id = resposta.json().get("id")
    if not foto_id:
        raise RuntimeError(f"upload sem id na resposta: {resposta.text[:300]}")
    return foto_id


def montar(cli: MLClient, item_id: str, *,
           envio: str = "me2",
           frete_gratis: bool = True,
           estoque: int = 1,
           preco: float | None = None,
           titulo: str | None = None,
           tipo_anuncio: str | None = None,
           atributos_extras: dict[str, str] | None = None,
           herdar_peso: bool = False,
           caixa: str | None = None,
           peso_caixa: str | None = None,
           origem_bruta: dict | None = None,
           desvincular_familia: bool = False,
           familia: str | None = None) -> tuple[dict, dict]:
    """
    Lê o anúncio de origem e devolve (payload, origem).

    Estoque nasce em 1 de propósito: se um recadastro escapar publicado com
    preço errado, o estrago é uma unidade. Subir estoque é decisão separada.

    `desvincular_familia=True` tenta criar um produto sem `family_name`
    nenhum. Medido em 09/09/2026: nas categorias de móveis desta conta o ML
    recusa com `body.required_fields [family_name]` mesmo assim — a conta
    inteira exige família em item novo, não é regra por categoria. Ou seja,
    isto só funciona onde o ML não exigir o campo; não confie nele sem testar
    com `--publicar` em UM item antes de repetir para outros.

    `familia`, se vier preenchido, é o caminho que sobrevive a essa exigência:
    declara uma família PRÓPRIA (até 60 caracteres, cortada na palavra) em
    vez de herdar a da origem. Não elimina a obrigatoriedade — societário nela
    em vez de lutar contra ela — mas tira o anúncio novo do agrupamento
    genérico herdado, criando um `user_product_id` novo e independente com o
    texto que você escolher. Tem precedência sobre `desvincular_familia`.
    O ML deriva o título visível a partir da família (mais atributos como
    cor), então confira o título real do anúncio depois de publicar — não
    é garantido que saia exatamente como a string enviada.

    `origem_bruta`, se vier preenchido, substitui a leitura por `cli.get`.
    Existe para o caso de origem e destino serem CONTAS DIFERENTES: o ML
    bloqueia `GET /items/{id}` de item de terceiro com 403 `access_denied`
    (ver tabela de bloqueios no CLAUDE.md) — então quando `cli` é o cliente
    da conta de DESTINO, ele não consegue ler um item que pertence à conta de
    ORIGEM. Quem chama precisa ter lido o item ANTES, com o `MLClient` da
    própria conta de origem (leitura legítima, dono lendo o próprio item), e
    passar o JSON já pronto aqui. `cli` continua sendo só quem PUBLICA.
    """
    if envio not in MODOS_DE_ENVIO:
        raise ValueError(f"Modo de envio inválido: {envio}. Use um de {MODOS_DE_ENVIO}.")

    origem = origem_bruta if origem_bruta is not None else cli.get(f"/items/{item_id}")

    if origem.get("variations"):
        raise ValueError(
            f"{item_id} tem {len(origem['variations'])} variação(ões). "
            "Este comando só monta anúncio de variação única — a de variações "
            "precisa de tratamento próprio para não misturar cor e estoque."
        )

    fotos = [{"source": p.get("secure_url") or p.get("url")}
             for p in (origem.get("pictures") or []) if p.get("secure_url") or p.get("url")]

    # free_shipping vale nos DOIS modos. Em `not_specified` ele é a opção
    # "combinar com o comprador + oferecer frete grátis" que a tela mostra —
    # o selo aparece na busca e o vendedor arca com a entrega combinada.
    # É o padrão que a conta já usou em 27/08/2026 nos anúncios criados.
    envio_bloco: dict[str, Any] = {
        "mode": envio,
        "local_pick_up": False,
        "free_shipping": bool(frete_gratis),
    }

    # Medida da EMBALAGEM. É o único jeito de ela entrar: informada de fora,
    # conferida, nunca herdada de outro anúncio. Sem ela o ML aceita o me2 no
    # POST e retira depois, carimbando `lost_me2_by_dimensions` — foi o que
    # aconteceu no MLB5178925399 em 02/09/2026.
    #
    # NUNCA declarar medida menor que a real: o ML remede no centro de
    # distribuição, cobra a diferença e bloqueia a conta para alterações
    # futuras. A conta irmã FACILITA já está nesse estado.
    extras_medida: dict[str, str] = {}
    if caixa:
        partes = [p.strip() for p in str(caixa).lower().replace("×", "x").split("x")]
        if len(partes) != 3 or not all(partes):
            raise ValueError(
                f"Medida de caixa inválida: {caixa!r}. Use COMPRIMENTOxLARGURAxALTURA "
                f"em cm, ex.: '140x86x90'."
            )
        c, l, a = partes
        # SELLER_PACKAGE_*, não PACKAGE_*. Medido em 02/09/2026: mandando
        # PACKAGE_LENGTH/WIDTH/HEIGHT o ML aceita o POST e descarta em
        # silêncio — o MLB7579694392 nasceu com `PACKAGE: {}`. Os anúncios
        # desta conta que TÊM Mercado Envios usam SELLER_PACKAGE_*.
        extras_medida["SELLER_PACKAGE_LENGTH"] = f"{c} cm"
        extras_medida["SELLER_PACKAGE_WIDTH"] = f"{l} cm"
        extras_medida["SELLER_PACKAGE_HEIGHT"] = f"{a} cm"
    if peso_caixa:
        # O ML guarda esse campo em GRAMAS ("20000 g" nos anúncios que
        # funcionam). Aceitar "28 kg" e converter evita o erro de digitar
        # 28 e o ML entender 28 gramas — que seria subdeclaração grosseira.
        p = str(peso_caixa).strip().lower().replace(",", ".")
        numero = "".join(ch for ch in p if ch.isdigit() or ch == ".")
        if not numero:
            raise ValueError(f"Peso de caixa inválido: {peso_caixa!r}. Use '28 kg' ou '28000 g'.")
        gramas = float(numero) * (1000 if "kg" in p else 1)
        extras_medida["SELLER_PACKAGE_WEIGHT"] = f"{int(gramas)} g"

    payload = {
        "title": titulo or origem.get("title"),
        "category_id": origem.get("category_id"),
        # Obrigatório nestas categorias, e o ML só avisa recusando com 400
        # `body.required_fields [family_name]`. É o nome da FAMÍLIA de produto
        # no modelo User Products: as variações de cor do mesmo sofá dividem
        # uma. Herdamos a do anúncio de origem porque é literalmente o mesmo
        # produto — inventar uma nova quebraria o agrupamento no painel.
        # `familia` manda: família própria, produto novo e independente.
        # Sem ela, `desvincular_familia` tenta sair do agrupamento (só
        # funciona onde o ML não exigir o campo). Sem nenhum dos dois,
        # herda da origem — mesmo produto, mesmo agrupamento no painel.
        "family_name": familia if familia else (None if desvincular_familia else origem.get("family_name")),
        "price": preco if preco is not None else origem.get("price"),
        "currency_id": origem.get("currency_id") or "BRL",
        "available_quantity": int(estoque),
        "buying_mode": origem.get("buying_mode") or "buy_it_now",
        "listing_type_id": tipo_anuncio or origem.get("listing_type_id"),
        "condition": origem.get("condition") or "new",
        "pictures": fotos,
        "attributes": _atributos(origem, {**(atributos_extras or {}), **extras_medida},
                                 herdar_peso),
        "shipping": envio_bloco,
    }

    # No modelo User Products o título é DERIVADO da família — o ML recusa com
    # "The fields [title] are invalid" se ele vier junto de family_name. Quem
    # manda a família abre mão de escrever o título à mão.
    if payload.get("family_name"):
        # O ML recusa com `item.family_name.length_invalid` acima de 60
        # caracteres, e alguns anúncios antigos têm família de 132 — herdada
        # de um título quilométrico. Cortamos na palavra, sem inventar texto:
        # o nome da família some do meio, não vira outra coisa.
        payload["family_name"] = _familia(payload["family_name"])
        payload.pop("title", None)
    else:
        payload.pop("family_name", None)

    if origem.get("sale_terms"):
        payload["sale_terms"] = [
            {"id": t["id"], "value_name": t.get("value_name")}
            for t in origem["sale_terms"] if t.get("id") and t.get("value_name")
        ]
    return payload, origem


def montar_sincronizado(cli: MLClient, item_id: str, *,
                        envio: str = "me2",
                        frete_gratis: bool = True,
                        estoque: int = 1,
                        preco: float | None = None,
                        tipo_anuncio: str | None = None) -> tuple[dict, dict]:
    """Monta um anúncio pendurado no MESMO User Product do anúncio de origem.

    Descoberto em 02/09/2026, quando o ML recusou um recadastro com
    `body.required_fields [family_name]`: nesta categoria a conta opera no
    modelo **User Products**. Quem guarda título, fotos e ficha técnica é o
    produto (`MLBU...`), não o anúncio. O anúncio guarda só preço, modalidade,
    estoque e frete.

    É isso que significa "anúncios sincronizados": o Clássico MLB7191880994 e o
    Premium MLB7574196068 do Sofá Yara Marrom são dois anúncios apontando para
    o MESMO `user_product_id` MLBU4332489633. Não é um recurso de cópia — é o
    mesmo produto visto de duas modalidades.

    Consequência prática, e ela importa: **não adianta mandar foto ou atributo
    aqui**. Eles não pertencem a este anúncio. Mudar foto de um par sincronizado
    é `PUT /user-products/{id}`, e muda os DOIS ao mesmo tempo — decisão
    separada, com o dono na frente.

    Diferente de `montar`, que cria um produto novo e independente.
    """
    if envio not in MODOS_DE_ENVIO:
        raise ValueError(f"Modo de envio inválido: {envio}. Use um de {MODOS_DE_ENVIO}.")

    origem = cli.get(f"/items/{item_id}")
    produto = origem.get("user_product_id")
    if not produto:
        raise ValueError(
            f"{item_id} não tem user_product_id — não está no modelo User "
            f"Products, então não há produto para compartilhar. Publique com "
            f"o modo normal (sem --sincronizar)."
        )

    envio_bloco: dict[str, Any] = {"mode": envio, "local_pick_up": False}
    if envio == "me2":
        envio_bloco["free_shipping"] = bool(frete_gratis)

    # A validação do ML lista TUDO que falta, não alternativas: com só
    # user_product_id ela pede [family_name]; acrescentando a categoria ela
    # passou a pedir [family_name, category_id]. Os dois são obrigatórios.
    # `family_name` sozinho abriria produto novo; junto de `user_product_id`
    # ele é só o rótulo da família a que este anúncio pertence.
    payload = {
        "user_product_id": produto,
        "family_name": origem.get("family_name"),
        "category_id": origem.get("category_id"),
        "price": preco if preco is not None else origem.get("price"),
        "currency_id": origem.get("currency_id") or "BRL",
        "available_quantity": int(estoque),
        "buying_mode": origem.get("buying_mode") or "buy_it_now",
        "listing_type_id": tipo_anuncio or origem.get("listing_type_id"),
        "condition": origem.get("condition") or "new",
        "shipping": envio_bloco,
    }
    if origem.get("sale_terms"):
        payload["sale_terms"] = [
            {"id": t["id"], "value_name": t.get("value_name")}
            for t in origem["sale_terms"] if t.get("id") and t.get("value_name")
        ]
    return payload, origem


def resumo_do_sincronizado(payload: dict, origem: dict) -> str:
    envio = payload.get("shipping") or {}
    linhas = [
        f"origem      : {origem.get('id')} ({origem.get('status')}, "
        f"{origem.get('listing_type_id')})",
        f"PRODUTO     : {payload.get('user_product_id')} — "
        f"{origem.get('family_name')}",
        f"modalidade  : {payload.get('listing_type_id')}",
        f"preco       : {payload.get('price')} {payload.get('currency_id')}",
        f"estoque     : {payload.get('available_quantity')}",
        f"ENVIO       : mode={envio.get('mode')} "
        f"free_shipping={envio.get('free_shipping')}",
        "fotos/ficha : herdadas do produto — este anúncio não as carrega",
    ]
    return chr(10).join(linhas)


def encerrar(cli: MLClient, item_id: str, *, simular: bool = True) -> dict:
    """
    Encerra um anúncio. Encerrar é definitivo — anúncio fechado não reativa.

    O ML nem sempre aceita ir de `active` direto para `closed`; quando recusa,
    o caminho é pausar antes. Fazemos os dois passos e reportamos o que
    aconteceu em cada um, porque "falhou" sem dizer onde não ajuda ninguém.
    """
    antes = cli.get(f"/items/{item_id}")
    resumo = {
        "item_id": item_id,
        "titulo": antes.get("title"),
        "status_antes": antes.get("status"),
        "vendidos": antes.get("sold_quantity"),
        "preco": antes.get("price"),
    }
    if simular:
        resumo["simulado"] = True
        return resumo

    # Um anúncio que já vendeu não é lixo de teste — pare e deixe a decisão
    # com quem opera a conta.
    if (antes.get("sold_quantity") or 0) > 0:
        resumo["resultado"] = "recusado por segurança: já tem venda"
        return resumo

    status, corpo = cli.escrever("PUT", f"/items/{item_id}", {"status": "closed"})
    if status not in (200, 201):
        resumo["tentativa_direta"] = f"{status}"
        s_pausa, _ = cli.escrever("PUT", f"/items/{item_id}", {"status": "paused"})
        resumo["pausou"] = s_pausa
        status, corpo = cli.escrever("PUT", f"/items/{item_id}", {"status": "closed"})

    resumo["status_http"] = status
    if status in (200, 201):
        resumo["resultado"] = "encerrado"
        resumo["status_depois"] = (corpo or {}).get("status")
    else:
        resumo["resultado"] = "falhou"
        resumo["erro"] = str(corpo)[:300]
    return resumo


def reativar(cli: MLClient, item_id: str, *, simular: bool = True) -> dict:
    """
    Despausa um anúncio. Ao contrário de encerrar, isto tem volta: é só pausar
    de novo.

    A checagem que importa não está aqui e sim em quem chama: despausar um
    anúncio que já tem gêmeo no ar coloca duplicata na loja. Em 02/09/2026,
    36 dos 40 sofás pausados desta conta tinham gêmeo publicado no mesmo dia.
    """
    antes = cli.get(f"/items/{item_id}")
    resumo = {
        "item_id": item_id,
        "titulo": antes.get("title"),
        "status_antes": antes.get("status"),
        "preco": antes.get("price"),
        "estoque": antes.get("available_quantity"),
    }
    if simular:
        resumo["simulado"] = True
        return resumo
    if antes.get("status") == "closed":
        resumo["resultado"] = "recusado: anúncio encerrado não reativa"
        return resumo
    status, corpo = cli.escrever("PUT", f"/items/{item_id}", {"status": "active"})
    resumo["status_http"] = status
    if status in (200, 201):
        depois = cli.get(f"/items/{item_id}")
        resumo["resultado"] = "reativado"
        resumo["status_depois"] = depois.get("status")
        resumo["sub_status"] = depois.get("sub_status")
    else:
        resumo["resultado"] = "falhou"
        resumo["erro"] = str(corpo)[:300]
    return resumo


def corrigir_sku(cli: MLClient, item_id: str, sku_novo: str, *,
                 simular: bool = True) -> dict:
    """
    Corrige o SKU (SELLER_SKU) de um anúncio existente. Não mexe em preço,
    envio, título nem nenhum outro atributo — só troca o valor desse campo.

    O ML guarda SKU em `seller_custom_field` OU no atributo `SELLER_SKU`;
    esta conta usa o atributo (ver `ml_api.sku_do_item`), então é ali que
    a correção entra.
    """
    antes = cli.get(f"/items/{item_id}") or {}
    sku_antes = None
    for a in antes.get("attributes") or []:
        if a.get("id") == "SELLER_SKU":
            sku_antes = a.get("value_name")
            break
    resumo = {
        "item_id": item_id, "titulo": antes.get("title"),
        "status": antes.get("status"), "vendidos": antes.get("sold_quantity"),
        "sku_antes": sku_antes, "sku_novo": sku_novo,
    }
    if simular:
        resumo["simulado"] = True
        return resumo

    payload = {"attributes": [{"id": "SELLER_SKU", "value_name": sku_novo}]}
    status, corpo = cli.escrever("PUT", f"/items/{item_id}", payload)
    resumo["status_http"] = status
    if status not in (200, 201):
        resumo["resultado"] = "falhou"
        resumo["erro"] = str(corpo)[:300]
        return resumo

    real = cli.get(f"/items/{item_id}") or {}
    sku_depois = None
    for a in real.get("attributes") or []:
        if a.get("id") == "SELLER_SKU":
            sku_depois = a.get("value_name")
            break
    resumo["sku_depois"] = sku_depois
    resumo["resultado"] = "corrigido" if sku_depois == sku_novo else "aceito mas não colou"
    return resumo


def corrigir_item(cli: MLClient, item_id: str, *,
                  titulo_novo: str | None = None,
                  atributos_novos: dict[str, str] | None = None,
                  simular: bool = True) -> dict:
    """
    Corrige título e/ou atributos (ex.: SELLER_SKU, COLOR) de um anúncio
    existente, num PUT só — mesma trava de sempre: só escreve com
    simular=False, e nunca mexe em preço, envio nem no que não foi pedido.

    `atributos_novos` é {id_do_atributo: valor}, ex.: {"COLOR": "Cinza"}.
    Usa a mesma trava de `item.attributes.not_modifiable` em anúncio
    `closed` — ver `corrigir_sku`.
    """
    antes = cli.get(f"/items/{item_id}") or {}
    attrs_antes = {a.get("id"): a.get("value_name") for a in antes.get("attributes") or []}
    resumo = {
        "item_id": item_id, "status": antes.get("status"),
        "vendidos": antes.get("sold_quantity"),
        "titulo_antes": antes.get("title"), "titulo_novo": titulo_novo,
        "atributos_antes": {k: attrs_antes.get(k) for k in (atributos_novos or {})},
        "atributos_novos": atributos_novos,
    }
    if simular:
        resumo["simulado"] = True
        return resumo

    payload: dict = {}
    if titulo_novo is not None:
        payload["title"] = titulo_novo
    if atributos_novos:
        payload["attributes"] = [{"id": k, "value_name": v} for k, v in atributos_novos.items()]

    status, corpo = cli.escrever("PUT", f"/items/{item_id}", payload)
    resumo["status_http"] = status
    if status not in (200, 201):
        resumo["resultado"] = "falhou"
        resumo["erro"] = str(corpo)[:300]
        return resumo

    real = cli.get(f"/items/{item_id}") or {}
    attrs_depois = {a.get("id"): a.get("value_name") for a in real.get("attributes") or []}
    resumo["titulo_depois"] = real.get("title")
    resumo["atributos_depois"] = {k: attrs_depois.get(k) for k in (atributos_novos or {})}
    bateu_titulo = titulo_novo is None or resumo["titulo_depois"] == titulo_novo
    # limpar um atributo (v == "") faz o ML devolver o campo ausente/None, não
    # uma string vazia -- comparar só com "==" marcava isso como "não colou"
    # mesmo quando o valor foi removido com sucesso.
    bateu_atributos = all(
        (not v and not resumo["atributos_depois"].get(k)) or resumo["atributos_depois"].get(k) == v
        for k, v in (atributos_novos or {}).items()
    )
    resumo["resultado"] = "corrigido" if (bateu_titulo and bateu_atributos) else "aceito mas não colou tudo"
    return resumo


def corrigir_disponibilidade(cli: MLClient, item_id: str, prazo: str | None, *,
                             simular: bool = True) -> dict:
    """
    Ajusta o prazo de disponibilidade de estoque de um anúncio existente.

    Na tela do ML esse campo aparece como "Disponibilidade de estoque"; na
    API é o sale_term MANUFACTURING_TIME (ex: value_name="7 dias"). Não mexe
    em preço, envio, título nem em nenhum outro atributo.

    prazo=None remove o sale_term inteiro — o anúncio volta a não mostrar
    prazo de disponibilidade nenhum.
    """
    antes = cli.get(f"/items/{item_id}") or {}
    prazo_antes = None
    for t in antes.get("sale_terms") or []:
        if t.get("id") == "MANUFACTURING_TIME":
            prazo_antes = t.get("value_name")
            break
    resumo = {
        "item_id": item_id, "titulo": antes.get("title"),
        "status": antes.get("status"), "vendidos": antes.get("sold_quantity"),
        "prazo_antes": prazo_antes, "prazo_novo": prazo,
    }
    if simular:
        resumo["simulado"] = True
        return resumo

    # Omitir o termo do array não remove nada — o ML mantém o valor antigo
    # ("aceito mas não colou"). É preciso mandar o termo de volta com
    # value_name=None: só assim a API interpreta como pedido de exclusão.
    termos = [t for t in (antes.get("sale_terms") or [])
              if t.get("id") != "MANUFACTURING_TIME"]
    termos.append({"id": "MANUFACTURING_TIME", "value_name": prazo})
    status, corpo = cli.escrever("PUT", f"/items/{item_id}",
                                 {"sale_terms": termos})
    resumo["status_http"] = status
    if status not in (200, 201):
        resumo["resultado"] = "falhou"
        resumo["erro"] = str(corpo)[:300]
        return resumo

    real = cli.get(f"/items/{item_id}") or {}
    prazo_depois = None
    for t in real.get("sale_terms") or []:
        if t.get("id") == "MANUFACTURING_TIME":
            prazo_depois = t.get("value_name")
            break
    resumo["prazo_depois"] = prazo_depois
    resumo["resultado"] = "corrigido" if prazo_depois == prazo else "aceito mas não colou"
    return resumo


def corrigir_descricao(cli: MLClient, item_id: str, texto_novo: str, *,
                       simular: bool = True) -> dict:
    """
    Substitui a descrição de um anúncio existente. Não mexe em preço, título,
    atributo nem envio — só o texto da descrição.

    PUT em vez de POST: o item já tem descrição (POST é só para criar a
    primeira). PUT falha se não houver nenhuma ainda.
    """
    antes = cli.get(f"/items/{item_id}") or {}
    texto_antes = descricao_de(cli, item_id)
    resumo = {
        "item_id": item_id, "titulo": antes.get("title"),
        "status": antes.get("status"), "vendidos": antes.get("sold_quantity"),
        "texto_antes": texto_antes, "texto_novo": texto_novo,
    }
    if simular:
        resumo["simulado"] = True
        return resumo

    status, corpo = cli.escrever("PUT", f"/items/{item_id}/description",
                                 {"plain_text": texto_novo})
    resumo["status_http"] = status
    if status not in (200, 201):
        resumo["resultado"] = "falhou"
        resumo["erro"] = str(corpo)[:300]
        return resumo

    resumo["texto_depois"] = descricao_de(cli, item_id)
    resumo["resultado"] = "corrigido" if resumo["texto_depois"] == texto_novo else "aceito mas não colou"
    return resumo


def alterar_preco(cli: MLClient, item_id: str, preco: float, *,
                  simular: bool = True) -> dict:
    """
    Muda o preço de um anúncio. Tem volta — mas nem sempre a volta que se quer.

    Três recusas por segurança, todas por motivo já visto em produção:

    1. **Promoção ativa.** Dentro de campanha o preço que vale é o da promoção,
       e o PUT no item ou é ignorado ou briga com ela. O caminho é sair da
       promoção primeiro, e sair não garante voltar.
    2. **Variações.** Com variação o preço mora em cada uma; mexer só no item
       aplica pela metade e fica pior que não mexer.
    3. **Encerrado.** Anúncio fechado não recebe preço.

    E a que não dá para prevenir daqui: o ML ancora no preço praticado e pode
    recusar um aumento grande com ERROR_CREDIBILITY_DISCOUNTED_PRICE. Por isso
    a função relê o item depois de escrever e reporta o preço que REALMENTE
    ficou — HTTP 200 não é prova de que o preço mudou.
    """
    antes = cli.get(f"/items/{item_id}") or {}
    preco_antes = antes.get("price")
    resumo = {
        "item_id": item_id,
        "titulo": antes.get("title"),
        "status_antes": antes.get("status"),
        "preco_antes": preco_antes,
        "preco_novo": float(preco),
        "vendidos": antes.get("sold_quantity"),
        "estoque": antes.get("available_quantity"),
        "variacoes": len(antes.get("variations") or []),
    }
    if preco_antes:
        resumo["variacao_pct"] = (float(preco) / float(preco_antes) - 1) * 100

    # No modelo User Products o preço PODE ser do produto e não do anúncio.
    # Em 03/09/2026 o PUT em MLB7573722130 moveu o MLB7573722152 três segundos
    # depois, sozinho — mas o PUT em MLB7574903018 NÃO moveu o MLB4992253385
    # (tipos diferentes, e o irmão em promoção ativa; com duas observações não
    # dá para dizer qual é a causa). Por isso o grupo é listado ANTES e relido
    # DEPOIS: o que vale é o que mudou, não o que deveria mudar. Na Decoralli
    # 190 dos 216 ativos têm irmão de user product.
    up = antes.get("user_product_id")
    resumo["user_product"] = up
    resumo["irmaos"] = []
    if up:
        try:
            busca = cli.get(f"/users/{cli.user_id}/items/search",
                            user_product_id=up) or {}
            resumo["irmaos"] = [i for i in (busca.get("results") or [])
                                if i != item_id]
        except Exception as e:
            resumo["aviso_irmaos"] = (f"não consegui listar os anúncios do mesmo "
                                      f"user product ({up}): {e}")

    promos_ativas = []
    try:
        for pr in (cli.promocoes_do_item(item_id) or []):
            if isinstance(pr, dict) and pr.get("status") == "started":
                promos_ativas.append(f"{pr.get('type')} {pr.get('id')} R$ {pr.get('price')}")
    except Exception as e:                       # não deixa a leitura derrubar o passo
        resumo["aviso_promocoes"] = f"não consegui ler promoções: {e}"
    resumo["promocoes_ativas"] = promos_ativas

    if antes.get("status") == "closed":
        resumo["resultado"] = "recusado: anúncio encerrado não recebe preço"
        return resumo
    if resumo["variacoes"]:
        resumo["resultado"] = (f"recusado: {resumo['variacoes']} variação(ões) — "
                               f"o preço vai em cada uma, não no item")
        return resumo
    if promos_ativas:
        resumo["resultado"] = ("recusado: promoção ativa — saia dela antes "
                               f"({'; '.join(promos_ativas)})")
        return resumo

    if simular:
        resumo["simulado"] = True
        return resumo

    status, corpo = cli.escrever("PUT", f"/items/{item_id}", {"price": float(preco)})
    resumo["status_http"] = status
    depois = cli.get(f"/items/{item_id}") or {}
    resumo["preco_depois"] = depois.get("price")

    # Quais irmãos de fato acompanharam. Supor é o erro que esta releitura
    # existe para evitar — a propagação acontece em alguns casos e não em outros.
    if resumo.get("irmaos"):
        moveram, ficaram = [], []
        for irmao in resumo["irmaos"]:
            outro = cli.get(f"/items/{irmao}") or {}
            (moveram if outro.get("price") == float(preco) else ficaram).append(
                f"{irmao} (R$ {outro.get('price')})")
        resumo["irmaos_que_moveram"] = moveram
        resumo["irmaos_intactos"] = ficaram

    if status in (200, 201) and depois.get("price") == float(preco):
        resumo["resultado"] = "alterado"
    elif status in (200, 201):
        resumo["resultado"] = "aceito mas NÃO aplicou — confira na tela"
        resumo["erro"] = str(corpo)[:300]
    else:
        resumo["resultado"] = "falhou"
        resumo["erro"] = str(corpo)[:300]
    return resumo


def sair_de_promocao(cli: MLClient, item_id: str, *, simular: bool = True,
                     tipo: str | None = None) -> dict:
    """
    Tira o anúncio da promoção que MANDA no preço — a mais barata das ativas.

    Sair não tem volta garantida: o ML não obriga a reentrada, e depois ancora
    no preço praticado para recusar aumento. Por isso o passo simula por
    padrão e mostra o que passa a valer.

    Duas armadilhas embutidas, ambas já pagas em produção:

    - **SMART e PRICE_MATCHING exigem `offer_id`**, que é o `ref_id` da
      listagem. Sem ele o ML devolve 400 e o anúncio CONTINUA na campanha —
      falha silenciosa se ninguém reler.
    - **HTTP 200 não é prova.** Duas leituras rápidas já mostraram `started`
      num anúncio que tinha saído. Aqui a releitura espera antes de concluir,
      e o resultado diz o que a API respondeu na segunda olhada.
    """
    ativas = []
    try:
        for x in (cli.promocoes_do_item(item_id) or []):
            if isinstance(x, dict) and x.get("status") == "started" and x.get("price"):
                ativas.append(x)
    except Exception as e:
        return {"item_id": item_id, "resultado": f"não consegui ler as promoções: {e}"}

    resumo = {"item_id": item_id, "ativas": len(ativas)}
    if not ativas:
        resumo["resultado"] = "nada a fazer: sem promoção ativa"
        return resumo

    ativas.sort(key=lambda x: float(x["price"]))

    # `tipo` existe porque duas campanhas podem estar no MESMO preço, e aí
    # "a mais barata" não escolhe nada — mas elas têm datas de fim diferentes,
    # e é a data que decide qual sair. Em 03/09/2026 o MLB7575758162 tinha
    # DEAL e SELLER_CAMPAIGN a R$ 771,63: a segunda morria naquela noite, a
    # primeira só em 10/09. Sair da DEAL não muda o preço hoje e devolve o
    # anúncio à tabela quando a outra expirar.
    if tipo:
        escolhidas = [x for x in ativas if x.get("type") == tipo]
        if not escolhidas:
            resumo["resultado"] = (f"nada a fazer: não há promoção ativa do tipo "
                                   f"{tipo} (ativas: {[x.get('type') for x in ativas]})")
            return resumo
        manda = escolhidas[0]
        restantes = [x for x in ativas if x is not manda]
        prox = restantes[0] if restantes else None
    else:
        manda, prox = ativas[0], (ativas[1] if len(ativas) > 1 else None)
    resumo.update({
        "tipo": manda.get("type"), "promocao_id": manda.get("id"),
        "offer_id": manda.get("ref_id"), "preco_hoje": float(manda["price"]),
        "termina": manda.get("finish_date"),
        "passa_a_valer": float(prox["price"]) if prox else None,
        "passa_a_valer_tipo": (prox.get("type") if prox else "tabela"),
    })
    if resumo["passa_a_valer"]:
        resumo["salto_pct"] = (resumo["passa_a_valer"] / resumo["preco_hoje"] - 1) * 100

    # A recusa que evita a falha silenciosa.
    if manda.get("type") in ("SMART", "PRICE_MATCHING") and not manda.get("ref_id"):
        resumo["resultado"] = (f"recusado: {manda.get('type')} sem ref_id — o DELETE "
                               f"voltaria 400 e o anúncio ficaria na campanha")
        return resumo

    if simular:
        resumo["simulado"] = True
        return resumo

    status, corpo = cli.sair_da_promocao(item_id, manda.get("id"), manda.get("type"),
                                         offer_id=manda.get("ref_id"))
    resumo["status_http"] = status

    # A saída não aparece na leitura seguinte: o ML leva dezenas de segundos
    # para refletir. Em 03/09/2026 quatro saídas SMART deram "ainda na
    # campanha" com espera de 4s e estavam TODAS fora quando relidas depois —
    # falso negativo que faz repetir o DELETE. Insiste com folga antes de
    # concluir, e só chama de falha quando o prazo inteiro passou.
    ainda = True
    for espera in (6, 10, 20):
        time.sleep(espera)
        try:
            ainda = any(
                isinstance(x, dict) and x.get("status") == "started"
                and x.get("type") == manda.get("type")
                and x.get("id") == manda.get("id")
                for x in (cli.promocoes_do_item(item_id) or []))
        except Exception:
            ainda = True               # leitura falhou: não conclui que saiu
            continue
        if not ainda:
            break
    resumo["ainda_na_campanha"] = bool(ainda)
    if status in (200, 201, 204) and not ainda:
        resumo["resultado"] = "saiu"
        item = cli.get(f"/items/{item_id}") or {}
        resumo["preco_agora"] = item.get("price")
    elif status in (200, 201, 204):
        resumo["resultado"] = "API aceitou mas o anúncio SEGUE na campanha — confira na tela"
    else:
        resumo["resultado"] = "falhou"
        resumo["erro"] = str(corpo)[:300]
    return resumo


def descricao_de(cli: MLClient, item_id: str) -> str | None:
    """Descrição vai em chamada separada, depois que o item existe."""
    try:
        d = cli.get(f"/items/{item_id}/description")
        return d.get("plain_text") or d.get("text")
    except Exception:
        return None


def _ler_o_erro(corpo) -> dict:
    """Extrai os códigos de `cause` e traduz os que já conhecemos.

    O ML devolve o motivo real dentro de `cause`, um nível abaixo de onde quem
    lê o terminal costuma olhar. Sem isto, `shipping.free_shipping.cost_exceeded`
    — o ML dizendo que o anúncio nasce no prejuízo — aparece como um 400 seco.

    Não inventa leitura: código desconhecido volta cru, sem tradução.
    """
    if not isinstance(corpo, dict):
        return {}

    codigos: list[str] = []
    for c in corpo.get("cause") or []:
        if isinstance(c, dict):
            for campo in ("code", "cause_id", "type"):
                if c.get(campo):
                    codigos.append(str(c[campo]))
                    break
            else:
                if c.get("message"):
                    codigos.append(str(c["message"])[:120])
        elif c:
            codigos.append(str(c)[:120])

    texto = " ".join([str(corpo.get("message") or ""), str(corpo.get("error") or "")])
    for conhecido in DIAGNOSTICO_DE_ERRO:
        if conhecido in texto and conhecido not in codigos:
            codigos.append(conhecido)

    saida: dict = {}
    if codigos:
        saida["codigos"] = codigos
    lidos = [f"{c}: {DIAGNOSTICO_DE_ERRO[c]}"
             for c in codigos if c in DIAGNOSTICO_DE_ERRO]
    if lidos:
        saida["diagnostico"] = lidos
    return saida


def publicar(cli: MLClient, payload: dict, *, simular: bool = True,
             descricao: str | None = None) -> dict:
    """
    Publica o anúncio. Com simular=True (padrão) NÃO fala com a API.

    Quem chama precisa ter confirmado a conta antes — o MLClient já aborta se
    o user_id do token divergir do registro, e essa checagem não se contorna.
    """
    if simular:
        return {"simulado": True, "payload": payload}

    # Anúncio sincronizado tem endpoint PRÓPRIO. Medido em 02/09/2026:
    # `POST /items` com user_product_id no corpo devolve
    # "The fields [user_product_id] are invalid for requested call". O caminho
    # é `POST /user-products/{id}/items`, e ele recusa tudo que pertence ao
    # produto e não ao anúncio — condition, family_name, attributes e
    # local_pick_up. Sobram preço, modalidade, estoque e frete, que é
    # exatamente o que um anúncio sincronizado carrega.
    produto = payload.pop("user_product_id", None)
    if produto:
        payload = {k: v for k, v in payload.items()
                   if k not in ("condition", "family_name", "attributes")}
        if isinstance(payload.get("shipping"), dict):
            payload["shipping"] = {k: v for k, v in payload["shipping"].items()
                                   if k != "local_pick_up"}
        caminho = f"/user-products/{produto}/items"
    else:
        caminho = "/items"

    status, corpo = cli.escrever("POST", caminho, payload)
    resultado = {"simulado": False, "status": status, "corpo": corpo}
    if status not in (200, 201):
        resultado.update(_ler_o_erro(corpo))
        return resultado

    novo = corpo.get("id")
    resultado["item_id"] = novo
    resultado["permalink"] = corpo.get("permalink")
    # O que o ML DEU, que pode não ser o que pedimos — é aqui que se descobre
    # se o me2 pediu foi aceito ou silenciosamente rebaixado.
    resultado["envio_obtido"] = (corpo.get("shipping") or {}).get("mode")
    resultado["logistic_type"] = (corpo.get("shipping") or {}).get("logistic_type")

    # A resposta do POST é OTIMISTA e não vale como veredito: em 02/09/2026 o
    # MLB5178925399 voltou "me2" no POST e, relido segundos depois, estava
    # not_specified com a tag `lost_me2_by_dimensions`. O ML aceita, valida
    # depois, e tira o Envios se a medida de embalagem não fecha. Quem não
    # relê publica achando que deu certo.
    try:
        real = cli.get(f"/items/{novo}")
        s = real.get("shipping") or {}
        resultado["envio_real"] = s.get("mode")
        resultado["logistic_real"] = s.get("logistic_type")
        resultado["tags_envio"] = s.get("tags")
        resultado["status_real"] = real.get("status")
        # A tag não vem como erro: o POST devolveu 201 e o anúncio existe.
        # Mas `lost_me2_by_dimensions` é o ML dizendo que derrubou o Envios,
        # e essa linha some no meio do JSON se ninguém a levantar.
        lidos = [f"{t}: {DIAGNOSTICO_DE_ERRO[t]}"
                 for t in (s.get("tags") or []) if t in DIAGNOSTICO_DE_ERRO]
        if lidos:
            resultado["diagnostico"] = lidos
    except Exception as erro:
        resultado["envio_real"] = f"nao relido: {erro}"

    if descricao and novo:
        s2, c2 = cli.escrever("POST", f"/items/{novo}/description",
                              {"plain_text": descricao})
        resultado["descricao_status"] = s2
        if s2 not in (200, 201):
            resultado["descricao_erro"] = c2
    return resultado


def resumo_do_payload(payload: dict, origem: dict) -> str:
    """Texto curto para conferir antes de autorizar a publicação."""
    envio = payload.get("shipping") or {}
    linhas = [
        f"origem      : {origem.get('id')} ({origem.get('status')}, "
        f"envio {(origem.get('shipping') or {}).get('mode')})",
        f"titulo      : {payload.get('title')}",
        f"family_name : {payload.get('family_name') or '(nenhum — produto independente)'}",
        f"categoria   : {payload.get('category_id')}",
        f"modalidade  : {payload.get('listing_type_id')}",
        f"preco       : {payload.get('price')} {payload.get('currency_id')}",
        f"estoque     : {payload.get('available_quantity')}",
        f"ENVIO       : mode={envio.get('mode')} "
        f"free_shipping={envio.get('free_shipping')}",
        f"fotos       : {len(payload.get('pictures') or [])}",
        f"atributos   : {len(payload.get('attributes') or [])} "
        f"(nenhum de embalagem, por regra)",
    ]
    peso = next((a["value_name"] for a in payload.get("attributes") or []
                 if a["id"] == "WEIGHT"), None)
    linhas.append(f"peso        : {peso or 'NÃO DECLARADO (melhor que declarar errado)'}")
    return "\n".join(linhas)


def payload_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
