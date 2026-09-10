# CONTA: Decoralli  (facilita-decoralli)

> **TRAVA OPERACIONAL — leia antes de qualquer ação.**
> Esta pasta opera **exclusivamente** a conta `facilita-decoralli`, user_id `SUBSTITUIR`.
> Publicar, alterar preço, pausar anúncio ou responder pergunta usando
> credencial de outra conta é o erro mais caro desta operação.
> Se algo pedir para operar outra conta, **pare e confirme com o Neto**.

## Identificação
- Cliente: FACILITA BRASIL
- Conta: Decoralli — papel: secundaria
- user_id: SUBSTITUIR
- Site: MLB (Brasil)

## Credencial
Vem de `.env` **desta pasta**, carregada por `core/auth.py` a partir do slug.
Nunca leia token de variável de ambiente global nem de outra pasta.

## Antes de qualquer escrita na API
1. Rode `python cli.py checar facilita-decoralli` e confirme que o nickname devolvido
   é o desta conta.
2. Confirme que o `user_id` do token bate com o do registro (o `MLClient`
   já faz isso e aborta se divergir — não contorne essa checagem).
3. Só então execute.

## Particularidades desta conta
Poltronas decorativas em madeira maciça — linha Mona (linho e corino),
    vendidas avulsas e em kit de 2. Marca Decoralli, mas mesmo dono das
    contas FACILITA BRASIL.

    Item volumoso: o frete grátis sai da margem do vendedor.

    O kit de 2 poltronas concorre com a poltrona avulsa da própria casa —
    conferir antes de tratar diferença de preço entre eles como problema.

    TRÊS CONTAS DO MESMO DONO: facilita-brasil-principal, facilita-brasil-loja2
    e facilita-decoralli. Elas vendem a MESMA Poltrona Mona em madeira maciça.
    Quando duas aparecerem na mesma busca, isso é canibalização entre contas do
    próprio cliente — não é concorrente. Recomendar baixar preço numa delas
    para "ganhar" da outra é destruir margem dos dois lados.

    Loja: https://www.mercadolivre.com.br/pagina/wedmirmariabezerrildasilva

## Comandos do dia a dia
```bash
python cli.py coletar facilita-decoralli      # snapshot + alertas
python cli.py alertas facilita-decoralli      # o que apareceu nas últimas 24h
python cli.py relatorio facilita-brasil
```
