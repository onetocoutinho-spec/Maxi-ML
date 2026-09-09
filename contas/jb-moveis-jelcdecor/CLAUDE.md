# CONTA: JELCDECOR  (`jb-moveis-jelcdecor`)

> **TRAVA OPERACIONAL.** Esta pasta opera **exclusivamente** o user_id
> `1627881723`. Antes de qualquer escrita: `python cli.py checar jb-moveis-jelcdecor` e
> confirme que o apelido devolvido é `JELCDECOR`.

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

## Verificação de restrição — 08/09/2026

**A conta não tem restrição.** Consultado `/users/me`:

    list.allow    true    codes: []        sell.allow     true   codes: []
    buy.allow     true    codes: []        billing.allow  true   codes: []
    site_status   active                   required_action  (vazio)
    immediate_payment  false               shopping_cart  buy/sell allowed
    nível  5_green   power_seller_status  PLATINUM

`mercadoenvios: not_accepted` aparece aqui como nas outras — e, como já está
provado no CLAUDE.md da Chinelaria, isso NÃO impede declarar me2 pela API.

### Mas há três anúncios marcados, e o motivo não sai pela API

    MLB7388499446  under_review / forbidden   R$   899,99  criado 11/08/2026
    MLB7388535224  under_review / forbidden   R$ 1.390,00  criado 11/08/2026
       ambos: "Poltrona Reclinável De Corino Com Apoio De Pernas, 1 Lugar"
       mesma categoria (MLB416807), mesmo dia, produto igual

    MLB5454152438  tag moderation_penalty     R$    79,90  criado 24/06/2025
       "Cadeira Monalisa Estofada Com Encosto Fixo Para Escritório"

`forbidden` é bloqueio do ML, não pausa do vendedor. Os dois serem o MESMO
produto, criados no MESMO dia, indica que o bloqueio é do produto ou do texto —
não incidente isolado de um anúncio.

**O motivo não é legível pela API com este app:** `/items/{id}/health` devolve
404 para `buy_it_now`, e `/moderations/infractions/search` devolve 401
(`unauthorized_request`) — falta escopo. O motivo aparece no painel do próprio
vendedor, em Anúncios ou em Publicações denunciadas. **Perguntar ao dono.**

### A reputação tem números feios no histórico, e bons nos últimos 60 dias

    historico:  8.607 transacoes | 7.442 concluidas | 1.165 CANCELADAS (13,5%)
                avaliacoes: 63% positiva | 12% neutra | 25% NEGATIVA
    60 dias  :  1.993 vendas | 14 reclamacoes (0,63%) | 0 cancelamentos
                61 envios atrasados (3,43%)

O 25% de negativa e os 13,5% de cancelamento são do acumulado histórico. O ML
classifica pela janela recente, e por ela a conta está **5_green e platinum** —
ou seja, pelo critério do próprio ML ela está saudável hoje.

**Não repetir esses percentuais históricos ao dono como se fossem o estado
atual.** O que merece olho é o atraso de envio: 61 casos em 60 dias é a única
métrica recente com volume.

## "Deixaram de ter envios" — o que a medição mostra (08/09/2026)

**Envio não parou.** Testado ao vivo: anúncio ativo com estoque devolve 2 a 3
opções de envio nas TRÊS contas, com custo R$ 0 para o comprador (frete grátis
obrigatório) e custo de lista de R$ 79 a R$ 148 para o vendedor.
`shipping_preferences` das três: `modes: [custom, not_specified, me2]`,
`trusted_user: true`. Nenhuma restrição de conta.

### Separando ATIVOS de PAUSADOS, que é o que confunde

    conta        grupo       n   flex_in  flex_out  flex_disp  sem_me2  perdeu_me2
    JELCDECOR    ATIVOS     16      3         1         1         0        0
    JELCDECOR    pausados   49      1        16        19         8        1
    EJPRIME      ATIVOS     12      3         0         0         0        0
    EJPRIME      pausados   95     67         0         4         4        0
    JB           ATIVOS     38      9         9         9         0        0
    JB           pausados  104      6        33        48        19        4

**Nenhum anúncio ATIVO está sem me2, nas três contas.** O que está fora de
envio é anúncio pausado — e anúncio pausado sai do Flex naturalmente.

A percepção de "perdemos envio" provavelmente vem do **Flex**, não do Mercado
Envios: na JELCDECOR só 3 dos 16 ativos estão no Flex, e na JB 9 de 38. A
EJPRIME é a exceção — mantém 67 pausados dentro do Flex, o que sugere que a
diferença é de configuração por conta, não de bloqueio.

### O que dá para consertar: 6 anúncios com `lost_me2_by_dimensions`

    JELCDECOR  MLB4435318301  caixa 62x81x87 cm, 33 kg   <- grande demais de verdade
    JB         MLB3692525640  SEM MEDIDA DE CAIXA
    JB         MLB3411912285  SEM MEDIDA
    JB         MLB3775333606  SEM MEDIDA
    JB         MLB3897007364  SEM MEDIDA
    JB         MLB7498579884  caixa 68x93x81 cm, 26,5 kg (ja fechado)

**Quatro dos seis perderam me2 só por não terem a medida da caixa** — é
exatamente a armadilha registrada no CLAUDE.md da Chinelaria: o ML aceita o me2
no POST e retira depois, carimbando `lost_me2_by_dimensions`. Declarar
`SELLER_PACKAGE_*` devolve o envio nesses quatro.

O de 62x81x87 cm e 33 kg está fora dos limites do Mercado Envios de verdade —
esse é frete próprio, não tem conserto por atributo.

### E os 8 sem me2 da JELCDECOR

Todos pausados, todos com caixa declarada enorme (62x81x87/33 kg,
67x78x92/24,8 kg). Não é falha de cadastro: é móvel que não cabe no Mercado
Envios. Modo `not_specified` neles está correto.

## Por que a linha de camas está pausada (apurado em 08/09/2026)

Não é cadastro, não é moderação, não é estoque. Todos os anúncios da linha
SOLTEIRO estão `paused_by_seller`, com estoque declarado de 9.900+ e histórico
de venda real.

**Os 47 anúncios pausados da JELC foram pausados em agosto e setembro de 2026 —
todos.** Nenhum antes disso. 35 em agosto, 12 em setembro. E não foi ação em
bloco: foi dia a dia (06, 12, 14, 17, 18, 20, 21, 22, 24, 25, 27, 28, 31).

Pausaram os campeões de venda:

| anúncio | SKU | vendas | pausado em |
|---|---|---|---|
| MLB6555789726 | SOLTEIROCOL_BEGE | **105** | 21/08 |
| MLB4785785395 | JUPOLTBENYMARROM | **85** | 06/08 |
| MLB4763503649 | SOLTEIROCOL_AZUL | **64** | 20/08 |
| MLB4763490881 | SOLTEIROCOL_ROSA | **59** | 20/08 |
| MLB4417205791 | JUPOLTGRAÇAPRET | **49** | 20/08 |
| MLB4763503647 | SOLTEIROCOL_BEGE | **41** | 21/08 |
| MLB4561685807 | SOLTEIROSC_AZUL | **38** | 20/08 |
| MLB6518929834 | SOLTEIROSC_BEGE | **34** | 17/08 |

A janela bate com a métrica da penalidade: `delayed_handling_time` = **61
atrasos, 3,42%, em 60 dias** (janela que cobre julho a setembro). A JB no mesmo
período: **0 atrasos, 0%**.

**Inferência (não confirmada pelo cliente):** pausaram para parar de gerar
pedido que não conseguiam despachar no prazo. É a reação racional a uma crise
de entrega — e explica por que os itens de maior giro saíram primeiro.

### O que isso implica para a migração

Se a causa foi incapacidade de despachar, **replicar essas camas na JB move o
problema para a conta limpa**. Camas de espuma são volumosas e é exatamente o
tipo de item que estoura logística. A JB tem 0 atraso em 1.611 vendas no
período, e é esse número que permite a ela ganhar catálogo no lugar da JELC.

Antes de subir qualquer cor nova de cama na JB, **perguntar ao cliente se o
gargalo de entrega foi resolvido**. O dado não responde isso — só ele responde.

Contraste importante: na JB os 94 pausados estão espalhados de fevereiro a
setembro (3, 15, 3, 14, 13, 6, 19, 21 por mês) — rotatividade normal. A
SOLTEIROSC_ROSA da JB foi pausada em 02/07, fora da onda. A pausa da JB não é
o mesmo evento.
