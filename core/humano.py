"""
Tradução do vocabulário do Mercado Livre para português de gente.

Motivo de existir, em uma frase: chegou no celular do operador
"Situação nova no anúncio (paused_by_seller)" e ele não fez ideia do que
tinha acontecido. Alerta que precisa ser decifrado não é alerta — é trabalho
extra numa hora em que a pessoa geralmente está sem tempo.

A regra aqui é uma só: a mensagem diz O QUE ACONTECEU, com sujeito e verbo,
como alguém contaria por telefone. Código técnico só aparece entre parênteses,
no fim, para quem quiser conferir.
"""
from __future__ import annotations

# ---------------------------------------------------------------- status
STATUS = {
    "active": "no ar",
    "paused": "pausado",
    "closed": "encerrado",
    "under_review": "em análise pelo Mercado Livre",
    "inactive": "inativo",
    "payment_required": "aguardando pagamento de taxa",
    "not_yet_active": "ainda não publicado",
}

SUB_STATUS = {
    "out_of_stock": "sem estoque",
    "paused_by_seller": "pausado por alguém da conta",
    "deleted": "excluído",
    "expired": "expirado",
    "freeze": "congelado pelo Mercado Livre",
    "suspended": "suspenso pelo Mercado Livre",
    "banned_registration": "bloqueado por cadastro irregular",
    "waiting_for_patch": "aguardando correção obrigatória",
    "picture_download_pending": "esperando o envio das fotos",
    "warning": "com advertência do Mercado Livre",
    "under_review": "em análise pelo Mercado Livre",
    "shipping_disabled": "com envio desabilitado",
    "moderated": "moderado pelo Mercado Livre",
}

ENVIO = {
    "me2": "Mercado Envios",
    "me1": "Mercado Envios (antigo)",
    "custom": "envio por sua conta",
    "not_specified": "sem envio configurado",
    "drop_off": "postagem em agência",
    "cross_docking": "coleta pelo Mercado Livre",
    "xd_drop_off": "postagem em agência",
    "self_service": "Flex (entrega própria)",
    "fulfillment": "Full (estoque no Mercado Livre)",
}

TIPO_ANUNCIO = {
    "gold_pro": "Premium",
    "gold_special": "Clássico",
    "gold": "Ouro",
    "silver": "Prata",
    "bronze": "Bronze",
    "free": "Grátis",
}


def _traduzir(tabela: dict, valor, padrao_tecnico: bool = True) -> str:
    """
    Traduz e, quando não conhece o termo, devolve o código cru em vez de
    inventar. Preferimos um código estranho na tela a uma tradução errada:
    o código o operador pesquisa, a tradução errada ele acredita.
    """
    if valor is None or valor == "":
        return ""
    chave = str(valor).strip().lower()
    return tabela.get(chave, str(valor) if padrao_tecnico else "")


def status(valor) -> str:
    return _traduzir(STATUS, valor)


def sub_status(valor) -> str:
    """Aceita 'a,b' ou lista, como o Mercado Livre devolve."""
    if not valor:
        return ""
    itens = valor if isinstance(valor, (list, tuple, set)) else str(valor).split(",")
    traduzidos = [_traduzir(SUB_STATUS, x) for x in itens if str(x).strip()]
    traduzidos = [t for t in traduzidos if t]
    if not traduzidos:
        return ""
    if len(traduzidos) == 1:
        return traduzidos[0]
    return ", ".join(traduzidos[:-1]) + " e " + traduzidos[-1]


def envio(valor) -> str:
    return _traduzir(ENVIO, valor)


def tipo_anuncio(valor) -> str:
    return _traduzir(TIPO_ANUNCIO, valor)


# ---------------------------------------------------------------- contas
_CACHE_NOMES: dict[str, str] = {}


def nome_da_conta(slug: str) -> str:
    """
    O nome que a PESSOA usa para essa conta — "Ênio Toldos", não
    "enio-toldos-principal" e muito menos "SV20260519065452".

    O apelido automático do Mercado Livre é o pior dos três: além de
    ilegível, ele muda quando o cliente configura a loja, e aí o histórico
    de mensagens parece ser de outra conta.
    """
    if not slug:
        return ""
    if slug in _CACHE_NOMES:
        return _CACHE_NOMES[slug]
    try:
        from .config import carregar_clientes
        for cliente in carregar_clientes(apenas_ativos=False):
            for conta in cliente.contas:
                rotulo = cliente.nome
                if len(cliente.contas) > 1:
                    rotulo = f"{cliente.nome} · {conta.nome_conta}"
                _CACHE_NOMES[conta.slug] = rotulo
    except Exception:
        pass
    return _CACHE_NOMES.get(slug, slug)


def titulo_curto(texto: str, limite: int = 46) -> str:
    """
    Corta no espaço, nunca no meio da palavra, e não usa reticências quando
    o título já coube. Título picado no meio de uma palavra é a diferença
    entre parecer um sistema e parecer um sistema quebrado.
    """
    # Espaço dobrado vem direto do título do anúncio e aparece na mensagem
    # como se fosse defeito nosso.
    texto = " ".join((texto or "").split())
    if len(texto) <= limite:
        return texto
    corte = texto[:limite].rsplit(" ", 1)[0]
    return (corte or texto[:limite]).rstrip(" ,.-") + "…"


def limpar_pontuacao(texto: str) -> str:
    """
    Tira a pontuação dobrada que aparece quando um título cortado cai no fim
    de uma frase: "…foto de capa de Rampa Pet Puff Nmg 2 Em…." — três pontos
    da reticência mais o ponto final. Detalhe pequeno, mas é o tipo de coisa
    que faz a mensagem parecer gerada por máquina quebrada em vez de escrita.
    """
    for dobrado, certo in (("….", "…"), ("…,", "…"), ("…:", "…"),
                           ("..", "."), (" .", "."), (" ,", ",")):
        texto = texto.replace(dobrado, certo)
    return texto


def titulo_distintivo(texto: str, limite: int = 52) -> str:
    """
    Corte que guarda o COMEÇO e o FIM do título.

    Existe por causa de anúncios que só se diferenciam no final — "…Porte
    Cinza" e "…Porte Marrom Claro". Cortados pelo começo, os dois viram a
    mesma linha na tela, e a mensagem passa a parecer que repetiu o mesmo
    anúncio duas vezes quando na verdade são dois produtos diferentes.
    """
    texto = " ".join((texto or "").split())
    if len(texto) <= limite:
        return texto
    cabeca = max(12, int(limite * 0.6))
    cauda = limite - cabeca - 1
    inicio = texto[:cabeca].rsplit(" ", 1)[0] or texto[:cabeca]
    fim = texto[-cauda:]
    if " " in fim:
        fim = fim.split(" ", 1)[1]
    return f"{inicio}… {fim}".strip()
