# Promoções da FACILITA — onde parou (02/09/2026, madrugada)

Escrito pela sessão Cowork para quem continuar daqui — inclusive o Claude Code
rodando nesta pasta. Aqui está tudo que já foi decidido e o que falta.

## Onde parou

**02/09/2026** — a rodada foi aplicada, conferida na vitrine, e a regra de
decisao foi corrigida. Em ordem do que importa:

### 1. O prejuizo foi estancado

`#6777799700` (POLTRONABENY-GRAFITE) vendia a R$ 569,99 pelo DEAL "9.9",
perdendo **R$ 47,11 por venda**. Saimos dessa promocao (`sair_da_promocao`,
DELETE 200). Passou a valer a SELLER_CAMPAIGN a **R$ 727,52**, margem 10,1%,
lucro R$ 73,40 — uma virada de R$ 120,51 por venda. Conferido na API e na
vitrine.

**Cuidado ao conferir**: a primeira leitura logo apos o DELETE ainda mostrava
o DEAL como `started`. So na segunda apareceu como `candidate`. O endpoint
demora alguns segundos para refletir — nao conclua pela leitura imediata.

### 2. A regra de decisao foi corrigida (a raiz das 40)

O script decidia olhando so proposta em `candidate`, cego para o que ja estava
valendo. Agora ele le tambem as `started`:

- **Nao afunda quando ja existe promocao ativa mais barata.** Descer o preco
  ali nao muda um centavo do que o comprador paga — so entrega margem. Nova
  decisao no CSV: `ENTRAR (sem afundar: ativa mais barata)`.
- **Avisa quando a ativa mais barata fura o piso**, com um bloco vermelho no
  fim da rodada. Esses casos nao se resolvem cadastrando: resolvem-se **saindo**
  de uma promocao, que e decisao humana.
- **Tres colunas novas no CSV**: `ativa_mais_barata`, `tipo_da_ativa`,
  `margem_da_ativa_pct` — a margem que vale de verdade.

A trava continua barrando so o que e inutil: no `#4309160515` a ativa mais
barata estava em R$ 671,99 e o alvo em R$ 645,16, entao afundar MUDA o preco
cobrado, e o script afundou normalmente.

## ALINHAMENTO DE PRECO ENTRE DERIVACOES (02/09/2026)

Pedido: "arruma os 31 SKUs com preco divergente". Nao foram os 31 — e a razao
importa mais que o numero.

### O dado que mudou a decisao

Antes de escrever, cruzei preco com `sold_quantity`. **Em 15 dos 30 SKUs
divergentes, o anuncio BARATO e o que vende, e o caro vendeu ZERO:**

| SKU | barato | caro |
|---|---|---|
| SOFACAMA-PRETO180 | R$ 1.429 — **13 vendas** | R$ 1.799 — 0 |
| SOFACAMA-CINZA180 | R$ 1.235 — **8 vendas** | R$ 1.527 — 0 |
| SOFAMILAO-CARAMELO140 | R$ 1.239 — **10 vendas** | R$ 1.390 — 0 |
| PUFFGRECIA-CINZA | R$ 708 — **5 vendas** | R$ 925 — 0 |

Alinhar para cima ali seria pegar o anuncio que carrega a venda e subir o preco
ate o de um irmao que ninguem compra. A leitura provavel: **o caro nao esta
caro por escolha, esta parado** — o preco que o mercado aceita e o do barato.

Ressalva do dado: `sold_quantity` e venda acumulada da vida do anuncio, nao dos
ultimos 30 dias. Anuncio novo aparece com zero sem estar morto.

Decidido em 02/09: alinhar **so onde o caro vende mais ou ninguem vendeu** — 14
SKUs.

### Feito: 12 precos em 10 SKUs

| anuncio | SKU | de | para | |
|---|---|---|---|---|
| #7295683762 | POLTRONABENY-PRETO | R$ 716,99 | R$ 899,00 | +25% |
| #4969935201 | POLTRONABENY-PRETO | R$ 771,99 | R$ 899,00 | +16% |
| #4719096939 | SOFABENY-CINZA180 | R$ 1.360,00 | R$ 1.699,00 | +25% |
| #6837942694 | POLTRONAEROS-CAFE | R$ 1.020,00 | R$ 1.199,90 | +18% |
| #6093665096 e #7575762246 | PUFFGRECIA-CAPUCCINO | R$ 760,00 | R$ 860,90 | +13% |
| #7266373954 | SOFACAMA-VERDE180 | R$ 1.526,99 | R$ 1.660,00 | +9% |
| #7266373958 | SOFACAMA-AZUL180 | R$ 1.526,99 | R$ 1.644,99 | +8% |
| #4701515641 | POLTRONAEROS-CARAMELO | R$ 960,00 | R$ 1.020,00 | +6% |
| #6777799700 | POLTRONABENY-GRAFITE | R$ 855,90 | R$ 889,00 | +4% |
| #6782525936 | POLTRONABENY-BEGE | R$ 883,90 | R$ 899,00 | +2% |
| #7044870930 | POLTRONABENY-CORINOPRETO | R$ 890,00 | R$ 899,99 | +1% |

Todos 200.

### REGRA DA CASA: quem diz qual e o produto e o SKU, nao o titulo

Definido pelo Neto em 02/09/2026, e vale para tudo neste repo.

Eu tinha pulado 4 SKUs achando que misturavam produtos diferentes, porque os
titulos discordavam: um anuncio de "Puff Sofa" carregando SKU de "Sofa Beny",
"Poltrona Elegance" com SKU de "Nuvem Confort". **Leitura errada minha.** No ML
o titulo e campo de palavra-chave — muda por anuncio para pegar busca — e o SKU
e a identidade do produto.

Consequencias diretas:

- Os 4 SKUs foram alinhados depois (+5 precos), completando os 14 autorizados.
- O `#5168161049`, que eu tinha marcado para possivel reversao por ser "Puff
  Sofa Organico" com SKU de Milao, **e um Sofa Milao**. Custo R$ 700 correto,
  saida da DEAL correta. **Nada a reverter.**
- **Nao usar divergencia de titulo como sinal de erro de cadastro.** Se o custo
  parecer errado, conferir o custo — nao o titulo.

### Os 15 onde o barato vende ficaram intocados

Nao e pendencia esquecida: e decisao. Subir o preco de quem carrega o
faturamento, para igualar a um irmao parado, e trocar venda por margem no
escuro. Se um dia quiserem mexer, o caminho e olhar venda RECENTE, nao
acumulada.

## O AJUSTE DE FRETE DO ML NAO SE SUSTENTA (02/09/2026)

O painel afirma, dentro de cada um dos seis anuncios do Sofa Yara 180:

> "Ajustamos o seu custo de envio apos medir e pesar seu pacote em nosso centro
> de distribuicao e confirmar o tamanho real."

**Isso nao pode ser verdade para estes anuncios.**

Varredura em TODOS os status (active 177, paused 55, closed 4): a linha
`SOFAYARA-*180` tem **zero vendas em toda a sua historia**, nos seis anuncios,
todos criados em **31/08/2026** — dois dias antes do ajuste. Nenhuma unidade
foi despachada, logo nao houve pacote medido no CD.

**Correcao de rumo registrada**: eu tratei o texto do painel como fato e
recomendei reverter a dimensao para 48 cm com base nele. A premissa era falsa.
Os 156x69x25 informados pelo Neto sao a unica medida real que existe sobre essa
caixa, e foram **reaplicados nos seis** (PUT 200, dimensao confirmada).

O frete segue R$ 221,78 — o ajuste do ML fica por cima do atributo do vendedor
e so cai por reclamacao.

### Texto da reclamacao (pronto para colar no "Preciso de ajuda")

> Anuncios #5163848249, #5163903435, #5163903437, #5163903439, #5163903441 e
> #7560420616 (variacoes do produto #7474350989963610), criados em 31/08/2026.
>
> O custo de envio foi alterado de R$ 67,88 para R$ 221,78 com a justificativa
> de que o pacote foi medido e pesado no centro de distribuicao.
>
> **Estes anuncios tem zero vendas desde a criacao.** Nenhuma unidade deste
> produto foi despachada, portanto nao houve pacote medido no CD. A medida real
> da embalagem e 156 x 69 x 25 cm.
>
> Solicito revisao do ajuste e do custo de envio.

A forca do argumento e que o ML confirma as duas coisas no sistema dele: data
de criacao e historico de vendas.

### Por que duplicar o anuncio nao resolve

Pedido duas vezes, recusado. O calculo do frete sai das MEDIDAS, nao do
anuncio: simulado, um anuncio novo em Pufes declarando 156x69x48 e 20 kg da os
mesmos R$ 221,78. O numero so cai se a medida declarada for menor que a caixa —
e a via legitima para isso e a reclamacao acima, nao um anuncio novo.

## TESTADO: mudar para Futon PIORA — nao fazer (02/09/2026)

A hipotese era que a categoria Pufes cobrava frete mais caro e mover para Futon
economizaria R$ 73,93 por venda. **Testado num anuncio, com reversao automatica.
Resultado: nao vale.**

| | categoria | Mercado Envios | frete gratis | custo |
|---|---|---|---|---|
| antes | Pufes | me2 | sim | R$ 221,78 |
| **em Futon** | Futon | **not_specified** | **NAO** | **R$ 279,90** |
| revertido | Pufes | me2 | sim | R$ 221,78 |

Na Futon o anuncio **perdeu o Mercado Envios na hora**, com a tag
`lost_me2_by_dimensions`, e o frete ficou MAIS caro. O aviso que veio junto do
primeiro 400 estava certo.

**A licao**: Futon e mais barata porque tem limite de tamanho MENOR. Uma caixa
de 156x69x48 nao cabe nela. Comparar tabela de frete entre categorias sem
checar o limite dimensional leva a conclusao errada.

Anuncio conferido depois da reversao: Pufes, me2, frete gratis, R$ 1.799 de
tabela, PRICE_DISCOUNT de R$ 1.320 intacta.

### O cadastro desses seis esta trocado

Descoberto no caminho. Os atributos descrevem outro produto:

| atributo | valor |
|---|---|
| MODEL | **"Pufe organico tipo sofisticado"** |
| POUF_TYPE | **"Luxo"** |
| SHAPE | **"Redonda"** |
| LENGTH | **72 m** (setenta e dois METROS) |

Titulo e SKU dizem Sofa Yara 180; os atributos dizem pufe redondo. Pela regra da
casa (o SKU manda), **os atributos e que estao errados**.

Corrigidos em 02/09 no `#5163848249`, com os dados do Neto: PRODUCT_TYPE Sofa,
SEATERS_NUMBER 2, IS_RECLINABLE Sim, REQUIRES_ASSEMBLY Sim,
INCLUDES_ASSEMBLY_MANUAL Sim, DEPTH 86 cm. **Faltam os outros cinco**, e
continuam pendentes em todos: MODEL, POUF_TYPE, SHAPE e o LENGTH de 72 m.

### RISCO ABERTO: os treze SOFAYARAFORNEC-140

Eles pagam so R$ 40,85 de frete porque declaram embalagem de **75 x 25 x 18 cm
e 2.827 g** — 2,8 kg para um sofa de 140. E o mesmo tipo de subdeclaracao que
fazia os 180 pagarem R$ 67,88 ate o ML pesar a caixa no CD e corrigir.

**Quando o ML medir um deles, o frete sobe igual.** Sao 13 anuncios apoiados
numa medida que ainda nao foi conferida. Avisar o Neto.

## O FRETE E DEFINIDO PELA CATEGORIA (02/09/2026)

Descoberta que fecha o caso do Sofa Yara 180 e vale para a conta inteira.

Simulando a MESMA caixa (90x82x73, 20 kg) em anuncios diferentes, o custo muda
so por causa da CATEGORIA — preco, tipo de anuncio e formato da caixa nao
importam:

| categoria | nome | frete |
|---|---|---|
| MLB31039 | **Pufes** | **R$ 221,78** |
| MLB1626 | **Sofas** | **R$ 221,78** |
| MLB186067 | Futon | R$ 147,85 |
| MLB458191 | Poltronas | R$ 147,85 |
| MLB416807 | Cadeiras de Balanco | R$ 147,85 |
| MLB439418 | Mesas para PC | R$ 147,85 |

Testes que descartaram as outras hipoteses:

- **Formato nao importa, so volume**: 156x69x48, 130x80x50, 110x90x52, 90x90x64
  e 82x88x72 — todos ~516.000 cm3 — deram exatamente R$ 221,78.
- **Preco nao importa**: R$ 467,60 em Mesas para PC paga R$ 147,85; R$ 799,00
  em Pufes paga R$ 221,78.

### O erro concreto

Os seis `SOFAYARA-*180` sao **Sofa Cama** cadastrados em **Pufes**. Os irmaos de
140 cm da MESMA linha (`SOFAYARAFORNEC-*140`, 13 anuncios) estao em **Futon**.
Mesmo produto, categorias diferentes, R$ 73,93 de diferenca por venda.

**Mover os seis de Pufes para Futon vale R$ 443,58 por rodada** — mais que os
R$ 325,80 da caixa (que nao funcionou) e mais que os R$ 190,83 do aumento de
preco. E e correcao, nao truque: sofa-cama nao e pufe.

Conferido o resto da categoria Pufes: dos 46 anuncios, 39 tem "puff/pufe" no
nome e estao certos. So os 6 sofa-cama estao errados (e possivelmente o
`#6756161546`, "Sofa Estofado Moderno").

**Nao precisa duplicar anuncio.** A categoria e o caminho legitimo.

### Bloqueado

O PUT de `category_id` foi negado pelo classificador de permissoes do Claude
Code. Precisa de liberacao do usuario para seguir.

### Pendencia: a dimensao 25 cm

O painel do ML diz, dentro do anuncio: *"Ajustamos o seu custo de envio apos
medir e pesar seu pacote em nosso centro de distribuicao e confirmar o tamanho
real."* Ou seja, os 156x69x48 sao **medicao fisica do ML**, nao chute de
cadastro.

Foi aplicado 156x69x25 nos seis a pedido do Neto. Isso contradiz a medicao do
ML — que aliais ignorou a alteracao e manteve o frete. **Avaliar reverter para
48 cm**: declarar contra medicao fisica e risco de cobranca retroativa.

## SOFA YARA 180 — o frete, o preco e a caixa (02/09/2026)

Seis anuncios, mesmo produto em seis cores: "Sofa Cama Capitonet Suede Madeira
Eucalipto", SKU `SOFAYARA-*180`. Preco de tabela R$ 1.799 nos seis, estoque
10.000, **zero vendas em todos**.

### O que aconteceu com o frete

Entre 09:55 e 11:07 o frete deles saltou de **R$ 67,88 para R$ 221,78**,
derrubando a margem de 15% para 2,7%. Nao foi acao nossa.

Investigado: **os R$ 67,88 nunca foram reais.** Simulando no endpoint do ML
(`/users/{user}/shipping_options/free?item_id=X&dimensions=HxWxL,peso`), um
pacote so custa R$ 67,88 quando pesa 5 a 6 kg. Um sofa-cama 180 nao pesa isso.
O cadastro tinha medida ou peso muito menores que o produto, e hoje isso foi
corrigido — pelo ML ou por alguem.

**Consequencia dura: esses seis nunca estiveram a 15%. Estavam a 2,7% o tempo
todo, e o zion-ml vinha calculando margem deles com dado falso desde sempre.**

### A tabela de frete do ML, medida

O custo e `max(peso real, peso cubado)`, cubado = HxWxL/6000. Medido no
proprio anuncio:

| caixa (peso 20 kg) | cubado | frete |
|---|---|---|
| 156x69x48 | 86 kg | R$ 221,78 |
| 156x69x30 | 54 kg | R$ 178,58 |
| 156x69x25 | 45 kg | R$ 167,48 |
| 156x69x20 | 36 kg | R$ 161,93 |
| 80x50x30 | 20 kg | **R$ 137,93 (piso)** |

Abaixo de 20 kg cubado o peso REAL assume e encolher mais nao adianta: uma
caixa de 20x20x15 custa igual a uma de 60x50x40.

### Preco: o teto de credibilidade do ML

Tentado subir a PRICE_DISCOUNT para R$ 1.375,92 (o valor de 10% de margem).
**Recusado**: `ERROR_CREDIBILITY_DISCOUNTED_PRICE`. O ML nao aceita desconto
que nao seja crivel contra o preco recente REAL do anuncio.

Descobertas do teste, que valem para qualquer aumento de promocao:

- **Nao da para alterar promocao ativa por cima** — POST devolve "No candidates
  found". Tem que SAIR e REENTRAR.
- **O teto e por anuncio, nao da conta.** R$ 1.320 passou em dois e foi recusado
  em quatro, mesmo produto e mesmo preco de tabela.
- **Sair e reentrar NAO e atomico.** Quatro anuncios ficaram alguns minutos sem
  promocao, valendo os R$ 1.799 cheios, porque a reentrada falhou. Restaurados
  na mesma operacao, mas houve janela real.
- **Descobrir o teto ANTES de sair** e o jeito certo — testar num irmao.

Resultado: R$ 1.320 / 1.310 / 1.290 / 1.270 / 1.259,99 conforme o teto de cada
um. Lucro por rodada dos seis: **R$ 239,03 -> R$ 429,86**. Nenhum chegou ao piso.

O teto sobe com o preco recente, entao da para subir em degraus ao longo de
dias. **A janela do PRICE_DISCOUNT expira em 09/09.**

### A caixa foi corrigida para 156x69x25

Medida real informada pelo Neto em 02/09. Aplicada nos seis
(`SELLER_PACKAGE_LENGTH`, PUT 200 em todos, dimensao confirmada na leitura).

**O frete ainda le R$ 221,78** — o calculo do ML nao reprocessou. O
`billable_weight` segue 86.112, que e a conta de 48 cm. A simulacao com
`dimensions=156x69x25` devolve R$ 167,48, entao o motor concorda; falta o
anuncio ser reindexado. `shipping.dimensions` nao e editavel (400, cause 240) —
o caminho e mesmo o atributo.

**Conferir depois.** Se cair para R$ 167,48, sao R$ 54,30 por venda em cada um,
**R$ 325,80 por rodada**, e tres dos seis passam do piso sem tocar em preco.

## AS 5 TROCAS DE REBATE, FEITAS (02/09/2026)

Executadas com reconferencia no momento da escrita — nao pelo CSV de minutos
antes, porque proposta do ML muda entre chamadas.

| anuncio | preco | saiu de | ficou com | ganho/venda |
|---|---|---|---|---|
| #7191818798 SOFAYARAFORNEC-CINZA140 | R$ 1.003,94 | DEAL (R$ 127,36) | SMART (R$ 160,79) | **+R$ 33,42** |
| #5163319305 SOFAYARAFORNEC-GRAFITE140 | R$ 1.003,94 | DEAL (R$ 127,36) | SMART (R$ 160,79) | **+R$ 33,42** |
| #6808480140 SOFACAMA-AZULTURQUESA180 | R$ 1.141,68 | DEAL (R$ 132,72) | SMART (R$ 146,88) | +R$ 14,16 |
| #4875060891 POLTRONAMONA-CINZA | R$ 539,09 | DEAL (R$ 54,00) | SMART (R$ 67,71) | +R$ 13,71 |
| #4382913497 PUFFGRECIA-CINZA | R$ 567,44 | SMART (R$ 57,40) | SMART (R$ 60,94) | +R$ 3,54 |

**R$ 98,25 por rodada de vendas, sem o comprador pagar um centavo a mais.**
Todas 200, todas conferidas na API com leitura espacada.

Cuidado na conferencia do #4382913497: a troca foi SMART -> SMART, entao
checar por tipo e preco nao distingue as duas. So o `id` resolve — a que ficou
e a `P-MLB17829062` ("TUDO pra Casa"), e a `P-MLB17829058` ("Casa e Decor em
Oferta") voltou a `candidate`.

Quatro das cinco sairam da DEAL "9.9", entao esses anuncios perderam a vitrine
daquela campanha. O ganho de margem esta medido; o custo em exposicao, nao —
vale olhar o giro desses quatro nos proximos dias.

## FAXINA DE 02/09/2026 — o resultado

Executado a pedido do Neto ("as que estiverem abaixo, suba"), depois de
analisar caso a caso.

### O que foi feito

- **11 saidas de promocao**, todas 200. Sao as que a analise mostrou que
  resolvem: sair da campanha mais barata deixa outra valendo, acima do piso.
- **4 precos alterados**, todos 200:
  - SOFANUVEM CINZA e BEGE: R$ 800 -> **R$ 1.055** (eram os dois no prejuizo)
  - SOFAMILAO-PRETO180 x2: R$ 1.000 -> **R$ 1.500**

### O resultado

| | antes | depois |
|---|---|---|
| vendendo no prejuizo | 2 | **0** |
| abaixo do piso | 16 | **3** |
| dentro da faixa | 116 | 121 |
| acima do teto | 41 | 51 |
| lucro por rodada de vendas | R$ 20.910,51 | **R$ 25.548,97** |

Sobraram 3 abaixo do piso, exatamente os que a analise previu que NAO se
resolvem saindo: `#4695944189` (2,4%) e os dois `SOFABENY-BEGE180` (9,1%).
Nesses, sair deixa uma promocao ainda pior valendo. Precisam de segunda saida
ou de repreco.

### ERRO DE RACIOCINIO MEU, registrado

O SKU `SOFAMILAO-PRETO180` esta em **tres anuncios que sao produtos
diferentes**: dois "Sofa Beny 180cm" e um "Puff Sofa Organico". Aliniei os dois
de R$ 1.000 ao "irmao mais caro" — que nao e irmao.

O preco final ficou defensavel por coincidencia: R$ 1.500 para um Sofa Beny 180
bate com os outros Beny 180 da conta (R$ 1.499). Mas a logica estava errada.

Pior: no `#5168161049` (o "Puff Sofa Organico" com SKU de Milao) sai da DEAL
usando custo R$ 700, que e o custo do Milao. Se ele e mesmo um puff, o custo e
da ordem de R$ 340, ele ja era lucrativo a R$ 1.425, e a saida subiu o preco
sem necessidade. **Reversivel voltando a DEAL** — falta o Neto confirmar o
produto.

**A raiz**: custo e casado por SKU. SKU errado = custo errado = margem errada
em tudo (promocao, revisao, alerta). Nao corrigir SKU por conta propria: e
cadastro do cliente e exige saber qual produto e qual.

### PDF de produtos e derivacoes

`scripts/relatorio_produtos_pdf.py` gera um PDF agrupado por SKU com cada
derivacao, o tipo de anuncio (Classico/Premium, que muda a tarifa), preco de
tabela, preco valendo, campanha e margem — vermelho no prejuizo, ambar abaixo
do piso. Traz tambem a lista de SKUs com preco divergente entre derivacoes e os
anuncios sem SKU.

```bash
python scripts/relatorio_produtos_pdf.py facilita-brasil-principal
```

Numeros de 02/09: 176 anuncios, 73 SKUs, 103 Classico e 73 Premium, e **31 SKUs
com preco divergente entre derivacoes** — a canibalizacao que ainda nao foi
tratada.

## O "PREJUIZO" NAO EXISTIA — bug do frete (02/09/2026)

Pedido: "arruma o frete do #6717022002". Ao abrir o anuncio, o frete nao estava
quebrado — **a nossa conta estava**.

```
"free_shipping": false, "mode": "not_specified", "methods": [],
"tags": ["lost_me2_by_dimensions"]
```

O anuncio **nao oferece frete gratis**. Quem paga o envio e o comprador. Mas os
scripts chamavam `custo_do_frete_gratis()` — que responde quanto CUSTARIA o
frete gratis — e subtraiam esse valor sempre, oferecendo ou nao.

| | margem calculada | margem real |
|---|---|---|
| #6717022002 SOFACAMA-CINZA180 | -9,75% | **+21,0%** |
| #7534274634 SOFACAMA-BEGE180 | 4,25% | **21,3%** |
| #4719690011 SOFACAMA-BEGE180 | 4,25% | **21,3%** |
| #7574144860 SOFACAMA-BEGE180 | 12,0% | **26,2%** |
| #5174192987 SOFACAMA-BEGE180 | 12,0% | **26,2%** |

Cinco anuncios, **R$ 1.223,50 de custo inventado por rodada**. Todos sofa-cama,
todos com a tag `lost_me2_by_dimensions`.

**A FACILITA nao tem nenhum anuncio vendendo no prejuizo.** O unico da lista
era erro nosso, e ele apareceu em tudo que este documento registrou hoje.

### Corrigido

Em `cadastrar_promos.py` e `revisar_promos.py`: o frete so e descontado quando
`shipping.free_shipping` e verdadeiro. **`free_shipping` ausente NAO vira
zero** — nesse caso continua perguntando e descontando. Errar para mais custo
deixa promocao boa de fora; errar para menos cadastra promocao ruim, que e o
erro caro.

### O que ESTA errado no frete desse anuncio

A tag `lost_me2_by_dimensions` e real: o anuncio perdeu o Mercado Envios por
tamanho. Embalagem declarada 191 x 123 x 34 cm, 43,3 kg reais, mas **133 kg de
peso cubado** (191x123x34/6000). Por isso o frete gratis custaria R$ 379,90 e
por isso ele saiu da logistica do ML — hoje e "Combine a entrega".

**Nao mexer nas dimensoes para baratear frete.** Elas conferem com um sofa-cama
de 180 embalado; reduzir no cadastro seria declarar medida falsa, e o problema
reaparece na coleta. Se houver o que resolver, e de produto — embalagem menor,
envio desmontado — nao de cadastro.

## REVISAO DO QUE ESTA NO AR — `scripts/revisar_promos.py` (02/09/2026)

Script novo, SOMENTE LEITURA. Existe porque o `cadastrar_promos` decide sobre
PROPOSTAS: ele varre as `candidate` e pula o anuncio que nao tem nenhuma —
antes mesmo de apurar custo e frete. Anuncio totalmente aderido fica invisivel,
e foi assim que o `#6717022002` vendeu no prejuizo por duas rodadas sem
aparecer em nada.

A revisao olha TODO anuncio ativo e responde outra pergunta: **qual a margem do
preco que esta valendo hoje**, que e o da promocao ativa mais barata.

### Retrato da FACILITA em 02/09/2026 (ja com o frete corrigido)

163 anuncios com promocao ativa, somando **R$ 20.910,51 de lucro por rodada de
vendas**:

| estado | anuncios |
|---|---|
| dentro da faixa 10–15% | **113** |
| acima do teto | 36 |
| abaixo do piso | **14** |
| vendendo no prejuizo | **0** |
| sem promocao ativa | 12 |
| sem custo na tabela | 1 |

**Nenhum anuncio no prejuizo.** Os 14 magros deixam R$ 805,11 por rodada; no
piso de 10% deixariam R$ 1.094,11 — **R$ 289,00 por rodada** e a conta do que
esta sendo vendido barato demais.

A primeira passagem, ANTES da correcao do frete, dizia 1 prejuizo, 16 abaixo do
piso e R$ 19.687,01 de lucro. Fica registrado so para quem tiver visto o
relatorio antigo nao se confundir.

**Os 31 acima do teto** tem margem media de 16,7%, maior 27,7%. Nao e problema:
e onde ainda cabe desconto se a vitrine pedir.

### Um numero que explica muita coisa

**145 dos 163 anuncios tem mais de uma promocao ativa ao mesmo tempo** — 11
deles com CINCO. Distribuicao: 18 com uma so, 68 com duas, 52 com tres, 14 com
quatro, 11 com cinco.

Como quem manda no preco cobrado e a mais barata, isso quer dizer que a maior
parte da conta e governada por uma campanha que ninguem escolheu de proposito.
E a razao de fundo de quase tudo que este documento registra.

### O prejuizo que continua

`#6717022002` (SOFACAMA-CINZA180) — **-9,8%, R$ 120,38 de perda por venda**.
Preco R$ 1.234,99, custo R$ 747,00, **frete gratis R$ 379,90**, taxa 11,5%,
imposto 7%. Nao e problema de promocao: e o preco de tabela que nao cobre o
frete. Sair de promocao nao resolve — precisa reprecificar ou tirar o frete
gratis.

### Como rodar

```bash
python scripts/revisar_promos.py facilita-brasil-principal --csv
```

`--limite N` para amostra, `--piso`/`--teto` para outra faixa. Nao escreve nada.

## REGRA NOVA: comparar com as JA ATIVAS e preferir rebate (02/09/2026)

Pedido do Neto, com o criterio dito assim: **"melhor cenario seria cliente
pagar menos e nos receber mais"**. Duas mudancas em `escolher` e na decisao.

### 1. A ativa DOMINA — nao entra

Se uma promocao ja ativa entrega **preco menor ou igual E dinheiro maior ou
igual**, entrar na candidata nao compra nada: o comprador nao paga menos e o
vendedor nao recebe mais. Pior, ainda arrisca a venda ser creditada na campanha
de rebate menor. Nova decisao no CSV: `RECUSAR (ativa domina)`, com a coluna
`observacao_ativa` dizendo qual promocao dominou e quanto ela deixa.

O caso que ensinou: `#7191463116`. Entramos numa PRICE_DISCOUNT a R$ 964,17
enquanto uma SMART, **no mesmo preco**, rendia 13,7% contra 9,8% — porque a
SMART vem com rebate do ML. Quatro pontos de margem entregues sem o comprador
ganhar nada.

Testado em 25 anuncios: **6 adesoes bloqueadas**, todas duplicatas de verdade
(mesmo preco, mesmo lucro, diferenca de centavos). Exemplo: `#4461784537`,
onde entrariamos numa PRICE_DISCOUNT a R$ 1.357,55 deixando R$ 308,65 com uma
SELLER_CAMPAIGN ja ativa no MESMO preco e MESMO lucro.

E ela **nao** bloqueia o caso bom: no `#6717142616` a adesao passou, porque a
nossa SMART deixa mais dinheiro que a ativa de preco igual. Preco igual para o
comprador, mais no bolso do cliente — exatamente o cenario pedido.

### 2. Empatou o lucro, ganha o MENOR PRECO

O desempate de `escolher` era: dinheiro por venda, campanha de verdade, e durar
mais. **Preco nao estava na lista** — entao, empatado o dinheiro, a escolha
entre uma a R$ 900 e outra a R$ 850 era arbitraria.

Duas campanhas deixam o mesmo por venda em precos diferentes quando o rebate do
ML cobre a diferenca. Empatado o que entra no bolso, o melhor negocio e o
comprador pagar menos: anuncio mais competitivo pelo mesmo resultado, e quem
paga a diferenca e o ML. Agora o menor preco e o primeiro desempate.

### 3. Bloco "Troca sem custo para o comprador"

Acrescentado logo depois. Entre as promocoes JA ATIVAS de um anuncio, quem
manda no preco cobrado e a mais barata. Se existe outra ATIVA **no mesmo
preco** que deixa mais dinheiro — porque tem rebate do ML e a outra nao — entao
sair da pior e ganho puro: **o comprador paga exatamente o mesmo e o vendedor
recebe mais.**

O script NAO sai sozinho: sair muda preco publico e e decisao humana. Ele lista
o caso no fim da rodada, como ja faz com o piso furado, dizendo de qual sair,
com qual ficar e quanto se ganha por venda.

Primeiro teste, 30 anuncios: 1 caso — `#4382913497` (PUFFGRECIA-CINZA), duas
SMART no mesmo R$ 567,44, uma deixando R$ 57,40 e a outra R$ 60,94. R$ 3,54 por
venda de graca.

**Limite conhecido, impresso junto do bloco**: so enxerga anuncios que ainda
tem alguma proposta candidata. Os totalmente aderidos nao passam pelo trecho do
codigo que apura custo e frete, entao ficam invisiveis — o mesmo buraco que o
aviso de piso teve na primeira versao. Fechar isso exige apurar custo e frete
tambem para quem nao tem candidata (~28 anuncios a mais na FACILITA).

## SAIDA DOS 4 ABAIXO DO PISO (02/09/2026)

Executada depois de conferir, um a um, o que passaria a valer — sair as cegas
pode deixar uma promocao ainda mais barata no comando.

| anuncio | SKU | antes | agora | |
|---|---|---|---|---|
| #6936131300 | SOFACAMA-TERRACOTA180 | 8,5% | **10,9%** | resolvido |
| #4936908031 | SOFACAMA-AZUL180 | 9,7% | **12,0%** | resolvido |
| #7191463116 | SOFAYARAFORNEC-BEGE140 | 9,8% | **13,7%** | resolvido |
| #4695269193 | POLTRONAEROS-CARAMELO | 7,0% | 8,0% | **ainda abaixo do piso** |

O caso do #7191463116 vale entender: nossa PRICE_DISCOUNT e a SMART estavam no
MESMO preco (R$ 964,17), mas a SMART rende 13,7% contra 9,8% — porque ela vem
com rebate do ML. **Mesmo preco para o comprador, 4 pontos a mais de margem.**
Quando duas promocoes empatam em preco, a que tem rebate e sempre melhor, e o
script hoje nao olha isso.

### #4695269193 — resolvido com uma SEGUNDA saida

Sair da nossa DEAL nao bastou: quem passou a mandar foi uma SMART a R$ 861,99
(8,0%), que nao era nossa. Saimos tambem dela em 02/09. Estado final:

| | |
|---|---|
| manda agora | PRICE_DISCOUNT R$ 927,99 |
| lucro | R$ 110,86 |
| margem | **11,9%** |

Preco subiu R$ 66 contra os R$ 861,99 anteriores. **Os quatro estao acima do
piso.**

### BUG ENCONTRADO: `sair_da_promocao` tambem precisava de `offer_id`

Das quatro saidas, duas voltaram **400 "Offer id is required"** — as duas SMART.
Mesmo defeito que o POST tinha, e que eu havia corrigido so na adesao: SMART e
PRICE_MATCHING exigem `offer_id` (o `ref_id`, que nas ja ativas vem como
`OFFER-…`). DEAL e PRICE_DISCOUNT saem sem ele.

Corrigido em `core/ml_api.py::sair_da_promocao`, que agora aceita `offer_id` e
omite `promotion_id` no PRICE_DISCOUNT. As duas saidas foram refeitas e deram
200.

**O perigo desse bug**: o DELETE falha e o anuncio CONTINUA na campanha. Quem
olhasse so o resumo poderia dar a saida como feita.

### A leitura velha e PIOR do que parecia

Ja tinha acontecido no #6777799700 e no #4936908031: a conferencia logo apos o
DELETE mostrava a promocao ainda ativa, e a segunda leitura corrigia.

No #4695269193 **duas leituras seguidas** ainda mostravam `started`, com o
mesmo `id` e o mesmo `ref_id` — dava para jurar que o DELETE nao pegou. So com
leituras espacadas (10s, 20s) apareceu `candidate`.

Regra pratica: **depois de um DELETE, so concluir que falhou apos esperar e
reler.** Duas leituras rapidas nao bastam. E o inverso do erro classico deste
documento: aqui o log estava certo e a leitura e que mentia.

## BUG DA TARIFA — encontrado, corrigido, estrago medido (02/09/2026)

### A tarifa do ML tem um DEGRAU em R$ 700

Medido no `/sites/MLB/listing_prices`, mesmo ponto nas categorias MLB458191,
MLB186067 e MLB31039 — ou seja, **regra do site, nao da categoria**:

| tipo | abaixo de R$ 700 | a partir de R$ 700 |
|---|---|---|
| Classico (`gold_special`) | 10,5% | **11,5%** |
| Premium (`gold_pro`) | 13,5% | **16,5%** |

No Premium o salto e de **3 pontos**.

### O bug

`tarifa()` guardava o percentual em cache por `(categoria, tipo)`, com o
comentario "a tarifa do ML e linear no preco". Nao e. A primeira consulta de
uma categoria fixava o percentual para TODOS os precos daquela categoria na
rodada inteira. Se o primeiro anuncio era barato, os caros herdavam a taxa
menor — e a margem saia **inflada**, que e o erro perigoso.

Foi assim que o `#4701515641` apareceu com tarifa R$ 81,85 onde a Central de
Promocoes mostrava R$ 89,65. **Corrigido**: o cache agora e chaveado por
`(categoria, tipo, preco)`. Custa mais chamadas, mas preco repetido — o mesmo
SKU em varios anuncios — continua batendo no cache.

Isso derruba a nota que estava aqui e no docstring do script dizendo que a
conta "erra sempre para MENOS margem" e "nunca cadastra promocao ruim por causa
disso". Errava para mais em 48 das 115 adesoes.

### Estrago na rodada de 07:20

Recalculadas as 115 adesoes com a tarifa certa:

| | |
|---|---|
| tarifa ja estava correta | 60 |
| margem CAI | **48** |
| margem sobe | 7 |
| passa a furar o piso de 10% | **4** |
| em prejuizo | 0 |

Os quatro abaixo do piso:

| anuncio | SKU | registrado | real |
|---|---|---|---|
| #4695269193 | POLTRONAEROS-CARAMELO | 10,00% | **7,00%** |
| #6936131300 | SOFACAMA-TERRACOTA180 | 11,49% | **8,49%** |
| #4936908031 | SOFACAMA-AZUL180 | 10,66% | **9,66%** |
| #7191463116 | SOFAYARAFORNEC-BEGE140 | 10,85% | **9,85%** |

**E tem um efeito silencioso maior**: varias adesoes marcadas como afundadas
"ate o teto de 15%" estao na verdade em **12%** — o alvo foi calculado com a
tarifa errada. Nao fura piso, mas significa que entregamos mais desconto do que
a regra mandava. A proxima rodada ja calcula certo.

### CONFERIDO NA CENTRAL DE PROMOCOES (02/09/2026)

Aberta em vendedores.mercadolivre.com.br/anuncios/lista/promos, com a sessao
do vendedor. 104 anuncios na lista, 5 paginas. O que a tela resolveu:

**1. O frete esta CERTO — e era o risco mais caro.** A tela abre "Voce recebe"
com a conta detalhada, e o "Custo de envio do Mercado Livre" bateu exatamente
com o que o script apurou:

| anuncio | frete na tela | frete do script |
|---|---|---|
| #4701515641 | R$ 70,95 | R$ 70,95 |
| #6808480140 | R$ 50,75 | R$ 50,75 |

Frete inventado e o que cadastra promocao no prejuizo. Nao e o caso.

**2. A TARIFA esta 1 ponto BAIXA — e isso INFLA a margem.** A tela mostra
"Tarifa de venda / Classico" em seis leituras dos dois anuncios, e a cheia da
sempre **11,5%**. O `tarifa()` deste script mediu **10,5%** nos dois:

| anuncio | preco | tarifa da tela | tarifa medida | diferenca |
|---|---|---|---|---|
| #6808480140 | R$ 1.141,68 | R$ 131,29 (11,5%) | R$ 119,88 (10,5%) | -R$ 11,41 |
| #4701515641 | R$ 779,54 | R$ 89,65 cheia (11,5%) | R$ 81,85 (10,5%) | -R$ 7,80 |

**Isto contradiz o que estava escrito aqui e no docstring do script**: a nota
dizia que a conta erra sempre para MENOS margem, deixando de fora promocao boa,
e "nunca cadastra promocao ruim por causa disso". Nestes dois casos erra para
MAIS margem. A conta soma o rebate por fora assumindo tarifa CHEIA — se a
tarifa usada ja vem abaixo da cheia, parte do desconto e contada duas vezes.

Alcance na rodada de 07:20: **35 das 115 adesoes** foram medidas a 10,5%. A
media delas e 16,2%, entao a maioria tem folga. Mas **tres ficam abaixo do
piso** se a tarifa real for 11,5%:

| anuncio | SKU | margem registrada | com 11,5% |
|---|---|---|---|
| #4875060891 | POLTRONAMONA-CINZA | 10,02% | ~9,0% |
| #4936908031 | SOFACAMA-AZUL180 | 10,66% | ~9,7% |
| #7191463116 | SOFAYARAFORNEC-BEGE140 | 10,85% | ~9,9% |

**Ressalva honesta**: a divergencia foi medida em DOIS anuncios, os unicos da
tela que abriram a conta detalhada com preco igual ao nosso. Nao esta provado
que os 35 tem o mesmo desvio. Antes de mexer na formula, confirmar em mais
anuncios — a tela e a fonte, o `listing_prices` e quem esta em duvida.

**3. Falso alarme conferido.** A tela diz que o #5166746541 (SOFACAMA-PRETO180)
"nao e elegivel para promocoes", mas nossas tres adesoes com esse SKU foram nos
anuncios #4461784537, #6717142616 e #5174182313. SKU repetido em anuncios
diferentes; nao ha contradicao com o log.

**4. "PRECO ALTO" em varios.** Era esperado: entramos em precos que protegem a
margem, e o ML rotula assim tudo que esta acima do desconto que ele queria. O
mesmo painel que rotula "PRECO ALTO" tambem escreve "Desconto atrativo,
continue assim" na promocao de 10,6% de margem. O rotulo e do ML, o piso e
nosso.

### 3. Segunda rodada aplicada, ja com a logica nova (02/09 07:20)

309 propostas, 119 adesoes tentadas: **115 OK, 4 erros**.

| tipo | adesoes |
|---|---|
| SELLER_CAMPAIGN | 48 |
| PRICE_DISCOUNT | 35 |
| SMART | 21 |
| DEAL | 11 |

Decisoes: 72 `ENTRAR`, **26 `ENTRAR (sem afundar: ativa mais barata)`** — a
trava nova em acao — e 21 `ENTRAR (afundado)`, onde afundar muda mesmo o preco.

Os 4 erros, todos ja conhecidos e nenhum exigindo acao:

- **3x `No candidates found for item`** — o anuncio JA tinha aquele tipo ativo,
  por sincronia entre anuncios irmaos ou de antes. Conferido um a um:
  `#4709252151` esta com o preco pretendido (R$ 575,99) valendo por um DEAL;
  `#5174192987` esta com o PRICE_DISCOUNT a R$ 1.485,12; `#5171648627` ja tinha
  PRICE_DISCOUNT ativo a R$ 964,17, margem sadia. Nada a refazer.
- **1x `ERROR_CREDIBILITY_DISCOUNTED_PRICE`** (`#5163903439`) — trava
  anti-desconto-falso do ML, que nao aceita desconto tao fundo contra o preco
  cheio recente. Regra do ML; reenviar igual nao adianta.

**Atencao a volatilidade**: a simulacao das 07:11 previa 6 afundados e a
aplicacao das 07:20 fez 21. Mesma conta, nove minutos, nenhuma escrita entre
as duas. E o mesmo efeito ja documentado na secao da previa — as propostas do
ML mudam entre chamadas. A trava de margem seguiu valendo nas duas.

### 4. O aviso na conta inteira

Disparou no fim da rodada: **11 anuncios com a promocao ativa mais barata
furando o piso, 1 no prejuizo** (`#6717022002`, tratado na secao abaixo).

### 3. O aviso novo, validado na conta inteira

Simulacao completa de 02/09 07:11 (nao escreveu nada). O bloco vermelho
disparou, e os numeros da trava:

| | |
|---|---|
| `ENTRAR (sem afundar: ativa mais barata)` | **38** |
| `ENTRAR (afundado)` — onde afundar muda mesmo o preco | 6 |
| lucro por venda preservado pelas 38 | **R$ 2.598,73** |

Antes, essas 38 teriam afundado ate 15% sem mudar um centavo do que o
comprador paga.

**Furo corrigido no proprio aviso.** A primeira versao so olhava linhas
`ENTRAR` e mostrava 7 anuncios. Mas vender magro e propriedade do ANUNCIO, nao
da nossa decisao: um anuncio que RECUSAMOS pode estar vendendo abaixo do piso
por promocao que ja estava ativa. Sem o filtro de decisao, sao **15**.

### 4. SEGUNDO PREJUIZO — e nao e problema de promocao

`#6717022002` (SOFACAMA-CINZA180) so apareceu por causa da correcao acima: a
decisao dele era RECUSAR, entao a versao anterior do aviso o engolia.

| | |
|---|---|
| preco de cadastro | R$ 1.234,99 |
| PRICE_DISCOUNT ativa | R$ 1.234,99 — **o mesmo preco** |
| custo | R$ 747,00 |
| frete gratis | **R$ 379,90** |
| taxa + imposto | 17,5% |
| resultado | **-R$ 108,03 por venda (-8,7%)** |

**Sair da promocao nao resolve**: ela esta no mesmo preco do cadastro, entao
sair nao muda nada. Este anuncio perde dinheiro no proprio preco de tabela, e
quem come a margem e o frete gratis de R$ 379,90 — quase o dobro dos R$ 191
que este documento ja registrava como pior caso em estofado.

O conserto e outro: **subir o preco ou tirar o frete gratis**. Decisao do Neto.

Fica a licao: o aviso da margem da ativa pega DOIS problemas diferentes, e
cada um tem cura diferente. Promocao mais barata furando o piso resolve-se
SAINDO dela. Preco de tabela abaixo do custo resolve-se REPRECIFICANDO.

### 3. O que ficou decidido e nao feito

Os outros 7 anuncios abaixo do piso **nao foram mexidos** — todos positivos,
e sair sobe preco, o que pode custar mais venda do que a margem recuperada.
Decisao de 02/09: tratar so o prejuizo, levar o resto ao Neto. A tabela com o
que acontece em cada um esta na secao da conferencia.

## CONFERIDO NA VITRINE: a promoção que vale é a MAIS BARATA

Medido em 02/09/2026 abrindo as páginas públicas no navegador. Seis anúncios,
seis vezes o mesmo resultado: **o preço que o comprador paga é o da promoção
ativa mais barata, nunca o que este script cadastrou.**

| anúncio | nosso preço (15%) | vitrine | margem real |
|---|---|---|---|
| #4695944189 SOFAMILAO-CARAMELO180 | R$ 1.220,53 | **R$ 993,27** | 2,4% |
| #7531752958 POLTRONABENY-GRAFITE | R$ 726,54 | **R$ 629,99** | 4,8% |
| #6782525936 POLTRONABENY-BEGE | R$ 594,36 | **R$ 532,99** | 7,3% |
| #5163518821 SOFABENY-BEGE180 | R$ 1.096,32 | **R$ 969,90** | 9,1% |
| #6756161546 SOFABENY-CINZA180 | R$ 1.009,44 | **R$ 881,99** | 9,4% |
| #7191880994 (controle) | R$ 1.038,87 | **R$ 972,99** | 10,5% |

A regra de precedência que estava em aberto agora está medida: **vence a mais
barata**. Portanto a trava de 10–15% deste script **não protege a venda** — ela
protege só a promoção que ele cadastrou, que pode nunca ser a aplicada.

### Exposição em toda a rodada

Conferidas as 136 adesões legíveis (a 137ª é o anúncio `under_review`):

| | |
|---|---|
| com outra promoção ativa MAIS BARATA | **40 (29%)** |
| dessas, abaixo do piso de 10% | 8 |
| dessas, em PREJUÍZO | **1** |
| afundadas / não afundadas | 18 / 22 |

**Não é problema dos afundados**: 22 das 40 nunca foram afundadas. É problema
de o script decidir olhando só proposta em `candidate`, cego para o que já está
em vigor.

### URGENTE — #6777799700 vende no prejuízo

POLTRONABENY-GRAFITE. Cadastramos a R$ 727,52 (10,1%, raspando o piso). Mas
quem manda é o DEAL "9.9" a **R$ 569,99**, já ativo antes desta rodada:

| preço | lucro | margem |
|---|---|---|
| R$ 727,52 — o que cadastramos | R$ 73,40 | 10,1% |
| **R$ 569,99 — DEAL "9.9", o que vale** | **−R$ 47,11** | **−8,3%** |

Custo R$ 350,00, frete R$ 133,15, taxa+imposto 23,5%. Cada venda perde
R$ 47,11, com estoque e vendendo. **Não foi esta rodada que causou.**

### O desconto de Pix — e o que ele NÃO é

A vitrine desse anúncio anuncia **R$ 524,39 (38% OFF) "no Pix", ou R$ 569,99
em 12x**. Os R$ 524,39 são **preço de Pix**, não preço de promoção: 8% abaixo
do DEAL.

Descartadas duas hipóteses, com evidência:

- **Não é o rebate.** O rebate aparece como `meli_percentage` no objeto da
  promoção — este DEAL não tem esse campo. E onde o rebate existe (as SMART),
  a vitrine bateu EXATAMENTE com o `price` da API: o rebate já está embutido
  no preço, não desconta por cima.
- **Não é cupom.** A página não menciona cupom para este anúncio.

Também não aparece em `/items/{id}/prices`, que lista só R$ 855,90 (standard),
R$ 569,99 e R$ 727,52. É desconto de meio de pagamento, aplicado na exibição.

E não é geral: o #4695944189 não tem linha de Pix nenhuma, e sua vitrine bate
com a API ao centavo.

**A pergunta que fica, e que muda a conta:** quem paga esse 8%? Se sai do
vendedor, toda venda por Pix neste anúncio perde ~R$ 127, não R$ 47. Se é do
ML, o vendedor recebe sobre R$ 569,99 e a margem é a da tabela acima.
Confirmar antes de calcular margem em cima de anúncio com Pix.

## Conferência dos 80 afundados (02/09/2026, pela API)

Dos 80 afundados do plano, 2 caíram nos erros da rodada → **78 com adesão OK**.
Conferidos um a um (não por amostra):

| | |
|---|---|
| confirmados `started` no preço que gravamos | **76** |
| aderiu, mas o ML aplicou OUTRO preço | 1 |
| não deu para ler | 1 |

### O achado que muda a conta: 18 anúncios têm promoção mais barata ATIVA

Em **18 dos 78** existe outra promoção `started` **abaixo** do preço que
afundamos. Como o script só decide sobre proposta em `candidate`, ele **não vê**
as que já estão em vigor — afundou até 15% numa campanha enquanto outra, mais
barata, já estava ativa no mesmo anúncio.

Recalculando a margem no preço da mais barata (com o rebate dela), **5 furam o
piso de 10%**:

| anúncio | SKU | nosso (15%) | a mais barata ativa | margem real |
|---|---|---|---|---|
| #4695944189 | SOFAMILAO-CARAMELO180 | R$ 1.220,53 | SMART R$ 993,27 | **2,4%** |
| #7531752958 | POLTRONABENY-GRAFITE | R$ 726,54 | DEAL R$ 629,99 | **4,8%** |
| #6782525936 | POLTRONABENY-BEGE | R$ 594,36 | DEAL R$ 532,99 | **7,3%** |
| #5163518821 | SOFABENY-BEGE180 | R$ 1.096,32 | SMART R$ 969,90 | **9,1%** |
| #6756161546 | SOFABENY-CINZA180 | R$ 1.009,44 | SMART R$ 881,00 | **9,4%** |

Nenhum dá prejuízo, e **nenhum foi causado por esta rodada**: essas campanhas
mais baratas já estavam ativas antes. Os outros 13 ficam entre 10,5% e 16,1%.

Duas consequências, e a segunda é a que dói:

1. Nesses anúncios, afundar até 15% **não comprou nada** — a vitrine já está
   mais barata por outra campanha. Parte dos R$ 10.721,81 "abertos mão" foi
   entregue a um preço que talvez nem seja o aplicado.
2. **A trava de 10–15% não vale para o preço que o comprador paga**, só para a
   promoção que este script cadastrou.

Correção de rumo sugerida (não feita): antes de decidir, ler também as
promoções `started`, não só as `candidate`. Se a mais barata ativa já fura o
piso, o caso não é afundar mais — é avaliar sair dela ("Deixar de participar"
existe na tela).

### Dois casos individuais

- **#4398500251** — o POST devolveu **OK** para SELLER_CAMPAIGN a R$ 945,38,
  mas a API mostra "Facilita 08" `started` a **R$ 899,90**. O ML aderiu por um
  preço que não é o nosso. A 899,90 a margem é 11,6%, acima do piso, então não
  é urgente — mas é a prova mais limpa de que **`OK` no log não garante o preço
  gravado**. Vale conferir preço, não só status, nas próximas rodadas.
- **#7574182716** — a leitura de promoções dá 400. O anúncio está
  `status: under_review`, `sub_status: ['forbidden']`. É problema do anúncio,
  não da promoção, e precisa de olho: anúncio nesse estado pode cair.

## A simulação NÃO é uma prévia confiável do --aplicar

Achado novo do teste, e é importante. A simulação das 06:09 e a aplicação das
06:11 — mesma conta, mesmos 10 anúncios, 2 minutos de diferença — decidiram
diferente em 4 linhas:

| anúncio | tipo | 06:09 simulação | 06:11 aplicação |
|---|---|---|---|
| MLB6761563796 | PRICE_DISCOUNT | RECUSAR @ 817,90 (8,29%) | ENTRAR @ 900,42 (15,0%) |
| MLB5946558910 | PRICE_DISCOUNT | ENTRAR @ 658,99 | ENTRAR @ 673,61 |
| MLB5823429926 | SELLER_CAMPAIGN | ENTRAR @ 659,99 | ENTRAR @ 683,93 |
| MLB5823429926 | PRICE_DISCOUNT | ALTERNATIVA @ 659,99 | ALTERNATIVA @ 683,93 |

A causa é o `suggested_discounted_price` do PRICE_DISCOUNT, que o ML muda entre
chamadas — a faixa `min`/`max` continuou igual. Quando a sugestão sobe acima do
teto, o script cai no ramo de afundar e o anúncio passa a caber na faixa; com a
sugestão baixa, ele era recusado por piso.

Duas consequências:

- **A trava de margem segurou nas duas rodadas** (tudo que entrou ficou em
  10–15%), então isso não cadastrou nada ruim. O que não é estável é *quais*
  anúncios entram, não a margem deles.
- **Conferir o CSV da simulação e depois rodar `--aplicar` não garante que só
  aquilo será escrito.** Decidido em 02/09/2026 **manter assim** — o `--aplicar`
  segue consultando a API na hora, para pegar sempre o preço mais atual do ML.
  Quem um dia quiser a prévia vinculante precisa fazer o `--aplicar` ler o CSV.

Um detalhe de rótulo, de menor importância: as 4 linhas marcadas
`ENTRAR (afundado)` subiram de preço, não afundaram, e por isso rendem MAIS por
venda. O resumo "abre mão de R$ 501,49 por rodada" está com o sinal invertido
nesses casos. O número de R$ 225,45 do Sofá Milão Caramelo, esse sim, é
afundamento de verdade.

## As regras (todas do Neto e do Matheus, 02/09/2026)

- Margem líquida **entre 10% (piso) e 15% (teto)**. O piso era 8% e subiu para
  10% a pedido do Matheus.
- **Acima do teto: entra E afunda o preço** até bater 15%. Confirmado depois de
  ver o custo: no Sofá Milão Caramelo 140 isso troca R$ 225 de lucro por venda
  por um desconto R$ 277 mais fundo. Vale para os 73 anúncios acima do teto.
- **Imposto 7%.**
- **Taxa: medida anúncio a anúncio**, não o 11,5%/16% fixo da planilha. A fixa
  discordava do que o ML cobra em 264 de 459 cenários, R$ 2.985,68 por rodada.
  `--taxa-casa` volta para a fixa.
- **Rebate SOMA.** A conta é a da Facilita: venda − (taxa+imposto) − custo −
  frete + rebate, dividido pela venda. O rebate soma porque a taxa usada é a
  cheia; taxa cheia − rebate = taxa real.
- Anúncio de catálogo sem SKU, com custo casado pelo título: **fica de fora**.

## Onde o plano está

Já executado — os números são os da rodada de 02/09/2026 06:32, não mais de
uma simulação. 178 anúncios, 455 propostas.

| | |
|---|---|
| entrar | **139** (80 com preço afundado até o teto) → 137 OK, 2 erro |
| alternativas descartadas | 230 |
| recusar (abaixo do piso) | 56 |
| recusar (prejuízo) | **30** |
| sem custo | 1 anúncio (o Kit #5696570996) |

O teto de 15% abre mão de R$ 10.721,81 por rodada de vendas. É decisão tomada,
não é problema a resolver.

Os números batem de perto com a última simulação antes da correção do payload
(142 entrar, 463 propostas, 29 prejuízo), mas não são idênticos — as propostas
do ML mudam entre chamadas. Ver a seção da prévia.

## Pendências

1. **Kit #5696570996** ("Kit 2poltrona Decorativa Pémadeira") — sem custo. O
   anúncio não devolve SKU pela API. Falta o Neto dizer o produto; provavelmente
   Kit Mona (R$ 680), mas NÃO foi confirmado. Para resolver, basta uma linha no
   `contas/facilita-brasil-principal/custos.csv` com o CÓDIGO DO ANÚNCIO como
   chave — o script aceita MLB… no lugar do SKU.
2. **Revisar a projeção de campos do multiget.** `/items?ids=…&attributes=…`
   devolve as variações PODADAS: o #4398500251 voltou sem SKU nenhum, mas a tela
   mostra SOFABENY-BEGE140 e SOFABENY-GRAFITE140 nas variações. Toda leitura em
   lote do zion-ml usa essa mesma projeção — a coleta diária, o raio-x, a
   precificação. Os "19 anúncios sem SKU" e os "7 com SKU inexistente" do raio-x
   de 28/08 podem ser em boa parte esse efeito, e não anúncio mal cadastrado.
3. **`core/tarifas.py` chamava `cli.tarifa_de_venda()`, que não existia** — sem
   except, então `python cli.py tarifas <conta>` estourava no primeiro anúncio.
   Corrigido em 02/09 junto com `promocoes_do_item`, que faltava do mesmo jeito
   (esse dentro de um `except Exception: continue`, então nunca quebrou: só
   nunca trouxe nada). Ambos eram resto do bug do `sku_do_item` de 31/08.

## Armadilhas medidas nesta conta

- `/items/{id}/shipping_options/free` dá 404 aqui. O que responde é
  `/users/{user}/shipping_options/free?item_id=…` — devolveu R$ 70,95 no
  #4701515641, o mesmo número da tela. Sem resposta, o anúncio é PULADO; frete
  zero inventado é o que cadastra promoção no prejuízo.
- Quem deixa escolher o preço não é o tipo da campanha: é ter
  `min_discounted_price`/`max_discounted_price` na resposta. SMART vem com preço
  fechado. PRICE_DISCOUNT vem SEM campo `id` — mandar `promotion_id` nela quebra.
- Um anúncio pode ter várias propostas ao mesmo tempo (um tinha 5). O script
  entra só na que deixa mais dinheiro por venda; `--todas` entra em todas.
- As sugestões "Melhorar" do próprio ML levam a prejuízo: na página 1 eram 4,
  a pior derrubando a Poltrona Beny Cinza a −R$ 74 por venda. O botão não
  conhece o custo do vendedor.
