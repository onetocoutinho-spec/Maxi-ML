# CONTA: EJPRIME  (`jb-moveis-ejprime`)

> **TRAVA OPERACIONAL.** Esta pasta opera **exclusivamente** o user_id
> `2245348587`. Antes de qualquer escrita: `python cli.py checar jb-moveis-ejprime` e
> confirme que o apelido devolvido é `EJPRIME`.

Conta **secundária** do cliente `jb-moveis` — "JB Móveis e Estofados".
Conectada em 08/09/2026. Retrato completo em
`dados/itens-origem-2026-09-08.json`.

## Esta conta NÃO é independente em preço

São quatro contas do mesmo dono, com `coordenar_preco: true` no
`clientes.yaml`. As três no ar dividem 43 fichas de catálogo entre si, 18 nas
três — **e isso é de propósito**: a operação escolhe qual variação entra em
qual ficha, porque cada uma rende diferente conforme a ficha.

**Nunca baixar preço aqui para vencer uma irmã.** Não é que a sobreposição seja
um defeito a corrigir — é que ganhar da irmã não traz venda nova, só reduz a
margem do grupo. Qual conta entra em qual ficha, e a que preço, é decisão da
operação, não do motor. Ver `contas/jb-moveis-principal/CLAUDE.md`.

## O estoque desta conta é fictício

Mediana perto de 10.000, máximo 99.999. Mesma prática da FACILITA e da
Decoralli. Não usar para "valor parado" e não copiar ao espelhar catálogo.
