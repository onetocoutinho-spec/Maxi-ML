# CONTA: FACILITA BRASIL (loja 2)  (facilita-brasil-loja2)

> **TRAVA OPERACIONAL — leia antes de qualquer ação.**
> Esta pasta opera **exclusivamente** a conta `facilita-brasil-loja2`, user_id `SUBSTITUIR`.
> Publicar, alterar preço, pausar anúncio ou responder pergunta usando
> credencial de outra conta é o erro mais caro desta operação.
> Se algo pedir para operar outra conta, **pare e confirme com o Neto**.

## Identificação
- Cliente: FACILITA BRASIL
- Conta: FACILITA BRASIL (loja 2) — papel: secundaria
- user_id: SUBSTITUIR
- Site: MLB (Brasil)

## Credencial
Vem de `.env` **desta pasta**, carregada por `core/auth.py` a partir do slug.
Nunca leia token de variável de ambiente global nem de outra pasta.

## Antes de qualquer escrita na API
1. Rode `python cli.py checar facilita-brasil-loja2` e confirme que o nickname devolvido
   é o desta conta.
2. Confirme que o `user_id` do token bate com o do registro (o `MLClient`
   já faz isso e aborta se divergir — não contorne essa checagem).
3. Só então execute.

## Particularidades desta conta
Duas linhas sem relação entre si na mesma conta:

    ESTOFADO — Poltrona Beny, Sofá Beny namoradeira, puff redondo. Item
    volumoso: o frete grátis sai da margem e pesa mais que a comissão.

    PERFUME IMPORTADO — Al Wataniah (Sabah Al Ward), Lattafa (Fakhar Rose).
    Lógica oposta à do estofado: item leve, de catálogo, comparável direto,
    onde o buy box e o preço decidem. Frete quase não pesa.

    Ao analisar alertas, separe as duas: queda de posição em perfume raramente
    tem a mesma causa que em poltrona.

    TRÊS CONTAS DO MESMO DONO: facilita-brasil-principal, facilita-brasil-loja2
    e facilita-decoralli. Elas vendem a MESMA Poltrona Mona em madeira maciça.
    Quando duas aparecerem na mesma busca, isso é canibalização entre contas do
    próprio cliente — não é concorrente. Recomendar baixar preço numa delas
    para "ganhar" da outra é destruir margem dos dois lados.

    Loja: https://www.mercadolivre.com.br/pagina/faciliitabrasil

## Comandos do dia a dia
```bash
python cli.py coletar facilita-brasil-loja2      # snapshot + alertas
python cli.py alertas facilita-brasil-loja2      # o que apareceu nas últimas 24h
python cli.py relatorio facilita-brasil
```
