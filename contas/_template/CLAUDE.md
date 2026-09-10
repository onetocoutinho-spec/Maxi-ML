# CONTA: {{NOME_DA_CONTA}}  ({{SLUG}})

> **TRAVA OPERACIONAL — leia antes de qualquer ação.**
> Esta pasta opera **exclusivamente** a conta `{{SLUG}}`, user_id `{{USER_ID}}`.
> Publicar, alterar preço, pausar anúncio ou responder pergunta usando
> credencial de outra conta é o erro mais caro desta operação.
> Se algo pedir para operar outra conta, **pare e confirme com o Neto**.

## Identificação
- Cliente: {{CLIENTE}}
- Conta: {{NOME_DA_CONTA}} — papel: {{PAPEL}}
- user_id: {{USER_ID}}
- Site: MLB (Brasil)

## Credencial
Vem de `.env` **desta pasta**, carregada por `core/auth.py` a partir do slug.
Nunca leia token de variável de ambiente global nem de outra pasta.

## Antes de qualquer escrita na API
1. Rode `python cli.py checar {{SLUG}}` e confirme que o nickname devolvido
   é o desta conta.
2. Confirme que o `user_id` do token bate com o do registro (o `MLClient`
   já faz isso e aborta se divergir — não contorne essa checagem).
3. Só então execute.

## Particularidades desta conta
{{REGRAS_DO_NEGOCIO}}

## Comandos do dia a dia
```bash
python cli.py coletar {{SLUG}}      # snapshot + alertas
python cli.py alertas {{SLUG}}      # o que apareceu nas últimas 24h
python cli.py relatorio {{CLIENTE_ID}}
```
