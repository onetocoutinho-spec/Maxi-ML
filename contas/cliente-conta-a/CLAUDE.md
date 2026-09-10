# CONTA: Conta A  (cliente-conta-a)

> **TRAVA OPERACIONAL — leia antes de qualquer ação.**
> Esta pasta opera **exclusivamente** a conta `cliente-conta-a`, user_id `SUBSTITUIR`.
> Publicar, alterar preço, pausar anúncio ou responder pergunta usando
> credencial de outra conta é o erro mais caro desta operação.
> Se algo pedir para operar outra conta, **pare e confirme com o Neto**.

## Identificação
- Cliente: cliente-tres-contas
- Conta: Conta A — papel: principal
- user_id: SUBSTITUIR
- Site: MLB (Brasil)

## Credencial
Vem de `.env` **desta pasta**, carregada por `core/auth.py` a partir do slug.
Nunca leia token de variável de ambiente global nem de outra pasta.

## Antes de qualquer escrita na API
1. Rode `python cli.py checar cliente-conta-a` e confirme que o nickname devolvido
   é o desta conta.
2. Confirme que o `user_id` do token bate com o do registro (o `MLClient`
   já faz isso e aborta se divergir — não contorne essa checagem).
3. Só então execute.

## Particularidades desta conta
_(preencher: modelo de anuncio, categoria, politica de preco)_

## Comandos do dia a dia
```bash
python cli.py coletar cliente-conta-a      # snapshot + alertas
python cli.py alertas cliente-conta-a      # o que apareceu nas últimas 24h
python cli.py relatorio cliente-tres-contas
```
