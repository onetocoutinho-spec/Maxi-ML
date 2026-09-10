# CONTA: MAXI DO BRASIL ECOMMERCE LTDA  (maxi-brasil-principal)

> **TRAVA OPERACIONAL — leia antes de qualquer ação.**
> Esta pasta opera **exclusivamente** a conta `maxi-brasil-principal`, user_id `SUBSTITUIR`.
> Publicar, alterar preço, pausar anúncio ou responder pergunta usando
> credencial de outra conta é o erro mais caro desta operação.
> Se algo pedir para operar outra conta, **pare e confirme com o Neto**.

## Identificação
- Cliente: maxi-brasil
- Conta: MAXI DO BRASIL ECOMMERCE LTDA — papel: principal
- Login do ML: essencialmoveis2024@gmail.com
- user_id: SUBSTITUIR
- Site: MLB (Brasil)

## Credencial
Vem de `.env` **desta pasta**, carregada por `core/auth.py` a partir do slug.
Nunca leia token de variável de ambiente global nem de outra pasta.

## Antes de qualquer escrita na API
1. Rode `python cli.py checar maxi-brasil-principal` e confirme que o nickname
   devolvido é o desta conta.
2. Confirme que o `user_id` do token bate com o do registro (o `MLClient`
   já faz isso e aborta se divergir — não contorne essa checagem).
3. Só então execute.

## Particularidades desta conta

**É a conta da própria Maxi do Brasil, não de cliente terceiro.** A Maxi
fabrica e fornece móveis que o Ênio (ShoppLima) revende no ML — ver
`contas/enio-toldos-principal/`. Os mesmos produtos podem aparecer nas duas
contas com preços diferentes e propósitos diferentes: aqui é venda da
fábrica, lá é revenda. Não tratar como canibalização.

**Tem campanha de CUPOM ativa.** Foi a razão de a conta entrar no zion-ml.
Cupom não altera o preço do anúncio — o desconto some no checkout e o
orçamento é 100% do vendedor, sem co-participação do Mercado Livre. Por isso:

- `python cli.py cupons maxi-brasil-principal` mostra usos e orçamento queimado;
- o alerta `cupom_fura_o_piso` só funciona com `custos.csv` preenchido nesta
  pasta. Sem custo cadastrado ele fica calado de propósito, em vez de dar
  veredito errado.

**A conta.yaml está com os valores do template.** Confirmar com o Neto a
margem mínima e o frete médio antes de tratar qualquer piso como definitivo.
A comissão real é medida por anúncio (`python cli.py tarifas`) e tem
precedência sobre os números redondos do conta.yaml.

## Comandos do dia a dia
```bash
python cli.py coletar maxi-brasil-principal      # snapshot + alertas
python cli.py cupons maxi-brasil-principal       # campanhas de cupom
python cli.py alertas maxi-brasil-principal      # o que apareceu nas últimas 24h
python cli.py relatorio maxi-brasil
```
