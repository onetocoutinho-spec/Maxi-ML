# CONTA: Ênio Toldos (ShoppLima)  (enio-toldos-principal)

> **TRAVA OPERACIONAL — leia antes de qualquer ação.**
> Esta pasta opera **exclusivamente** a conta `enio-toldos-principal`, user_id `SUBSTITUIR`.
> Publicar, alterar preço, pausar anúncio ou responder pergunta usando
> credencial de outra conta é o erro mais caro desta operação.
> Se algo pedir para operar outra conta, **pare e confirme com o Neto**.

## Identificação
- Cliente: enio-toldos
- Conta: Ênio Toldos (ShoppLima) — papel: principal
- user_id: SUBSTITUIR
- Site: MLB (Brasil)

## Credencial
Vem de `.env` **desta pasta**, carregada por `core/auth.py` a partir do slug.
Nunca leia token de variável de ambiente global nem de outra pasta.

## Antes de qualquer escrita na API
1. Rode `python cli.py checar enio-toldos-principal` e confirme que o nickname devolvido
   é o desta conta.
2. Confirme que o `user_id` do token bate com o do registro (o `MLClient`
   já faz isso e aborta se divergir — não contorne essa checagem).
3. Só então execute.

## Particularidades desta conta
Duas linhas na mesma conta, e elas não se analisam do mesmo jeito:

- **Toldos** — item de projeto, vendido por medida. Comparação de preço com
  concorrente exige conferir a dimensão do anúncio e se o frete está incluso.
- **Móveis (fábrica da Maxi)** — item de catálogo, comparável direto.
  Buy box importa; preço é o principal fator de vitória.

Nunca trate uma queda de posição em toldo com a mesma leitura de uma queda
em móvel — as causas são diferentes.

## Comandos do dia a dia
```bash
python cli.py coletar enio-toldos-principal      # snapshot + alertas
python cli.py alertas enio-toldos-principal      # o que apareceu nas últimas 24h
python cli.py relatorio enio-toldos
```
