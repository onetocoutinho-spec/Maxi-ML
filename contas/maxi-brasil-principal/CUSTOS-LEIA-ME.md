# Planilha de custo — como preencher

Salve o arquivo nesta pasta com o nome **`custos.csv`** (ou `custos.xlsx`).
Depois rode:

```
python cli.py precos SLUG_DA_CONTA
```

Ele mostra o que entendeu, o que casou com quais anúncios e o piso de preço de
cada um — **antes** de qualquer alerta usar esses números. Confira essa tela
antes de confiar na planilha.

## O mínimo

Duas colunas: uma que **identifique o anúncio** e uma de **custo**.

| coluna | aceita também | obrigatória |
|---|---|---|
| `item_id` | `MLB`, `anuncio`, `sku`, `codigo`, `titulo`, `produto` | sim |
| `custo` | `custo_unitario`, `preco_de_custo`, `cmv` | sim |
| `embalagem` | `custo_embalagem`, `caixa` | não |
| `frete` | `frete_proprio`, `custo_frete`, `logistica` | não |
| `imposto` | `imposto_percentual`, `tributos`, `aliquota` | não |
| `outros` | `custo_extra`, `adicional` | não |

Maiúscula, acento e espaço no cabeçalho não importam: `Custo Unitário` e
`custo_unitario` são lidos igual. Valor pode vir como `1.234,56`, `1234.56` ou
`R$ 89,90`. Imposto pode ser `8` ou `0,08`.

## Como cada linha encontra o anúncio

Nesta ordem: **MLB no texto** → **título idêntico** → **título parecido**.

O jeito seguro é pôr o MLB. Casamento por título existe para quando a planilha
vem do ERP do cliente, que não conhece MLB nenhum — funciona, mas é o que mais
erra. O que não casar aparece na tela como sobra, nunca é adivinhado.

## O que o sistema faz com isso

Calcula o **piso**: o menor preço que ainda entrega a margem mínima definida em
`conta.yaml`. E o **empate**: onde o lucro é zero.

```
piso = (custo + embalagem + outros + frete que você absorve)
       ÷ (1 − comissão − imposto − margem)
```

O frete só entra quando o anúncio é **frete grátis**, porque aí quem paga é
você. O valor vem da medição diária do frete real de cada anúncio; se não
houver medição, usa o que estiver na coluna `frete`.

A comissão sai de `conta.yaml`, por tipo de anúncio (clássico e premium têm
percentuais diferentes).

## O que muda nos alertas

Sem planilha, o alerta termina assim:

> SKYIFLEX está a R$ 1.369,07 (−29,2% vs. seus R$ 1.932,99)

Com planilha, ele termina resolvendo a dúvida:

> …**NÃO acompanhe: abaixo de R$ 1.535,62 você vende no prejuízo.**

ou

> …**Dá para acompanhar: seu piso é R$ 1.190,91.**

## Antes de confiar

`margem_minima_percentual` em `conta.yaml` precisa ser o número real do cliente.
Com ela zerada, o piso sai igual ao empate — e o sistema passa a dizer que dá
para acompanhar qualquer preço acima do custo, o que não é o que ninguém quer.
