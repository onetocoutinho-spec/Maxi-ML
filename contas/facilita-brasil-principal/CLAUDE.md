# CONTA: FACILITA BRASIL  (facilita-brasil-principal)

> **TRAVA OPERACIONAL — leia antes de qualquer ação.**
> Esta pasta opera **exclusivamente** a conta `facilita-brasil-principal`, user_id `SUBSTITUIR`.
> Publicar, alterar preço, pausar anúncio ou responder pergunta usando
> credencial de outra conta é o erro mais caro desta operação.
> Se algo pedir para operar outra conta, **pare e confirme com o Neto**.

## Identificação
- Cliente: FACILITA BRASIL
- Conta: FACILITA BRASIL — papel: principal
- user_id: SUBSTITUIR
- Site: MLB (Brasil)

## Credencial
Vem de `.env` **desta pasta**, carregada por `core/auth.py` a partir do slug.
Nunca leia token de variável de ambiente global nem de outra pasta.

## Antes de qualquer escrita na API
1. Rode `python cli.py checar facilita-brasil-principal` e confirme que o nickname devolvido
   é o desta conta.
2. Confirme que o `user_id` do token bate com o do registro (o `MLClient`
   já faz isso e aborta se divergir — não contorne essa checagem).
3. Só então execute.

## Particularidades desta conta
Estofados: poltronas decorativas, poltronas do papai reclináveis,
    sofás, sofás-cama e namoradeiras. Loja no ML:
    https://www.mercadolivre.com.br/pagina/mayararoncolatocambrais

    Item volumoso. Frete pesa muito e some da margem sem aviso — nesta
    categoria conferir o custo do frete é tão importante quanto conferir o
    preço do concorrente.

    TRÊS CONTAS DO MESMO DONO: facilita-brasil-principal, facilita-brasil-loja2
    e facilita-decoralli. Elas vendem a MESMA Poltrona Mona em madeira maciça.
    Quando duas aparecerem na mesma busca, isso é canibalização entre contas do
    próprio cliente — não é concorrente. Recomendar baixar preço numa delas
    para "ganhar" da outra é destruir margem dos dois lados.

    ATENÇÃO — sobreposição com outro cliente da carteira: a linha de móveis
    do Ênio Toldos (ShoppLima) vem da fábrica da Maxi e ocupa a mesma
    prateleira (sala de estar). Se as duas contas aparecerem na mesma busca,
    é canibalização entre clientes SEUS, não concorrência. Vale conferir
    antes de recomendar baixar preço em qualquer uma das duas.

## Comandos do dia a dia
```bash
python cli.py coletar facilita-brasil-principal      # snapshot + alertas
python cli.py alertas facilita-brasil-principal      # o que apareceu nas últimas 24h
python cli.py relatorio facilita-brasil
```
