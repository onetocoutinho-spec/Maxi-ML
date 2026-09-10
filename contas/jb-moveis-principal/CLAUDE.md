# CONTA: JB Móveis e Estofados  (`jb-moveis-principal`)

> **TRAVA OPERACIONAL.** Esta pasta opera **exclusivamente** o user_id
> `493976420`. Antes de qualquer escrita: `python cli.py checar <slug>` e
> confirmar que o apelido devolvido é `JBMOVEISESTOFADOS`.

Cliente `jb-moveis` — "JB Móveis e Estofados", móveis e estofados. Registrado
em `config/clientes.yaml` em 08/09/2026, com esta como **principal** e
`jb-moveis-loja2` como **secundária** (destino do espelhamento, ainda sem
credencial).

## Roteiro: como baixar frete, ou publicar já barato (destilado em 08/09/2026)

Vale para as três contas do grupo (JB, JELCDECOR, EJPRIME) — mesmo dono, mesmo
padrão de catálogo. Antes de repetir a investigação inteira de hoje, comece
por aqui. O caso completo que gerou este roteiro está mais abaixo, nas seções
sobre `MLB3895367079` e `MLB7606444628`.

### Anúncio NOVO

1. **Declare a caixa REAL, sempre.** É a única alavanca legítima de frete.
   Produto menor/mais leve de verdade baixa o custo; caixa inventada menor só
   troca frete caro por sobretaxa na coleta ou recusa — foi o que já tirou a
   JELCDECOR da buy box (atraso por remessa mal dimensionada).
2. **Fora do catálogo, o frete é a SUA caixa (`SELLER_PACKAGE_*`). Dentro do
   catálogo, é a caixa que a FICHA declara** — e isso não se escreve pela
   conta do cliente. Se a ficha tiver medida ruim (grande, ou errada — já
   vimos um `WEIGHT: 150 kg` numa poltrona de 1 lugar), nascer *fora* do
   catálogo com a caixa real pode sair mais barato. Prova de hoje: mesma
   ficha, R$147,85 vinculado x R$119,05 fora dela.
3. **Isso só funciona se a categoria não exigir GTIN para item fora de
   catálogo.** Testado e travado sem código de barras real (`MLB416807`
   exige; `EMPTY_GTIN_REASON` não dispensa). Confirme ANTES de prometer o
   resultado ao cliente.
4. **Flex (`self_service`) hoje está quebrado nesta conta** — tag
   `self_service_trial` em `/users/{id}/shipping_preferences` com cobertura
   real zerada. Não conte com ele como plano até confirmar que voltou.

### Anúncio JÁ EXISTENTE, com frete alto

- **É de catálogo?** O frete não está na sua mão — é a ficha. Dois caminhos:
  reportar o erro pro ML (se o dado da ficha for claramente errado) ou
  recriar fora do catálogo. Só vale a pena recriar se: (a) tem GTIN real,
  (b) **já existe irmão saudável cobrindo a mesma ficha** — senão a saída
  tira a conta da disputa de buy box de verdade — e (c) **o item não tem
  histórico de venda relevante** — senão joga fora reputação e ranqueamento
  por uma economia de frete que não compensa.
- **Já é tradicional (fora do catálogo)?** O frete é a caixa que a própria
  conta declarou. Confira se bate com a medida real; se está maior que o
  produto de verdade, corrija com PUT **isolado** só no campo de dimensão
  (nunca `shipping` inteiro de uma vez) e releia depois — mandar mais de um
  campo já desligou frete grátis duas vezes nesta conta, sem querer.

### O que já foi testado e NÃO funciona — não repetir

- Caixa menor que a real pra forçar preço: não baixa custo, transfere o
  problema pra depois (sobretaxa/recusa/atraso).
- Forçar `logistic_type` por PUT: às vezes volta HTTP 200 e não muda nada —
  o ML ignora o campo quando o item está numa trilha especial da conta
  (ex: `self_service_trial`).
- Presumir que sair do catálogo sempre é mais barato: só é quando a ficha
  está com dado pior que a sua caixa real. Comparar os dois antes de decidir
  — sem isso é aposta, não alavanca.
- `PUT catalog_product_id` para vincular um item já publicado a uma ficha:
  devolve `400 not_modificable`. O vínculo só acontece no nascimento
  (POST); não dá pra migrar depois pela API.

## Estado em 07/09/2026

Conectada por OAuth em 07/09/2026, com o mesmo app das outras contas (só o
consentimento muda). `.env` gravado nesta pasta.

| | |
|---|---|
| apelido | JBMOVEISESTOFADOS |
| user_id | 493976420 |
| reputação | 5_green · 18.570 transações |
| tags | business, eshop, **user_product_seller** |
| `status.mercadoenvios` | `not_accepted` — mas isso NÃO impede me2 pela API (ver CLAUDE.md da Chinelaria) |
| anúncios | 143 (38 ativos, 99 pausados, 5 em revisão, 1 fechado) |

## O objetivo: espelhar este catálogo numa segunda conta do MESMO dono

O Neto vai conectar a conta de destino em **08/09/2026**. Origem e destino são
do mesmo dono.

⚠️ **Consequência já avisada e aceita:** nas 99 fichas de catálogo as duas
contas passam a disputar a MESMA buy box. É canibalização entre irmãs — ligar
`ml-concorrencia` quando estiver no ar.

## O retrato da origem já está extraído

Tudo em `dados/`, colhido em 07/09 enquanto a origem estava autorizada. A
migração não depende mais de a origem continuar no ar.

| arquivo | o que é |
|---|---|
| `itens-origem-2026-09-07.json` | os 143 anúncios completos, como a API devolveu |
| `descricoes-origem.json` | 136 descrições (6 anúncios não têm nenhuma) |
| `fichas-catalogo.json` | as 93 fichas distintas em que ele anuncia |
| `fotos-origem.json` | 1.311 fotos: `id` e URL do CDN, por anúncio |
| `variacoes-origem.json` | a estrutura dos 24 com variação (115 combinações) |
| `plano-migracao.csv` | **uma linha por anúncio, com a rota de cada um** |

## As três rotas, e por que não é um lote só

    99  CATALOGO      nao se clona: publica-se na MESMA ficha (catalog_product_id)
    24  VARIACOES     a esteira recusa de proposito; 115 combinacoes dentro
    19  TRADICIONAL   a esteira `cli.py publicar` pega direto

**Só 19 dos 142 passam pela esteira como ela está.** Quem tratar isso como um
lote único vai quebrar na primeira dezena.

Os 99 de catálogo são, na verdade, a parte mais rápida — publicar numa ficha
existente é menos trabalho que recadastrar. Os 24 com variação são o item mais
caro: a conta é `user_product_seller`, então provavelmente cada variação vira
item separado, como na Chinelaria.

## O estoque desta conta é FICTÍCIO — não copiar

    mediana 10.000 | maximo 99.999 | 133 dos 142 declaram mais de 500

Mesma prática já registrada em FACILITA e Decoralli. A "vitrine" calculada
sobre isso dá R$ 3,5 bilhões e **não significa nada** — nunca levar esse número
ao cliente. A esteira nasce com estoque 1 de propósito; manter assim e decidir
o estoque do destino à parte.

## O que testar PRIMEIRO amanhã, antes de publicar em lote

1. **`picture_id` atravessa conta?** Se o destino aceitar `{"id": ...}` das
   fotos da origem, são 1.311 fotos que não precisam ser baixadas e resubidas.
   Se recusar, o caminho é baixar, preparar e subir — e aí vale a receita da
   Chinelaria (o ML recorta borda branca de foto vinda por URL).
2. **`family_name`**: 71 nomes distintos cobrindo 105 anúncios. É imutável
   depois do POST. Conferir a string ANTES de subir o primeiro.
3. **Publicar em ficha de catálogo** exige o item passar na validação da
   ficha. Testar com UM antes do lote.

## As três contas dividem ficha de propósito (08/09/2026)

Conectadas mais duas do mesmo dono: **JELCDECOR** (user_id 1627881723, 8.607
transações, 67 anúncios) e **EJPRIME** (user_id 2245348587, 6.242 transações,
111 anúncios).

    JB         93 fichas       JB x JELCDECOR ....... 22 em comum
    JELCDECOR  47 fichas       JB x EJPRIME ......... 27 em comum
    EJPRIME    63 fichas       JELCDECOR x EJPRIME .. 30 em comum
                               nas TRÊS ............. 18

**43 fichas têm mais de uma conta do grupo dentro, e isso é intencional.**

### ⚠️ CORREÇÃO — eu li isto errado em 08/09/2026

Apresentei essas 43 fichas ao Neto como canibalização, com uma lista de "onde
o dono está dando lance contra si mesmo". **Estava errado, e ele corrigiu:**

> "Não é canibalização. Nós criamos os anúncios e vinculamos os melhores nos
> catálogos; tem variações que ficam mais competitivas em cada catálogo, por
> isso essa grande quantidade de repetidos."

A operação **escolhe** em qual ficha cada variação entra, porque a mesma linha
de produto rende diferente conforme a ficha. Repetição de ficha entre as irmãs
é cobertura deliberada, não descuido.

**Lição para quem for analisar estas contas:** sobreposição entre contas do
mesmo dono NÃO é, por si, defeito. Antes de chamar de canibalização, pergunte
à operação qual é a intenção. Um número alto de fichas compartilhadas aqui é
sinal de estratégia funcionando, não de erro — e uma "correção" automática de
preço destruiria justamente o que faz o esquema render.

### O que `coordenar_preco: true` faz aqui, e por que fica ligado

Mantido — mas pela razão certa. Ele NÃO existe para tratar a sobreposição como
problema. Existe para impedir que o motor recomende **baixar o preço de uma
conta para vencer a irmã**: como o dono é o mesmo, ganhar da irmã não ganha
venda nova, só reduz a margem do grupo. A decisão de qual conta entra em qual
ficha, e a que preço, é da operação.

### O único ponto que talvez valha o olho do dono

Três fichas em que o preço de uma irmã está muito distante das outras:

    MLB42526637   JB 899  |  EJPRIME 899  |  JELCDECOR 5.000
    MLB42526431   JELCDECOR 200  |  JB 899  |  EJPRIME 899
    MLB36264611   JB 499  |  JELCDECOR 899  |  EJPRIME 899

Pode ser proposital — preço alto para manter o anúncio vivo sem vender é
prática conhecida. Registrado como pergunta, não como diagnóstico.

### O que continua valendo

As três compartilham a prática de estoque fictício (mediana ~10.000 nas três).
Não usar "valor parado" em nenhuma delas, e não copiar esse estoque ao
espelhar catálogo.

## Replicação JELC -> JB: os 5 primeiros (08/09/2026)

Motivo: a JELCDECOR está **"RESTRITO PARA GANHAR — você não pode ganhar porque
teve envios atrasados"** (61 atrasos em 60 dias, 3,43%). A JB tem **0% de
atraso em 1.611 vendas**. Mesma ficha, conta limpa, chance de buy box de volta.

Mapa origem->novo em `dados/replicados-2026-09-08.json`.

    MLB7591090126 -> MLB7606444628   R$ 1.190,00  est 1.624  ficha MLB50913618
    MLB7591101172 -> MLB7606469746   R$ 1.190,00  est 1.933  ficha MLB50913632
    MLB4435244121 -> MLB7606469806   R$   899,00  est 1.597  ficha MLB52368713
    MLB4856935029 -> MLB7606444836   R$   799,00  est 1.680  ficha MLB37447334
    MLB4435382735 -> MLB7606469942   R$   899,00  est 1.564  ficha MLB48941762

Os 5 nasceram `active` (anúncio de catálogo nasce ativo; a regra de "nascer
pausado" é da Chinelaria, não desta conta).

### O que o teste com `/items/validate` provou antes de escrever

1. **`picture_id` ATRAVESSA de uma conta para outra do mesmo dono.** As fotos
   foram por id, sem baixar nem resubir. Economiza o trabalho inteiro de
   imagem numa migração.
2. **A JB publica nas fichas da JELC** sem impedimento.
3. `lost_me1_by_user` é **aviso**, não erro — a distinção está no campo `type`
   de cada `cause`. `/items/validate` devolve 400 mesmo quando só há avisos:
   **contar os `type == "error"`, não olhar o status HTTP.**

### ⛔ DOIS PROBLEMAS QUE SÓ APARECERAM DEPOIS DE PUBLICAR

**1. Descrição não existe em anúncio de catálogo.**
`Description is not modifiable on catalog listing item`. O texto vem da ficha.
Não é falha — é como o catálogo funciona. Não tentar copiar descrição.

**2. Quatro dos cinco perderam o Mercado Envios.** Mandei `me2` no POST e o ML
gravou `not_specified`. Causa: em anúncio de catálogo eu não enviei atributos,
então nasceram **sem `SELLER_PACKAGE_*`** — e sem medida de caixa o ML rebaixa
o envio, o mesmo padrão do `lost_me2_by_dimensions` já documentado.

Copiei a caixa da origem e reafirmei o me2: **o frete grátis voltou, o modo
NÃO.** Ficam `not_specified` com a etiqueta `me2_available`.

O único que manteve me2 veio de uma origem com caixa PEQUENA (30x40x80,
13 kg). Os quatro que falharam vêm de caixas grandes — 78x83x94 / 34,8 kg e
63x76x88 / 28,1 kg. As originais da JELC têm me2 com essas mesmas caixas, o
que sugere regra aplicada na criação e mantida nas antigas.

**Erro meu no meio disso:** tentei forçar `logistic_type` no PUT e as duas
tentativas **desligaram o frete grátis**. Restaurado em seguida nos 5.
Lição: `shipping` é objeto inteiro — mandar campo a mais reescreve o resto.
Alterar envio um por vez e reler depois de cada PUT.

### O que falta decidir

Os 4 estão no ar com frete grátis mas sem Mercado Envios. Em ficha de
catálogo isso provavelmente pesa contra na buy box. Caminhos:
- confirmar com o dono a caixa REAL desses produtos (78x83x94 e 34,8 kg pode
  estar superdimensionado; se a caixa real for menor, o me2 volta);
- ou aceitar frete próprio nesses quatro.

**Não mexer na medida sem o número real** — a caixa é o que o ML cobra de
frete, e chutar menor é criar prejuízo por venda.

### O envio dos 5 replicados: o que ficou provado e o que não resolvi (08/09/2026)

**Estado final:** 1 dos 5 com me2 funcionando; 4 como `not_specified` +
frete grátis, ou seja **"a combinar com o comprador"** — `methods: []` e
`shipping_options` devolvendo 404 `no_coverage_options_found`.

    MLB7606444836  cat MLB32664   me2 / cross_docking   54x62x85  13,8 kg   OK
    MLB7606469806  cat MLB416807  not_specified         58x73x85  29,25 kg  me2_available
    MLB7606469942  cat MLB1626    not_specified         58x73x85  29,25 kg  me2_available
    MLB7606444628  cat MLB416807  not_specified         83x87x105 30,66 kg  lost_me2_by_dimensions
    MLB7606469746  cat MLB416807  not_specified         83x87x105 30,66 kg  lost_me2_by_dimensions

**O ML REESCREVEU a caixa que mandei** — 78x83x94/34.800 g virou
83x87x105/30.660 g; 63x76x88/28.143 virou 58x73x85/29.252. É o mesmo
comportamento já registrado na Chinelaria. **Calcular limite e frete pela
medida que o ML GRAVOU, nunca pela que foi enviada.**

Comparando com os 38 anúncios de catálogo da JB que TÊM me2 nessas mesmas
categorias: eles ficam entre 192 e 238 cm de soma e **8 a 23 kg**. Os dois que
perderam por dimensão estão em 275 cm e 30,66 kg — acima. Os outros dois estão
dentro (216 cm, 29,25 kg) e mesmo assim o ML não atribui o modo.

### Três hipóteses testadas e DESCARTADAS

1. **"Faltou a caixa no POST."** Recriei um item com `SELLER_PACKAGE_*` no
   payload de criação: continuou `not_specified`. Não era isso.
2. **"A caixa é grande demais, tem que declarar menor."** A JB **já vende**
   poltrona reclinável com me2 declarando 73x85x102 e **40 kg**
   (MLB4683374677, MLB4660978015). O tamanho, sozinho, não explica.
3. **"É só reafirmar o modo depois."** `PUT shipping` devolve **200** e o ML
   mantém `not_specified`. Não dá para forçar por API.

⚠️ **Cuidado com o PUT de `shipping`: é objeto inteiro.** Mandar
`logistic_type` junto DESLIGOU o frete grátis em duas tentativas. Alterar um
campo por vez e reler depois de cada chamada.

### O que NÃO foi feito, e por quê

O Neto perguntou se dava para replicar com medida menor para ganhar o me2.
**Não é preciso e não seria seguro:** a JB já roda me2 com caixa maior que essa,
então o tamanho não é o bloqueio; e a medida declarada é a base do frete que o
ML cobra e do que a transportadora espera. Subdimensionar gera sobretaxa ou
recusa na coleta, e depois atraso de entrega — que é exatamente a penalidade
que tirou a JELCDECOR da buy box. Os **0% de atraso da JB** são hoje o ativo
mais valioso do grupo.

### O que falta, e onde está a resposta

Não descobri por que o ML não atribui me2 a anúncio NOVO nessas categorias
nesta conta hoje, sendo que os de 2025 têm. A API não expõe o motivo. **O
painel do vendedor mostra** — abrir um dos quatro em Anúncios > Envio e ver o
que o ML alega ali.

**Erro meu no processo:** criei um 6º anúncio (MLB5203602853) para testar e
fechei em seguida. Ficou como `closed` na conta.

## Por que anúncio de catálogo NOVO nasce sem Mercado Envios (08/09/2026)

**Em anúncio de catálogo, o ML calcula o envio pela medida da FICHA, não pela
sua.** O `SELLER_PACKAGE_*` que você manda é ignorado; o PUT de `shipping` volta
HTTP 200 e não aplica nada. Se a ficha declara peso/medida impossível ou acima
do teto do Mercado Envios, o anúncio nasce `not_specified` — "a combinar com o
comprador" — e não há payload que conserte.

Medido nas 5 réplicas de 08/09:

| cópia | ficha | envio | o que a FICHA declara | tag |
|---|---|---|---|---|
| MLB7606444628 | MLB50913618 | not_specified | **41 kg**, 97x101x108 | `lost_me2_by_dimensions` |
| MLB7606469746 | MLB50913632 | not_specified | **41 kg**, 97x101x108 | `lost_me2_by_dimensions` |
| MLB7606469806 | MLB52368713 | not_specified | 22 kg, **8000 cm** de largura | `me2_available` |
| MLB7606469942 | MLB48941762 | not_specified | 22 kg, 80x90x117 | `me2_available` |
| MLB7606444836 | MLB37447334 | **me2** | **nenhuma medida** | — |

As duas fichas de 41 kg passam do teto de 30 kg do ME2 — e são exatamente as
duas que o ML marca como `lost_me2_by_dimensions`. A única que funciona é a
única cuja ficha não declara peso: sem dado na ficha, o ML cai para a caixa do
vendedor. 8000 cm é erro de digitação de quem criou a ficha, não nosso.

### O que foi descartado com teste, para não refazer

- **conta**: `/users/493976420/shipping_options/free` devolve cobertura SIM e
  custo real (R$ 119 a R$ 200) para TODAS essas caixas.
- **categoria**: a JB tem 26 anúncios com me2 em MLB416807 e 14 em MLB1626 —
  as mesmas categorias que falharam.
- **ficha em si**: em cada uma das 4, há 3 ou 4 concorrentes com me2 e frete
  grátis. A ficha aceita me2; o que não passa é anúncio novo.
- **caixa menor**: réplica na MESMA ficha com caixa de 30x40x80 / 13 kg —
  gravada sem o ML reescrever — continuou `not_specified`. **Declarar caixa
  menor não resolve**, porque a nossa caixa não é lida.
- **frete grátis**: desligar e religar não muda o modo.
- **`shipping.dimensions`**: aceito, gravado, irrelevante.
- **vincular depois**: `PUT catalog_product_id` → 400 `not_modificable`.
  Não dá para nascer tradicional e migrar para a ficha pela API.

### O que FUNCIONA (testado no mesmo dia, mesma conta, mesma caixa)

Anúncio **tradicional** em MLB416807, caixa 63x76x88 / 28,1 kg, R$ 899, frete
grátis → nasce `me2` + `cross_docking` + `mandatory_free_shipping` na hora.
Testes MLB5203749765 e MLB5203750659, ambos fechados em seguida.

### Caminhos

1. **Ativar os 5 já pausados** da JB nas fichas da JELC — todos já com me2 e
   cross_docking. Não depende de cadastro novo nem do ML.
2. **Pedir correção da ficha** ao ML (sugerir alteração na página do catálogo):
   41 kg e 8000 cm são erro de ficha. Corrigido lá, anúncio novo passa a nascer
   com me2. Depende da revisão do ML.
3. **Subir tradicional** enquanto isso: nasce com me2 comprovado, mas não
   disputa a ficha — não devolve a buy box que a JELC perdeu.

Nunca declarar caixa menor que a real para forçar me2: além de não funcionar
aqui, a caixa declarada é a base do frete, e subdeclarar dá sobretaxa ou recusa
na coleta — que vira atraso, que é exatamente a penalidade que tirou a JELCDECOR
do catálogo. A JB tem 0% de atraso em 1.611 vendas; é o ativo mais caro do grupo.

## Ativação dos 4 pausados (08/09/2026, autorizada pelo Neto)

Ativados: MLB7416828576 (R$ 878), MLB6721386060 (R$ 899), MLB5811943086
(R$ 799), MLB6693260610 (R$ 799). Todos mantiveram `me2` + `cross_docking` +
frete grátis, sem `sub_status`. O quinto (MLB7521778056, R$ 499) já estava
ativo — eram 4 pausados, não 5.

Frete real medido antes de ativar (`/items/ID/shipping_options`), que a JB paga
por ser frete grátis obrigatório:

| anúncio | SP | Porto Alegre | Recife |
|---|---|---|---|
| MLB7416828576 | 133 | 106 | **425** |
| MLB7521778056 | 148 | 121 | **456** |
| MLB6721386060 | 133 | 94 | **412** |
| MLB5811943086 | 119 | 88 | **377** |
| MLB6693260610 | 148 | 100 | **435** |

Nordeste custa 3 a 4 vezes o Sul/Sudeste e chega a metade do preço do produto.
Se a margem desses cinco foi feita com o frete do Sudeste, ela é teto.

### `not_listed` depois de reativar

Logo após ativar, os 4 voltaram `price_to_win = not_listed` e não apareciam em
`/products/{ficha}/items`. Três leituras em 4 minutos, sem mudar. **Não é
defeito de cadastro**: nos 44 anúncios de catálogo ativos da JB o placar é
32 winning, 4 listed, 3 sharing_first_place, 1 competing e 4 not_listed — e os
4 not_listed são exatamente estes. Ficha ativa, item ativo, sem sub_status,
constam na busca `catalog_listing=true`. O ML reavalia a entrada no catálogo
depois da reativação e demora. **Reconferir no dia seguinte antes de concluir
qualquer coisa.**

### Preço contra a irmã, nas fichas destes 4

| ficha | JB | JELC | terceiro mais barato |
|---|---|---|---|
| MLB65905769 | 878 | 978,99 | 641 |
| MLB50390784 | 899 | 669,90 | (só a JELC) |
| MLB53620943 | 799 | 479,99 | (só a JELC) |
| MLB49100139 | 799 | 686,99 | (só a JELC) |

Em três das quatro a JB está ACIMA da irmã. Como a JELC está restrita para
ganhar, ninguém do grupo leva a ficha: a JELC não pode, a JB está cara. Decisão
de preço é do Neto — mas é aqui que a migração ou funciona ou não serve para
nada.

A réplica nova MLB7606444836 já está **winning** na ficha dela. As outras duas
que competem estão `listed`. Ou seja: a esteira funciona quando a ficha não
sabota o envio.

## CORREÇÃO (08/09/2026, mais tarde): não é o valor da ficha, é a ficha declarar

A seção acima diz que o anúncio nasce sem me2 porque a ficha declara peso
**errado** (41 kg, 8000 cm). **Está errado.** Publiquei MLB5203913803 numa
ficha que declara 2,5 kg e 78x65x80 — número perfeitamente dentro do limite do
Mercado Envios — e ele nasceu `not_specified` igual aos outros.

Placar das 6 réplicas, sem exceção:

| réplica | ficha | a ficha declara medida? | envio |
|---|---|---|---|
| MLB7606444628 | MLB50913618 | sim, 41 kg | not_specified |
| MLB7606469746 | MLB50913632 | sim, 41 kg | not_specified |
| MLB7606469806 | MLB52368713 | sim, 22 kg | not_specified |
| MLB7606469942 | MLB48941762 | sim, 22 kg | not_specified |
| MLB5203913803 | MLB53172876 | sim, **2,5 kg** | not_specified |
| MLB7606444836 | MLB37447334 | **não declara** | **me2** |

**A regra é: ficha que declara peso/medida própria faz o anúncio de catálogo
NOVO nascer sem Mercado Envios, seja o número razoável ou não.** A única que
funciona é a única sem medida na ficha — aí o ML cai para a caixa do vendedor.
Corrigir o 41 kg da ficha provavelmente NÃO resolve; o que resolve é a ficha
não declarar medida, o que não está na nossa mão.

Reafirmar me2 por PUT continua voltando 200 e não aplicando (testado 2x neste
anúncio, com 75 s de intervalo).

### Descrição em anúncio de catálogo

`POST /items/ID/description` → 400 `Description is not modifiable on catalog
listing item`. Não é defeito: anúncio de catálogo exibe a descrição da ficha.
Não tentar copiar descrição nessa rota.

### Estado de MLB5203913803

Publicado a pedido do Neto em 08/09: R$ 799, estoque 1624, 7 fotos, ficha
MLB53172876 (onde só a JELC anunciava, a R$ 629,90). Está `active`, sem envio,
`not_listed`. **Anúncio ativo sem envio vende "a combinar com o comprador"** —
para uma loja com 0% de atraso em 1.611 vendas isso é risco de reputação sem
contrapartida, já que sem envio ele nem disputa a ficha.

## CORREÇÃO do frete (08/09/2026): o frete grátis é só no Sudeste

A tabela de frete na seção "Ativação dos 4 pausados" está **errada** na leitura.
Ali eu li `list_cost` e disse que a JB paga R$ 377 a R$ 456 para o Nordeste.
**Não paga.** O campo que diz quem paga é o `cost` de `/items/ID/shipping_options`:
`cost = 0` significa frete grátis (a JB absorve o `list_cost`); `cost > 0`
significa que **o comprador paga**.

Medido em MLB5204037969 (R$ 899), e o mesmo padrão vale para os de catálogo:

| destino | comprador paga | quem banca |
|---|---|---|
| SP capital, Campinas, Ribeirão Preto | 0 | **JB paga R$ 133,15** |
| Rio de Janeiro, Belo Horizonte | 0 | **JB paga R$ 133,15** |
| Curitiba | 91,99 | comprador |
| Florianópolis, Porto Alegre | 93,99 | comprador |
| Belém | 275,99 | comprador |
| Fortaleza | 307,99 | comprador |
| Salvador | 319,99 | comprador |
| Recife | 411,99 | comprador |

**O frete grátis obrigatório cobre o Sudeste. Fora dele o comprador paga.**
A exposição da JB por venda é R$ 133,15 no Sudeste, não R$ 400+ no Nordeste.

Curiosidade a investigar: Guarulhos-SP devolveu `cost = 54,99` (comprador paga),
sem opção gratuita, enquanto Campinas e Ribeirão Preto vieram zero. Pode ser
oferta só de Flex naquele CEP. Não confirmado.

Regra para não repetir o erro: **`list_cost` é o custo cheio do frete; `cost` é
o que o comprador desembolsa.** Só quando `cost = 0` o vendedor está pagando.

## Decor bege publicado como TRADICIONAL (08/09/2026, autorizado pelo Neto)

`MLB5204037969` — Poltrona Reclinável Retrátil Papai E Mamãe Lorentti Decor
Bege Liso. R$ 899, estoque 1546, 3 fotos, SKU JUPOLTDECORBEGE.
**Nasceu com `me2` + `cross_docking` + frete grátis**, e a descrição subiu
(HTTP 201) — em anúncio tradicional a descrição é gravável, ao contrário do
de catálogo.

Era o único dos 5 travados sem nenhum anúncio equivalente com envio na JB.
Os outros 4 já tinham irmão vendendo com me2 em OUTRA ficha (casado por SKU).

## MLB3895367079 preso em self_service sem cobertura (08/09/2026)

Reativado hoje (preço 1.409→800) e nasceu `logistic_type: self_service` em vez
de `cross_docking` — a conta está com tag `self_service_trial` em
`/users/493976420/shipping_preferences`, com só 1 serviço de transporte
configurado contra os 7 do cross_docking. Resultado: `/items/ID/shipping_options`
devolve 404 em qualquer CEP testado (vendedor, SP, PA, PE, RS), inclusive sem
token — o comprador real vê "a combinar com o comprador". Não é falta de
`SELLER_PACKAGE_*` (o item tem 77x44x58/21kg completo) nem transição: outro
item da conta (MLB6721344376) está preso no mesmo estado desde maio.

**Tentei o PUT isolado `{"shipping":{"logistic_type":"cross_docking"}}`
(autorizado pelo Neto): HTTP 200, mas não aplicou nada — `logistic_type`
continuou `self_service` depois de reler.** Frete grátis não caiu desta vez.
Mesmo padrão já visto aqui para `me2`/`not_specified`: o ML aceita o PUT e
ignora o campo quando o item está dentro do trial de Flex da conta.

**Painel do vendedor também não deixa corrigir** (confirmado pelo Neto olhando
ao vivo). Tentei então recriar um anúncio semelhante do zero (rota tradicional,
mesma caixa real do item de origem — 77x44x58cm, produto 10kg / embalagem
bruta 21kg —, sem forçar `logistic_type`): nasceu **`MLB5205044615`**, e em vez
de repetir o `self_service` sem cobertura, caiu num bloqueio diferente,
`lost_me2_by_dimensions`, com `free_shipping` zerado — mesma caixa que já
funciona em outros anúncios maiores desta conta (73x85x102/40kg tem me2 em
outro anúncio já documentado acima). Dois mecanismos de bloqueio diferentes,
no mesmo dia, na mesma conta: não parece mais ser sobre cadastro de item
nenhum — parece a conta inteira com algo quebrado do lado do ML hoje
(08/09/2026), possivelmente ligado ao `self_service_trial` que apareceu em
`/users/493976420/shipping_preferences`.

**Os dois foram pausados** (autorizado pelo Neto, 08/09/2026) — nenhum dos
dois vendia de qualquer forma, sem frete calculável. `MLB3895367079` e
`MLB5205044615` ficam pausados até resolver por suporte do ML ou até o
problema da conta se resolver sozinho; não repetir a tentativa de PUT em
`shipping` sem antes conferir se o `self_service_trial` ainda está ativo na
conta.

**CORREÇÃO — não é a conta inteira, é a família do MLB3895367079.** Testei
recriar o mesmo tipo de anúncio a partir de uma origem SAUDÁVEL desta vez
(`MLB6693260610`, que já roda `me2`+`cross_docking` de verdade) em vez do item
travado. Nasceu limpo: **`MLB7608181160`**, `me2`/`cross_docking`/frete grátis,
cobertura real confirmada em São Paulo (`list_cost` R$ 119,05). Ou seja, a
publicação nova funciona normalmente nesta conta hoje — o bloqueio é
específico da família/`user_product` ligada ao `MLB3895367079`
(`family_id 6192121291150224`), não um problema geral da conta ou do
`self_service_trial` afetando tudo. `MLB7608181160` fica ativo como
substituto funcional; os dois travados (`MLB3895367079`, `MLB5205044615`)
seguem pausados — não vale a pena insistir nessa família específica, é mais
barato nascer de novo a partir de um irmão saudável, como foi feito aqui.

Receita que funcionou, para repetir: rota tradicional, `family_name` liderado
pelo substantivo do produto, atributos da origem menos `ITEM_CONDITION`, fotos
por `picture_id`, `shipping` me2 + free_shipping. O ML gerou o título
"Poltrona Reclinável Retrátil Papai E Mamãe Lorentti Decor Bege Liso" — diz o
que o produto é, ao contrário de "Ms Móveis Decor Liso Preto" que saiu da rota
de catálogo. Avisos benignos na simulação: `MANUFACTURER ignored`,
`lost_me1_by_user`, `mandatory_free_shipping added`.

Custo: fora do catálogo ele não disputa a ficha MLB52368713 — troca posição de
catálogo por ter envio. Para este SKU era a escolha certa, porque sem envio ele
não vendia de jeito nenhum.

## MLB7606444628: GTIN bloqueia antes de chegar ao teste de frete (08/09/2026)

Retomei o teste de frete deste item (caixa real 83x87x105/30,66 kg) autorizado
a usar `EMPTY_GTIN_REASON`. **Não funcionou, em nenhuma das três formas
testadas**, e a hipótese de frete (item grande de verdade, acima da faixa
saudável de 192-238cm/8-23kg da conta) não chegou a ser avaliada — trava
anterior e mais fundamental.

1. `--atributo EMPTY_GTIN_REASON="O produto não tem código cadastrado"` (texto
   livre) → a simulação local (sem `--publicar`) passa limpa, porque o comando
   só monta o payload e não valida contra a API. O POST real (`--publicar
   --sim`) devolveu de novo `HTTP 400 item.attribute.missing_conditional_required
   — GTIN é obrigatório`. Causa: `EMPTY_GTIN_REASON` é atributo tipo `list`
   (confirmado em `/categories/MLB416807/attributes`) — só aceita `value_id`,
   não `value_name` livre.
2. Corrigido para `value_id` certo (`17055160` = "O produto não tem código
   cadastrado") → **mesmo erro 400**, confirmado via `/items/validate`
   (chamada isolada, sem criar item, para não gastar mais uma tentativa real).
3. Acrescentando `GTIN` vazio junto (sem valor, ou `value_name: null`) →
   mesmo erro, mais o aviso `item.attribute.dropped` avisando que o ML
   descartou o GTIN vazio.

**Conclusão: nesta categoria (MLB416807), `EMPTY_GTIN_REASON` não dispensa
`GTIN` para anúncio fora de catálogo — mesmo enviado corretamente.** O único
anúncio tradicional que funcionou nesta mesma categoria hoje (`MLB5204037969`,
seção "Decor bege" acima) tinha GTIN **real** herdado da origem
(`7896129415923`) — não usou a rota de motivo vazio; não é precedente de que
`EMPTY_GTIN_REASON` funcione aqui. O item de catálogo `MLB7606444628` não tem
GTIN porque item de catálogo não precisa (a ficha responde por isso); ao tentar
sair do catálogo para ganhar frete próprio, a exigência de GTIN aparece e não
há bypass pela API para esta categoria. Não inventei um código — atribuir um
GTIN que não é do produto seria dado falso no cadastro.

**Nada foi publicado.** Nenhuma chamada desta rodada criou item: a tentativa
com `--publicar --sim` recebeu 400 antes de criar qualquer recurso, e as
tentativas seguintes usaram `/items/validate` (que nunca cria). O teste da
hipótese de frete grande (83x87x105/30,66 kg fora do catálogo) segue pendente
de um SKU desta família que tenha GTIN real, ou de decisão do cliente sobre
cadastrar um código para esta linha.

## MLB7606444628, retomado com GTIN real: GTIN parou de bloquear, a caixa confirmou ser grande demais — investigação ENCERRADA (08/09/2026)

O dono forneceu o GTIN real desta linha de produto: `7896461077230`. Repeti o
teste com `--caixa "83x87x105" --peso-caixa "30.66 kg" --atributo
GTIN=7896461077230`, checado por `cli.py checar` (nickname `JBMOVEISESTOFADOS`,
user_id 493976420 confirmado) antes de escrever.

**A simulação bateu limpa**: GTIN gravado, os quatro `SELLER_PACKAGE_*`
presentes (83/87/105 cm, 30.660 g), `shipping.mode=me2` sem `logistic_type`
forçado, preço igual ao original (R$ 1.190), rota tradicional. Publiquei de
verdade.

**Publicou.** `MLB7608264878` — desta vez o GTIN NÃO bloqueou o POST (era
exatamente o problema das duas tentativas anteriores, agora resolvido pelo
código real). Mas:

    status                  active, sem sub_status
    shipping.mode           not_specified
    shipping.logistic_type  not_specified
    shipping.free_shipping  false
    shipping.tags           lost_me2_by_dimensions
    /shipping_options       404 no_coverage_options_found

**Confirma a hipótese que estava em aberto: não era o GTIN escondendo o
problema de frete — a caixa 83x87x105 / 30,66 kg é grande demais de verdade
para o Mercado Envios nesta conta, hoje.** Está acima da faixa saudável já
documentada aqui para anúncio de catálogo saudável (192–238 cm de soma /
8–23 kg) e no teto observado nas fichas de catálogo desta mesma família
(30 kg). Diferente do caso de catálogo (onde a medida vinha da FICHA), aqui o
anúncio é tradicional e a medida É a nossa, enviada corretamente — então desta
vez o bloqueio é genuinamente de tamanho/peso, não de payload incompleto ou
de ficha contaminada. Não tentei contornar com caixa menor: caixa declarada é
a base do frete real, e subdimensionar troca um problema de cadastro por um
de sobretaxa ou recusa na coleta — a mesma penalidade que já tirou a JELCDECOR
da buy box.

**Investigação deste item encerrada em 08/09/2026, com as duas causas
distintas e sequenciais resolvidas:**
1. GTIN obrigatório na categoria MLB416807 para item fora de catálogo — hoje
   resolvido com o código real do produto (`7896461077230`).
2. Caixa genuinamente grande demais para Mercado Envios — não resolvido, e
   não é para "resolver" por aqui: exigiria caixa/peso real menor (se existir
   um SKU assim) ou aceitar frete próprio/"a combinar com o comprador" para
   esta linha 83x87x105/30,66 kg. Sem novo dado de medida real, não há mais
   teste a fazer neste anúncio.

`MLB7608264878` foi pausado (autorizado pelo Neto, 08/09/2026) — sem Mercado
Envios, não vendia de qualquer forma. Fica pausado junto com `MLB3895367079` e
`MLB5205044615` até decidir o que fazer com essa linha de produto (caixa
menor de verdade, ou aceitar que só vive em ficha de catálogo).

## Terceiro teste do MLB3895367079: forçar Clássico não muda nada — é a família, não a modalidade (08/09/2026)

Hipótese testada: os dois travados (`MLB3895367079` origem e o clone
`MLB5205044615`) eram os únicos dois `gold_pro` (Premium) desta investigação;
os dois clones saudáveis (`MLB7608181160`, `MLB7608264878`) nasceram
`gold_special` só porque herdaram modalidade de outras origens. Faltava testar
Clássico partindo da MESMA origem travada.

Simulação (`--caixa "77x44x58" --peso "10 kg" --peso-caixa "21 kg" --modalidade
gold_special`, sem herdar modalidade da origem): payload bateu limpo —
`listing_type_id: gold_special` de fato (não herdou `gold_pro`), rota
tradicional (categoria MLB186067, sem `catalog_product_id`), `shipping.mode=me2
free_shipping=true` sem `logistic_type` forçado, os 4 `SELLER_PACKAGE_*`
presentes (77/44/58cm, 21000 g), preço R$800 igual ao original.

Publicado de verdade (autorizado): **`MLB5205288987`**
(http://produto.mercadolivre.com.br/MLB-5205288987). Nasceu, de novo, sem
Mercado Envios:

    status                  active, sem sub_status
    listing_type_id         gold_special (confirmado — não é Premium)
    shipping.mode           not_specified
    shipping.logistic_type  not_specified
    shipping.free_shipping  False
    shipping.tags           ['lost_me2_by_dimensions']
    /shipping_options       404 (sem cobertura)

**Hipótese Premium descartada.** Forçar Clássico não mudou o resultado: mesmo
`lost_me2_by_dimensions` do clone anterior (`MLB5205044615`, também
`gold_special` por herança). Confirma de novo que o bloqueio é da
família/`user_product` do `MLB3895367079` (`family_id 6192121291150224`), não
da modalidade de anúncio. Já são três nascimentos dessa família — origem
reativada, clone 1, clone 2 — e os três falharam de formas diferentes
(`self_service` sem cobertura, `lost_me2_by_dimensions`, `lost_me2_by_dimensions`
de novo), enquanto clones de outras origens saudáveis (`MLB7608181160`) nascem
limpos no mesmo dia, na mesma conta. Não vale mais gastar tentativa nesta
família: o caminho é o já registrado acima — nascer de um irmão saudável, ou
aceitar catálogo/frete próprio para este SKU específico.

`MLB5205288987` foi pausado (autorizado pelo Neto, 08/09/2026) — sem Mercado
Envios, não vendia de qualquer forma. Fica pausado junto com `MLB3895367079`,
`MLB5205044615` e `MLB7608264878`: são quatro exemplares dessa família sem
frete, todos pausados, até decidir reportar ao suporte do ML ou aceitar que
este SKU só vive em ficha de catálogo.
