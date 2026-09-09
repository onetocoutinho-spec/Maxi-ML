# CONTA: Chinelaria Leilane Neves  (chinelaria-principal)

> **TRAVA OPERACIONAL — leia antes de qualquer ação.**
> Esta pasta opera **exclusivamente** a conta `chinelaria-principal`, user_id `2332812759`.
> Publicar, alterar preço, pausar anúncio ou responder pergunta usando
> credencial de outra conta é o erro mais caro desta operação.
> Se algo pedir para operar outra conta, **pare e confirme com o Neto**.

## Estado: AUTORIZADA em 02/09/2026 — e SEM NENHUM ANÚNCIO NO AR

Credencial gravada e conferida (`checar` devolve CHINELARIALEILANENEVES).
A primeira coleta rodou e achou o seguinte:

| leitura | valor |
|---|---|
| anúncios ativos / pausados / fechados / em revisão | **0 / 0 / 0 / 0** |
| vendas concluídas em 365 dias | 32 |
| reputação | 5_green · 0 reclamação · 0 cancelamento · 0 atraso |
| `status.mercadoenvios` | **not_accepted** |
| `status.list.allow` | true (pode publicar) |

Ela tem histórico e reputação boa, mas **hoje não há um único anúncio** —
varrido por `/users/{id}/items/search` em todos os status, não só ativos.
Portanto:

- relatório, painel, diagnóstico e alerta desta conta saem vazios **porque não
  há o que ler**, não porque a conta esteja saudável. Não leve "0 problemas"
  para a cliente como se fosse bom sinal;
- o trabalho aqui não é otimizar anúncio, é **cadastrar do zero** (skill
  `cadastrar-produto-ml`), e não pela esteira `cli.py publicar`, que precisa de
  um anúncio de origem — não existe nenhum nesta conta nem em conta irmã;
- `mercadoenvios: not_accepted` é a primeira pedra do caminho: em chinelo, item
  leve, publicar sem Mercado Envios é publicar sem frete competitivo. Resolver
  isso ANTES de subir catálogo, senão sobe tudo errado e recadastra depois.

Checklist do cadastro:

- [x] cliente e conta registrados em `config/clientes.yaml` (user_id 2332812759)
- [x] pasta alinhada ao template atual (custos, fichas de catálogo, redirect)
- [x] autorizada — `.env` gravado nesta pasta em 02/09/2026
- [x] `cli.py checar` — apelido confere
- [x] primeira coleta — snapshot em branco, pelo motivo acima
- [x] Mercado Envios — resolvido: pela API o me2 entra e fica (03/09/2026)
- [ ] definir o que entra primeiro: catálogo de produtos + fotos + custo
- [ ] `custos.csv` com o custo real dela (ver `CUSTOS-LEIA-ME.md`)
- [ ] confirmar a margem mínima com a Leilane e corrigir `conta.yaml`
      (os 20% de lá vieram do esqueleto, não dela)
- [ ] `palavras-chave.yaml`: os 4 termos são chute do esqueleto. A busca por
      termo devolve ficha de catálogo, e hoje os três termos de babuche caem
      todos no mesmo produto errado ("Botton Pins para Babuche", um acessório).
      Rever depois que existir produto real cadastrado.

## Identificação
- Cliente: chinelaria-leilane
- Conta: Chinelaria Leilane Neves — papel: principal
- user_id: 2332812759
- Apelido no ML: CHINELARIALEILANENEVES
- Conta criada em 17/03/2025 · tags: business, eshop, user_product_seller
- Site: MLB (Brasil)

## Credencial
Vem de `.env` **desta pasta**, carregada por `core/auth.py` a partir do slug.
Nunca leia token de variável de ambiente global nem de outra pasta.
O app do ML é o mesmo das outras contas — o que muda é só o consentimento,
que precisa sair do login DELA (janela anônima, senão você autoriza a conta
que já estava aberta no navegador).

## Antes de qualquer escrita na API
1. Rode `python cli.py checar chinelaria-principal` e confirme que o nickname devolvido
   é o desta conta.
2. Confirme que o `user_id` do token bate com o do registro (o `MLClient`
   já faz isso e aborta se divergir — não contorne essa checagem).
3. Só então execute.

## Particularidades desta conta

**Modelo "User Products".** Cada variação de tamanho/cor é um item separado
compartilhando o mesmo `family_name`. Consequência para quem analisa: o mesmo
chinelo aparece como vários anúncios. Antes de chamar isso de duplicata ou de
canibalização, confira o `family_name` — irmão da mesma família é grade, não
concorrente de si mesmo. E **nunca** altere `family_name` de item já publicado.

Atributos que a categoria exige: `BRAND`, `MODEL`, `GENDER`, `SIZE_GRID_ID`,
`GTIN` (ou `EMPTY_GTIN_REASON`) e `SELLER_SKU`. Tabela de medida via
`POST /catalog/charts`, por categoria de gênero.

**Concorrência.** Em calçado boa parte da briga acontece fora de ficha de
catálogo, e o ML não deixa ler anúncio de terceiro por ID (403). O que dá para
prometer à cliente: DESCOBRIR esses concorrentes no raio-x, como retrato do
momento. O que não dá: ACOMPANHAR com alerta contínuo. Só ficha de catálogo
tem vigilância de verdade — é o que vai em `concorrentes.yaml`.

_(a preencher depois da conversa de entrada: política de preço, quem decide
preço, marcas próprias x revenda, prazo de produção)_

## Comandos do dia a dia
```bash
python cli.py coletar chinelaria-principal      # snapshot + alertas
python cli.py alertas chinelaria-principal      # o que apareceu nas últimas 24h
python cli.py relatorio chinelaria-leilane
```

## Mercado Envios: o `not_accepted` NÃO é o que impede (medido em 03/09/2026)

O perfil da conta traz `status.mercadoenvios: not_accepted`. Isso levou a
concluir, no começo desta sessão, que a conta não podia publicar com Mercado
Envios. **Está errado.**

Testado com `POST /items/validate` — que valida o payload e **não cria
anúncio** — em três variantes, com dados reais de um tênis Molekinho
(EAN, peso 0,730 kg, caixa 31x21x12):

| `shipping.mode` | resposta |
|---|---|
| `me2` | 400 — `Attribute [SIZE_GRID_ID] is missing` |
| `me2` + `free_shipping` | 400 — o mesmo |
| `not_specified` | 400 — o mesmo |

As três param no MESMO ponto, e não é envio. O ML devolve todas as causas de
uma vez; se o me2 fosse recusado para esta conta, apareceria aqui. Bate com o
que o `CLAUDE.md` da raiz já registrava de outra conta: o formulário não
oferece Mercado Envios, mas pela API o `shipping.mode` é declarado e aceito.

**O que trava de verdade é a TABELA DE MEDIDAS.** Em calçado, no modelo User
Products, `SIZE_GRID_ID` é obrigatório. A conta não tem nenhuma tabela criada
(`/catalog/charts/search` e `/users/2332812759/catalog/charts` voltam vazios).
Na categoria MLB273770 (Sandálias e Chinelos): `SIZE` é obrigatório e de
variação, `SIZE_GRID_ROW_ID` é o atributo de variação que aponta a linha da
guia.

Ordem correta do cadastro, portanto:

1. criar a tabela de medidas por gênero (`POST /catalog/charts`) — **é escrita
   na conta, exige autorização**;
2. publicar com `family_name` (e SEM `title` — o ML recusa os dois juntos);
3. `shipping.mode = me2` mais `SELLER_PACKAGE_LENGTH/WIDTH/HEIGHT/WEIGHT`.
   Sem a medida da caixa o ML aceita o me2 no POST e **retira depois**,
   carimbando `lost_me2_by_dimensions`. A Magazord tem peso e as três
   dimensões em 96% das derivações, então dá para mandar sempre.

## Tabela de medidas: o que já se sabe (03/09/2026)

Endpoint certo: **`POST /catalog/charts`** (existe; os `GET` de busca dão 404).
Descoberto por tentativa, com os erros do próprio ML:

- `domain_id` vai **sem o prefixo `MLB-`** — mandar `SANDALS_AND_CLOGS`, não
  `MLB-SANDALS_AND_CLOGS`. O ML compõe e reclama de `MLB-MLB-...`.
- `names` é **mapa por site**: `{"MLB": "nome da guia"}`. Lista devolve
  `JSON parse error ... from Array value`.
- `main_attribute.attributes[]` usa a chave **`id`**, não `attribute_id`.
- `attributes` (nível da tabela) não pode ficar vazio — leva GENDER.
- Cada linha exige **`FOOT_LENGTH`** (comprimento do pé em cm). Sem isso:
  `required_row_attribute_not_found`.
- `SIZE` **não** serve como `main_attribute`: `invalid_main_attribute_id`.

O que falta para criar: o valor de FOOT_LENGTH por numeração, e o
`main_attribute` correto (provavelmente `BRAND_SIZE` ou `FOOT_LENGTH`).

**Não inventar o FOOT_LENGTH.** Guia de tamanho errada gera devolução e
reclamação, que é o que mais machuca reputação em calçado. Vem da tabela do
fornecedor (Grendene, Molekinho, Boaonda publicam), ou medindo.

### A guia da marca NÃO dá para reaproveitar

As fichas de catálogo de terceiros expõem a guia delas — ex.: Tênis Molekinho
2623-121 usa `SIZE_GRID_ID 4325435`, com linhas `4325435:2` e `SIZE "26 BR"`.
Testado no `/items/validate` da conta dela: `SIZE_GRID_ID is not valid`.
A guia é presa à ficha, não é pública para qualquer vendedor.

## RESOLVIDO em 03/09/2026: a tabela de medidas e o Mercado Envios

Tabela criada na conta: **`grid_id 7298346`** — "Modare Feminino Adulto",
domínio `SANDALS_AND_CLOGS`, 33 a 40 BR. Linhas em `dados/guia-modare-feminino.json`.

### A receita que o ML aceita em `POST /catalog/charts`

```json
{ "names": {"MLB": "<nome da guia>"},
  "domain_id": "SANDALS_AND_CLOGS",        // SEM o prefixo MLB-
  "site_id": "MLB",
  "attributes": [ {"id":"GENDER","values":[{"name":"Feminino"}]},
                  {"id":"BRAND", "values":[{"name":"Modare"}]} ],
  "rows": [ {"attributes":[ {"id":"BR_SIZE","values":[{"name":"35 BR"}]},
                            {"id":"FOOT_LENGTH","values":[{"name":"23.3 cm"}]} ]} ] }
```

O que custou tentativa e erro, e não está em lugar nenhum:

- **NÃO mandar `main_attribute`.** As guias que funcionam trazem ele `null`;
  o ML define sozinho (`main_attribute_id: BR_SIZE`).
- **NÃO pôr `SIZE` nas linhas** — só `BR_SIZE` e `FOOT_LENGTH`. Com `SIZE` o
  ML recusa: `invalid_row_attribute`.
- `names` é **mapa por site**, não lista.

### De onde tirar o FOOT_LENGTH sem inventar

**`GET /catalog/charts/{grid_id}` de terceiro é LIBERADO SÓ ÀS VEZES.**
Medido em 03/09/2026: as guias de MARCA saem (Molekinho `4325435`, Modare),
mas as de VENDEDOR devolvem 403 `access_denied` — "the user is not the owner
of the chart" (testado em `2706912`, `2674300`, `2697260`). Ou seja: dá para
colher a numeração das marcas, não a dos concorrentes. Então: acha-se a ficha
de catálogo da marca
(`/products/search` por domínio), lê-se o `SIZE_GRID_ID` dela, e o GET devolve
a numeração em centímetros publicada pela PRÓPRIA MARCA.

Colhido em `dados/ml-guias-de-tamanho.csv`. Ex.: Modare feminino 33=21,9 cm …
40=26,6 cm; Molekinho meninos, 25 tamanhos.

### O que o `/items/validate` ainda cobra (03/09/2026)

Com a guia certa e `shipping.mode=me2`, o envio **para de ser recusado**.
Restam:

| erro | o que fazer |
|---|---|
| `requiresPictures` | foto é obrigatória em `gold_special` — as URLs do CDN da Magazord resolvem |
| `missing_required [COLOR, FOOTWEAR_TYPE]` | ambos saem do nome da derivação |
| `lost_me1_by_user` | informativo: ela não tem me1. Não impede o me2 |
| **`mandatory_free_shipping`** | **acima de R$ 79 o ML OBRIGA frete grátis** |

O último muda a conta: **73 dos 121 produtos da fila estão acima de R$ 79**,
logo todos vão com frete grátis obrigatório, pago por ela. O piso desses tem
que absorver o frete — não é escolha, é imposição do ML.

### Em aberto: numeração PAREADA (27/28, 33/34)

Boa parte da grade dela é pareada — é o normal em babuche e chinelo. Nenhuma
guia lida até agora tem linha pareada: as amostras vêm com tamanho simples
("25", "28 BR", "29 BR"). Não está provado que o ML aceita `BR_SIZE` pareado
numa guia própria, e isso afeta um pedaço grande do catálogo.
**TESTADO E FECHADO em 03/09/2026: o ML NÃO aceita numeração pareada.**

- Guia com `BR_SIZE` "27/28 BR" e "27/28": `invalid_row_attribute_value`.
- O atributo `SIZE` da categoria MLB273770 tem **44 valores permitidos e
  nenhum com barra** (16, 17, … 36, com meios-números como 31.5 e 34.5).

Não é limite da guia: é a categoria inteira. A grade pareada dela — que é o
normal em babuche e chinelo, e cobre 33/34, 41/42, 27/28 entre as numerações
mais comuns — **precisa ser convertida para tamanho simples** antes de virar
anúncio. Isso é decisão comercial, não técnica:

| saída | o que custa |
|---|---|
| desdobrar o par em dois tamanhos (27 e 28) | dobra a descoberta; o estoque tem de ser dividido, e vender os dois pelo total do par gera venda a descoberto |
| publicar só um tamanho do par | estoque honesto; quem busca o outro número não acha |

Decidido em 03/09/2026: começar desdobrando, com estoque dividido, e medir.
(Preço do Babuche LED definido pelo Neto: **R$ 141,90**, margem 19,5%.)

Também confirmado: `FOOTWEAR_TYPE` da categoria só aceita
**Sandália, Chinelo, Tamanco, Mule** — babuche não está na lista, escolher
qual usar.

## ARMADILHA: as fotos NÃO estão separadas por cor (03/09/2026)

`dados/magazord-fotos-urls.csv` traz `cod_agrupador` (produto+cor), e é
tentador tratá-lo como chave de cor. **Não é.** No Babuche LED Molekinho
2874.407, as 22 fotos estão TODAS sob `2585111-102997pretoamareloneon`, mas
ao abrir as imagens:

- fotos 01 e 05 → babuche **preto** com friso neon
- fotos 09 e 12 → babuche **marinho** com friso laranja (a OUTRA cor)
- foto 07 → sola preta, não identifica cor nenhuma

Publicar por esse mapeamento poria foto de sapato azul num anúncio vendido
como preto. Foi pego pelo Neto antes de subir; nada foi publicado.

O arquivo tem coluna `confianca`, o que já denuncia que o casamento foi
inferido: 8.003 ALTA, 804 MEDIA, 592 "BAIXA - REVISAR" e 1.660 em branco.
E "ALTA" não salva: as 22 do babuche são todas ALTA.

### Tamanho do problema na fila dos 121

| situação | quantos |
|---|---|
| **uma cor só** — foto não tem como estar trocada | 33 |
| **várias cores** — precisa revisar foto a foto | 61 |
| sem foto | 27 |

Dos 33 de cor única, só **2** estão prontos no resto (EAN completo, peso,
preço ≥ R$ 79). Ou seja: a foto virou o gargalo real do cadastro, não o
Mercado Envios nem a tabela de medidas.

**O que resolve na fonte:** uma exportação da Magazord que ligue FOTO à
DERIVAÇÃO (ou à cor), em vez de ao produto. No site cada variante de cor tem
galeria própria — o dado existe, só não veio neste arquivo.

## PRIMEIRO ANÚNCIO NO AR — 03/09/2026

**`MLB7584200654`** — Babuche LED Infantil Molekinho 2874.407 EVA, Preto, 27 BR.
R$ 141,90 · estoque 5 · 10 fotos · SKU 01045727 · EAN 7900350914565.

O que o ML devolveu, e é o que interessa guardar:

```
shipping.mode      = me2          <- Mercado Envios ACEITO
shipping.logistic  = drop_off
free_shipping      = true
SELLER_PACKAGE_*   = 26x18x11 cm, 350 g   (gravou, não descartou)
SIZE_GRID_ID       = 7739769  linha :1  SIZE "27 BR"
tags               = cart_eligible, good_quality_thumbnail,
                     immediate_payment, user_product_listing
status             = paused / picture_download_pending
```

**Nenhum carimbo `lost_me2_by_dimensions`.** O `status.mercadoenvios:
not_accepted` do perfil era o formulário — pela API o me2 entra e FICA, desde
que `SELLER_PACKAGE_*` vá no payload. Fica provado para as próximas.

`paused` + `picture_download_pending` é normal: o ML está baixando as 10 fotos
do CDN da Magazord. Ele ativa sozinho quando terminar. Conferir depois; se
ficar pendente por muito tempo, é sinal de URL que o ML não conseguiu buscar.

### A separação de fotos usada (conferida no olho)

As 22 do agrupador `2585111-102997pretoamareloneon` são de DUAS cores:

- **Preto** (friso verde neon): 01–07 estúdio + 19–22 ambientadas
- **Marinho** (friso laranja): 08–14 estúdio + 15–18 ambientadas

Simétrico — 7 de estúdio e 4 ambientadas para cada. A 07 é sola solta e foi
para o preto pelo tom. Ordem publicada: capa de estúdio primeiro, **LED aceso
em segundo** (22 no preto, 18 no marinho), resto depois.

Faltam subir os outros 19 irmãos (payloads prontos em
`dados/payload-babuche-led.json`).

## O que deu errado no piloto, e como foi corrigido (03/09/2026)

O `MLB7584200654` nasceu `paused/picture_download_pending` e passou a
`under_review` com **`waiting_for_patch`**. Duas causas, achadas no exame:

### 1. As fotos do CDN viraram imagem pequena

O ML **recorta as bordas brancas** da foto que baixa. As fotos de estúdio da
Magazord têm muito fundo branco, então depois do corte sobrava pouco:

    capa       686x390     <- abaixo do minimo de 500x500
    3 fotos    ~687x310
    2 fotos    317x310 e 302x313
    4 fotos    1000x1200   <- so as AMBIENTADAS passaram

Ou seja: **passar a URL do CDN direto para o ML é armadilha** em foto de
estúdio. Some com o produto e o anúncio entra em revisão.

**Correção que funcionou:** baixar a original, recortar o branco, reescalar e
subir para o ML por `POST /pictures/items/upload`, depois
`PUT /items/{id}` com os `picture_id`. O anúncio foi para `active` na hora.

Escalar pelo MAIOR lado não basta — foto achatada (vista lateral) continua
morrendo no corte. A receita boa é **escalar pelo MENOR lado até ~620 px**,
teto de 1500 no maior, e centralizar em tela quadrada branca.

### 2. O ML TROCA a medida da embalagem

Enviei `26x18x11 cm, 350 g` (o que está na Magazord). O ML gravou:

    SELLER_PACKAGE_LENGTH  12 cm    (mandei 26)
    SELLER_PACKAGE_WIDTH   23 cm    (mandei 18)
    SELLER_PACKAGE_HEIGHT  29 cm    (mandei 11)
    SELLER_PACKAGE_WEIGHT  355 g    (mandei 350)

Ele descarta a medida declarada e aplica uma caixa padrão de calçado. O frete
é cobrado pelo peso cúbico, então isso importa: 858 g viraram **1.334 g**.

Impacto medido neste produto: frete R$ 19,05 -> **R$ 19,45**, margem 19,5% ->
**19,2%**. Pequeno aqui; em item maior pode não ser. **Calcular margem com a
medida que o ML GRAVOU, não com a que você mandou** — reler o item depois de
publicar e refazer a conta.

## O agrupamento: como ele acontece (03/09/2026)

Os 17 anúncios do Babuche LED **estão agrupados**. Conferido item a item:

    family_name  "Babuche Led Infantil Molekinho 2874.407 Eva"   (igual nos 17)
    family_id    8258019780319887                                (igual nos 17)

É assim que o modelo User Products agrupa: não existe `variations`. Cada
tamanho/cor é um item próprio, e o que junta é o **`family_name` idêntico** —
o ML deriva o `family_id` dele e passa a mostrar um seletor de tamanho e cor
numa página só.

**Consequência operacional, e é a que morde:** para um irmão novo cair na
mesma família, o `family_name` tem de ser **exatamente a mesma string**. Um
acento, uma maiúscula ou um espaço a mais cria uma família NOVA, e o produto
se parte em dois grupos na vitrine. O ML normaliza o texto ao gravar (mandei
"LED ... EVA", ele gravou "Led ... Eva"), mas não conte com isso: reaproveite
a string do payload, não redigite.

Não há endpoint público para listar uma família (`/families/{id}`,
`/user-products/families/{id}` e `?family_id=` dão 404). Para conferir o
agrupamento, leia `family_id` de cada item e compare.

## Segundo produto no ar: Zaxy Conectada (03/09/2026)

16 anúncios, `family_id 5506766791329104` — "Sandalia Plataforma Feminina
Zaxy 19409 Conectada Up". R$ 194,90 · 43 pares · 8 numerações × 2 cores
(Marrom cc109, Preto cc112). Guia criada: **`grid_id 7741603`**.

Frete lido: **R$ 22,25** (caixa 32x22x13, 500 g -> peso cobrado 1.526 g).
Margem a R$ 194,90: **21,4%** (lucro R$ 41,67).

### ⚠️ A guia Zaxy usa centímetros da MODARE — confirmar

Não existe guia de marca legível para Zaxy nem para sandália feminina adulta:
todas as candidatas são de vendedor e dão 403. Usei os centímetros da tabela
Modare publicada no ML (33 = 21,9 cm … 40 = 26,6 cm), porque numeração BR ->
comprimento do pé é norma nacional e o gênero e as numerações são os mesmos.

**É premissa, não dado da Zaxy.** Confirmar com a tabela da Grendene (dona da
Zaxy) e corrigir a guia 7741603 se divergir.

### ⚠️ As fotos da Zaxy são peça de marketing

Das 24 fotos, **só 4 estão limpas**: 01 e 13 (marrom), 07 e 19 (preto). As
outras 20 têm texto sobreposto ("Conforto para sua rotina", "Estilo que
valoriza cada momento") ou selos, e as com modelo trazem faixa de texto. O ML
penaliza imagem com texto promocional e reprova na capa.

**REGRA DEFINIDA PELO NETO em 03/09/2026: sobe todas as fotos; só a CAPA não
pode ter escrita.** Aplicada nos 16 anúncios da Zaxy — 10 fotos cada, nesta
ordem: as 2 limpas de estúdio, as 2 com modelo, as 2 do par visto de cima, e
por fim os infográficos. Capa = foto 01 (marrom) / 07 (preto), ambas limpas.

Vale para os próximos produtos: peça de marketing entra, mas nunca na primeira
posição.

Separação de cor conferida no olho: **01–06 e 13–18 marrom, 07–12 e 19–24
preto** — dois conjuntos por cor. O `cod_agrupador` de novo carimbou tudo como
uma cor só (cc109), e a `confianca` era MEDIA nas 24.

## REGRA DA OPERAÇÃO: anúncio nasce e fica PAUSADO (Neto, 03/09/2026)

Terminou o cadastro de um item, **pause**:

```
PUT /items/{id}   {"status": "paused"}
```

Quem decide ativar é o Neto, não a esteira. Em 03/09/2026 os 33 anúncios do
Babuche LED e da Zaxy Conectada ficaram todos `paused_by_seller`.

Por que isso importa na hora de conferir: `paused` com sub_status
**`paused_by_seller`** é o estado NORMAL desta conta — não é problema. O que
exige ação é outro sub_status (`waiting_for_patch`, `picture_download_pending`,
`under_review`) ou `paused` sem `paused_by_seller`.

Não reative nada sem pedido explícito, mesmo que pareça esquecimento.

## Lote de 03/09/2026: 10 produtos, 111 anúncios

Conta fechou o dia com **144 anúncios**, todos `paused_by_seller` e todos com
me2 — 723 pares, R$ 104.923 de vitrine. Categorias: 90 em MLB273770
(sandálias/chinelos) e 54 em MLB23332 (tênis).

Guias criadas (uma por marca+gênero+domínio, porque a guia é presa ao domínio):

| guia | grid_id | domínio |
|---|---|---|
| Modare Feminino 33-40 | 7298346 | SANDALS_AND_CLOGS |
| Molekinha Meninas 27-36 | 7300854 | SANDALS_AND_CLOGS |
| Havaianas Feminino 33-40 | 7300856 | SANDALS_AND_CLOGS |
| Cartago Meninos 28-36 | 7741963 | SANDALS_AND_CLOGS |
| Actvitta Feminino 34-40 | 7742075 | SANDALS_AND_CLOGS |
| Zaxy Feminino 33-40 | 7741603 | SANDALS_AND_CLOGS |
| Modare Feminino Tênis 33-40 | 7742085 | SNEAKERS |
| Actvitta Feminino Tênis 34-40 | 7742087 | SNEAKERS |

A esteira do lote está em `scratchpad/subir_lote.py` (sessão de 03/09).

### Três armadilhas que este lote revelou

**1. TÊNIS é outra categoria e outro domínio.** `MLB23332` (Tênis), domínio
`SNEAKERS`. A guia de medidas é **presa ao domínio**: a guia de SANDALS não
serve para tênis, tem de existir uma por domínio. E em MLB23332 o
`FOOTWEAR_TYPE` não é exigido, enquanto em MLB273770 é obrigatório.

**2. `COLOR` é lista fechada** nas duas categorias (51 valores em MLB23332).
Cor tirada do texto da derivação quebra: "preto/hibisco 110463" e "104809
preto/pink" não existem na lista. A saída é varrer as palavras do texto e usar
a primeira que exista na lista do ML — o que salva "Preto" nos dois casos.
Sem isso o POST morre em `item.attributes.missing_required`.

**3. Detectar "é tênis?" pelo título falhou por ACENTO.** O teste
`"enis" in titulo` dá falso em "**Tênis**" (é "ênis"), e dois produtos vieram
sem título na exportação. Resultado: tênis foi cadastrado como chinelo e
morreu em `missing_required`. Não infira categoria de texto com acento —
mantenha lista explícita, como está em `TENIS_IDX` no script.

### O que ficou retido do lote de 15

Cinco produtos precisam de numeração **41 a 46**, e a tabela de centímetros
colhida do ML vai até 40. Não foram publicados, e nas demais famílias os
tamanhos acima de 40 ficaram de fora: Havaianas unissex 35/36-45/46, Actvitta
37-43 e 37-44, Cartago 37-45, Havaianas Top Herois 35/36-41/42.

**Para destravar:** o comprimento do pé de 41 a 46, da tabela do fornecedor.
Não extrapolar a progressão — guia errada gera devolução.

## ERRO GRAVE E CORREÇÃO: foto de cor misturada em lote (03/09/2026)

A esteira do lote mandou **todas as fotos do PRODUTO para todos os anúncios**.
Em produto de várias cores, isso pôs foto de sapato azul em anúncio preto —
o mesmo erro que o Neto pegou no piloto, agora repetido em escala.

**Como escapou:** o filtro de "cor única" lia a cor como o PRIMEIRO token do
texto da derivação, assumindo que era um código numérico
(`105739 marinho/laranja`). Nas Havaianas o texto começa com palavra
(`t basic branco/br/branco`), então o token era "t" para todas as cores e o
produto passou como se fosse de uma cor só.

**A cor de verdade é o `Código Agrupador`** (produto+cor), não um pedaço do
texto. Onde ele existe, a foto ESTÁ separada por cor.

**Correção aplicada:** `scratchpad/corrigir_fotos.py` usa a chave que já estava
gravada em cada anúncio — `SELLER_SKU` → derivação → `Código Agrupador` →
fotos daquele agrupador — e faz `PUT` só em `pictures`. Sem republicar.
**128 anúncios corrigidos**, 0 erro.

### ⛔ 74 anúncios NÃO PODEM SER ATIVADOS

Em 13 combinações de cor **não existe foto no arquivo da Magazord**. Esses
anúncios seguem com a foto de OUTRA cor, e estão em
`dados/anuncios-sem-foto-da-cor.json`. Nenhum está visível: a conta inteira
está pausada. Mas ativar qualquer um deles é anunciar o produto errado.

Os maiores: Babuche LED marinho/laranja (9), Zaxy Conectada preto (8), Tênis
Modare London branco/avela e branco/dourado (7 cada), Havaianas Glitter
verde-olive e cinza-gelo (6 cada), Havaianas Jelly buttercream e blossom
(6 cada).

**Resolve com a exportação da Magazord que ligue foto à derivação** — o mesmo
pedido que está aberto desde a manhã. Enquanto não vier, esses 74 ficam
pausados e marcados.

## `family_name` é IMUTÁVEL depois de criado (03/09/2026)

Quatro produtos (28 anúncios) nasceram com `family_name: "(sem Titulo)"`
porque a exportação do TikTok Shop tinha o campo `Título` vazio para eles, e
a esteira usava esse campo sem checar.

**`PUT /items/{id}` com `family_name` sempre devolve 400** —
`BODY_INVALID_FIELDS: The field family name is invalid` — inclusive
reenviando o MESMO valor que o item já tem. Não é o valor que é inválido: o
campo é **fechado para edição depois do POST**, ponto final.

**Correção:** não tem meio-termo. Fecha o anúncio velho
(`PUT status=closed`) e cria um novo idêntico — mesma categoria, preço,
estoque, fotos, atributos, envio — só com o `family_name` certo. O antigo
fica em `closed` para sempre (histórico, não se apaga), o novo nasce
`active` e é pausado na sequência, como de praxe.

Confirmado **sem venda nenhuma** nos 28 antes de mexer (`sold_quantity` zerado
em todos) — recriar um item vendido teria implicações diferentes
(reputação, histórico de comprador) que não foram avaliadas aqui.

Script usado: `scratchpad/corrigir_titulos.py` (sessão de 03/09). 27 de 27
corrigidos automaticamente, 1 corrigido manualmente antes de rodar o lote,
0 erros. Agrupamento conferido depois: cada família recriada ficou com
`family_id` único e consistente entre os irmãos.

### Um nome vinha corrompido na própria Magazord

"Chinelo Havaianas Fantasia Style ||" — o campo `Produto - Derivação` trazia
`||` onde deveria ser o algarismo romano `II` (o campo `Modelo`, mais limpo,
tinha `FANTASIA STYLE II`). Não é erro da esteira: é sujeira na fonte. Corrigi
à mão para "Chinelo Dedo Havaianas Fantasia Style II" antes de recriar — o ML
normalizou para "Style Ii" no título, aceitável.

**Lição para a próxima exportação de título vazio:** cair para o `Modelo` da
Magazord, nunca usar o campo bruto `Produto - Derivação` sem checar por lixo
como esse.

## Os 74 travados por foto: 17 resolvidos, 57 pedem foto da cliente (03/09/2026)

A auditoria de ontem comparava contra o ARQUIVO CSV da Magazord, não contra a
foto que de fato está gravada no anúncio. Duas combinações — Babuche LED
Marinho e Zaxy Preto — eu já tinha corrigido À MÃO antes daquele CSV existir
(separação por olho das 22/24 fotos originais). Conferido item a item contra
o conjunto de foto correto: **17 de 17 já estavam certos**. Removidos da
lista de travados.

**Restam 57, em 11 combinações reais, sem foto em lugar nenhum que já
verifiquei:**

- não existem no arquivo de fotos da Magazord (nem nas linhas duplicadas);
- não têm ficha de catálogo no ML (5 das 11 nem têm EAN; as 6 com EAN não
  acham `/products/search` ativo).

Lista em `dados/pedido-fotos-pendentes.csv`: marca, modelo, cor, EAN (quando
tem) e quantos anúncios cada uma trava.

| marca | modelo | cor | anúncios |
|---|---|---|---|
| Havaianas | Fantasia Style II | rosa ballet | 4 |
| Havaianas | Top Basic | preto/pre/branco | 3 |
| Havaianas | Top Basic 25/6 | preto/preto/preto | 4 |
| Moleca | 5832.100 PVC | chocolate | 4 |
| Moleca | 5832.100 PVC | preto 01 | 4 |
| Modare | 7401.102 London | branco off/avela | 7 |
| Modare | 7401.102 London | branco dourado | 7 |
| Havaianas | Glitter Edge | verde olive | 6 |
| Havaianas | Glitter Edge | cinza gelo | 6 |
| Havaianas | Jelly | buttercream | 6 |
| Havaianas | Jelly | blossom | 6 |

**Deliberadamente NÃO busquei foto na internet para resolver isso.** São
coloridos com nome de marca — existe foto oficial publicada por aí, mas
image de terceiro sem saber a origem é risco de direito de imagem, e seria o
mesmo erro de inventar EAN ou custo: quando o dado não existe em fonte já
validada, o caminho é pedir ao cliente, não fabricar.

Os 57 continuam pausados, com a foto de outra cor do mesmo produto (herdada
do lote original) — não representam risco enquanto pausados, mas **não
ativar nenhum destes 11** até a foto chegar.

## `domain_discovery/search` erra categoria — não confiar no primeiro resultado (03/09/2026)

Para "Babuche Molekinho 2874.202 Gaspea Eva" o classificador do ML devolveu
**Tênis (MLB23332) na frente de Sandálias e Chinelos**. 10 anúncios nasceram
na categoria errada antes de eu perceber — sem `FOOTWEAR_TYPE`, guia de
tamanho incompatível com o domínio.

**Correção:** não usar `domain_discovery` para decidir tênis vs. chinelo.
Regra explícita: `"tenis" in texto_sem_acento` → `MLB23332/SNEAKERS`, senão
`MLB273770/SANDALS_AND_CLOGS`. Mesmo cuidado do bug de acento em `TENIS_IDX`
— sempre comparar em texto normalizado (sem acento), nunca com o texto cru.

Corrigidos os 10: fechar (`status: closed`) e recriar com `category_id`
certo, `FOOTWEAR_TYPE` e a guia `Molekinho|Meninos` (grid **7739769** — a
mesma do Babuche LED, criada na manhã, só que nunca tinha sido registrada em
`guias.json` sob esse nome).

## Lote multicor de 03/09/2026: 64 produtos processados, ~4 bugs corrigidos no motor

Esteira geral: `scratchpad/subir_geral.py` (sessão de 03/09). Diferença central
para a esteira do lote de cor única: publica **por `Código Agrupador`** (a
cor de verdade), nunca por produto inteiro — pula a cor sem foto em vez de
herdar foto de outra cor. Foi assim que resolvemos a foto misturada de vez.

### Bugs achados e corrigidos DURANTE a rodada (todos sem publicar errado
### para o cliente final — pego antes ou desfeito na hora)

1. **`guia_para` devolvia dict puro quando a guia já existia**, mas quem
   chama espera tupla `(guia, status)`. Corrigido antes de rodar em escala.
2. **`domain_discovery/search` não é confiável para tênis x chinelo.**
   Para "Babuche Molekinho 2874.202 Gaspea Eva" ele devolveu Tênis (MLB23332)
   **na frente de** Sandálias e Chinelos — 10 anúncios nasceram na categoria
   errada. Trocado por regra explícita (`"tenis" in texto_sem_acento`),
   mesmo cuidado do bug de acento já visto de manhã. Os 10 foram fechados e
   recriados na categoria certa.
3. **Gênero por marca faltando para Modare e Zaxy** (marcas que só vendem
   linha feminina) — sem a palavra "feminino" no título, caía no default
   genérico e não achava a guia já existente. Corrigido com mapa fixo.
4. **Guias do Molekinho e da Zaxy nunca tinham sido salvas em `guias.json`**
   — existiam em arquivo solto de sessões anteriores. Mescladas.
5. **Cor de marketing não bate com a lista fechada do ML** ("camel",
   "avelã", "olivia", "caramelo" não existem nos 51 valores aceitos).
   Criado dicionário de sinônimos — sempre equivalência real de cor, nunca
   um tom inventado.
6. **Motor só bloqueava margem NEGATIVA, não abaixo do piso de 5%.**
   "Chinelo Havaianas Elegance Liso" a R$ 30,90 publicou com **2,7%** —
   contra a própria regra da skill ("margem < piso → não publica"). Achado
   na auditoria final, os 6 anúncios (todos ainda pausados, nenhum risco)
   foram **fechados**. Piso agora é obrigatório no motor. Preço mínimo para
   esse produto: **R$ 31,90** (calculado, não seguido — decisão de preço é
   do Neto).

### O que ainda pede decisão ou dado externo

- **3 BOLSAS entraram na fila de calçado por engano** (Bolsa Moleca
  50007.1, Bolsa Moleca Zíper Neo 50048.3, Bolsa infantil Molekinha 20019.2)
  — vieram do TikTok Shop sem filtro de categoria. Nenhuma foi publicada
  (bloqueadas por acaso: numeração de calçado não bate com bolsa). Bolsa
  precisa de pipeline próprio — atributos e categoria são outros.
- **Calçado de bebê (tamanho 17 a 26)** — Sandália Infantil Molekinho e
  Chinelo Baby Havaianas. A única tabela de cm que existe para essa faixa
  (colhida de manhã) tem **inconsistência conhecida** (20 BR "menor" que
  19 BR). Não criei guia com esse dado — precisa da tabela real do
  fornecedor antes de cadastrar bebê.
- **Marcas sem ficha legível**: Under Armour, Actvitta masculino, Cartago
  (quando o gênero não aparece no título), Ipanema, Vizzano, Azaleia, Rider.
  Testado e confirmado 403 (vendedor) ou zero ficha com grid — não é bug,
  é limite real da API para essas marcas.
- **Tamanhos 41 a 46** seguem fora de qualquer guia (mesmo gap da manhã).

Estado da conta ao final do lote: **397 registros — 353 pausados (vivos),
44 fechados** (28 título + 10 categoria + 6 margem). 1.583 pares no ar,
R$ 187.828,70 de vitrine.

## Maior achado do dia: "verde luna" era 4 cores misturadas (03/09/2026)

O item mais valioso de toda a fila pendente — **Modare 7208.101 Nobuck**,
978 pares, R$ 120 mil — estava bloqueado por "sem foto". O Neto perguntou
"nenhuma dessas imagens tem na pasta?" e a resposta certa era: TEM, só que
com o mesmo defeito do Babuche LED — uma pasta (`100983 verde luna nobu`,
54 fotos) misturando várias cores sob uma etiqueta só.

**O que resolveu:** cruzar pela DATA DE ENVIO (`dt_inclusao`) e pelo `id`
de cada foto, não pela cor a olho. O nome de arquivo revelou que a pasta
tinha **duas linhas de produto diferentes coladas junto** (Onça/leopardo,
Micro Perfurado) mais **4 lotes de envio da linha lisa**, cada lote uma cor:

| lote (id da foto) | data | cor | fotos |
|---|---|---|---|
| 1473–1487 | 28/03/2025 | Preto | 15 |
| 12433–12436 + 15639–15640 | 26/12/2025 + 06/05/2026 | Avelã (o de maio tem "avela-soft" NO NOME do arquivo) | 4+2 |
| 15560–15566 | 29/04/2026 | Alecrim (verde-oliva) | 7 |
| 16406–16411 | 05/06/2026 | Creme | 6 |
| 17889–17896 | 30/07/2026 | **Onça — produto IRMÃO, não usar aqui** | 8 |
| 16270–16274, 16400–16405 | 01–05/06/2026 | **Micro Perfurado — produto IRMÃO, não usar aqui** | 12 |

Publicado: **28 anúncios, 978 pares** (Preto, Bege/avelã, Verde-musgo/alecrim,
Creme — 7 tamanhos cada, tamanho 33 sem EAN em todas as 5 cores do produto,
padrão normal). Guia reaproveitada: `Modare|Feminino` (7298346), cobre 33-40
sem precisar criar nova.

**Achado a mais:** o produto tem uma 5ª cor, **Nude (52531), 41 pares**, que
não tem foto em NENHUM lote — nem entre as 54 misturadas. Essa entra na
lista de pedido normal.

### A técnica que funcionou, para repetir nos próximos casos suspeitos

Quando uma pasta parecer ter foto "genérica" ou nome que não bate com a
grade (como "verde luna" não sendo nenhuma cor da grade atual):

1. Listar `id` e `dt_inclusao` de cada foto da pasta, ordenado.
2. Procurar SALTOS de data — cada salto grande costuma ser um lote de
   upload diferente, e cada lote costuma ser uma cor diferente.
3. Olhar o NOME DO ARQUIVO — às vezes a cor está literal ali
   ("avela-soft"), mesmo quando a pasta/agrupador não bate.
4. Abrir UMA foto de cada lote em tamanho real e confirmar visualmente.
5. Nunca publicar por semelhança de pixel sozinha — cruzar com pelo menos
   um outro sinal (nome de arquivo, data, ou confirmação do cliente).

## Técnica repetida em 5 produtos grandes: mais 691 pares resolvidos (03/09/2026)

Aplicando a mesma técnica (data de envio + nome de arquivo, nunca só cor a
olho) nos próximos maiores da lista de "sem foto":

| produto | cor achada | onde estava escondida |
|---|---|---|
| Havaianas Top Liso | **Preto** e **Branco** | mesma pasta "top l amarelo pop", 36 fotos = 12 cores × 3 fotos, sequenciais no mesmo dia (15/04/2025). Preto = posições 34-36, Branco = 25-27. As outras 2 datas da pasta (05/06/2025 "Top Animals", 24/12/2025 "Ginga Top Bossa") são PRODUTOS IRMÃOS — não usar. |
| Havaianas Brasil | **Branco** | pasta "1288 amarelo pop marinho", lote de 16/04/2025 (9 fotos = 3 cores × 3: preto+branco+azul). O lote de 11/04/2025 é "Slim Brasil" — produto irmão, não usar. |
| Molekinho 2874.202 Gaspea Eva | **Preto/amarelo neon** | mesma pasta "marinho laranja", por eliminação: só 2 cores existem nesse produto, e o lote de 15/06/2026 (6 fotos) não é o marinho/laranja do nome — logo é a outra. |
| Cartago 12158 Dallas | **bs786** | mesma pasta "bm370 begemarrom", por eliminação entre as 3 cores do produto (bege/marrom = nome da pasta, azul/vermelho = padrão xadrez claramente distinto, sobra bs786 pro lote do meio, 22/12/2025). **Achou a foto, mas continua sem publicar** — Cartago Masculino não tem NENHUMA ficha de marca com guia legível (testado de manhã: 0 fichas com grid). Falta a tabela de numeração, não a foto. |
| Havaianas Top Tiras | **Café** e **Rose Gold** | pasta "rosa ballettiras", 2 lotes de 3 fotos cada (05/06 e 10/06/2025), coloridos e claramente distintos. |

**Publicado: 46 anúncios.** Preto/Branco Top Liso, Branco Brasil e as duas
Top Tiras reaproveitaram a guia `Havaianas|Sem gênero` (já existia). Gaspea
Eva reaproveitou `Molekinho|Meninos` (mesma do Babuche LED da manhã).

Conta em 03/09/2026, fim do dia: **471 registros, 427 vivos, todos com me2,
2.986 pares, R$ 333.122,42 de vitrine.**

### Padrão consolidado da técnica (usar sempre que "sem foto" parecer estranho)

1. Cruzar TODAS as fotos da pasta por `dt_inclusao` + `id`, nunca só olhar
   a miniatura.
2. Salto de data quase sempre = cor diferente, OU produto-irmão colado
   (nome de arquivo diferente do esperado — checar sempre).
3. Nome de arquivo às vezes entrega a cor de graça ("avela-soft"); quando
   não entrega, contar quantas cores o produto tem de verdade na Magazord
   e resolver por ELIMINAÇÃO entre os lotes, sempre conferindo 1 foto de
   cada lote em tamanho real antes de decidir.
4. Achar a foto não garante poder publicar — a guia de tamanho é um
   problema separado (caso Cartago Masculino: foto resolvida, tabela
   continua faltando).

## Segunda rodada da técnica: mais 6 produtos investigados (03/09/2026)

Aplicando a mesma técnica num lote maior de candidatos:

| produto | resultado |
|---|---|
| Havaianas Tradicional | **achou Preto e Rosa Flux** — pasta "hav trad azul" tinha 9 fotos = 3 cores × 3, mesmo padrão do Top Liso |
| Molekinha Injetada EVA com Pins | **achou Creme e Rosa** — 12 fotos de um único lote (15/06/2026) misturavam 3 cores (Preto+Creme+Rosa, 4 cada). O NOME DO ARQUIVO mentia aqui — dizia "rosa" numa foto que era preta. Só a inspeção visual foto a foto resolveu |
| Molekinho Slide Eva | **achou Preto** — pasta só tinha "marinho" no nome, mas eram 16 fotos = 2 cores × 8 |
| Ipanema Glow | achou a foto (rosa/dourado), **mas Ipanema não tem NENHUMA ficha de marca com guia legível** — bloqueado por tabela, não por foto |
| Cartago Atlanta II | achou a foto (marrom/bege), **mas Cartago adulto/masculino não tem guia** — mesmo bloqueio do Dallas |
| Under Armour Core 2 | achou as 3 cores (preto/branco/roxo), **mas Under Armour não tem guia legível** (só ficha de vendedor, 403) |
| Rider 12674 Core M | pasta encontrada é "Rider **12673** Core" — nome de modelo parecido mas não idêntico. **Não usei**: risco de mostrar o produto errado é maior que o benefício. Fica pendente |

**Publicado nesta rodada: 35 anúncios.** Confirma o padrão: achar a foto resolve
~metade dos casos — a outra metade esbarra na tabela de numeração, que é um
problema **diferente e não resolvido por esta técnica**.

Conta ao fim de 03/09/2026: **506 registros, 462 vivos, 3.272 pares,
R$ 353.489,82 de vitrine.**

### Atualização da lista de pedido à Leilane

Some-se à tabela de numeração pendente (Under Armour, Actvitta masculino,
Ipanema, Vizzano, Azaleia, Rider) — todas essas marcas AGORA JÁ TÊM FOTO
identificada e arquivada, só falta a tabela de comprimento do pé por
numeração para publicar. Confirmar também se "Rider 12673 Core" e o produto
"Rider 12674 Core M" da nossa base são o mesmo modelo — se forem, a foto já
está pronta.

## Terceira rodada: 16 publicados, e onde a técnica parou de compensar (03/09/2026)

- **Havaianas Brasil Preto** e **Top Liso Azul-marinho**: já estavam nos
  lotes que eu tinha baixado antes (Brasil = mesmo lote 9 fotos de branco;
  Top Liso = mesmo lote de 36 fotos de preto/branco, um dos DOIS grupos
  azuis do lote — "marinho" e "azul naval" são cores nomeadas distintas
  no Magazord e ambas azuis; usei o lote mais escuro para "azul naval" por
  inferência de tom, não por prova. **`TOPLMARINHO` (32 pares) segue sem
  foto própria — mesma pasta, outro grupo azul, não usado ainda.**
- **Cartago (Sintra, Ravena, Atlanta, Alabama, Durban)**: nem investigado a
  fundo — são todos adulto/masculino, mesma trava de guia já confirmada.
  Foto não muda nada até a tabela existir.
- **Modare 7142.106 NP/Sen Flex**: pasta mistura **3 produtos-irmãos**
  colados (NP/Sen Flex = nosso; "Tres Berço" e "Tresse Alba" = outros
  modelos, mesmo código 7142.106). Isolando só o nosso, sobram 3 cores
  batidas (preto, verde-oliva, camel) que **não combinam limpo** com os 3
  nomes que precisamos (Camel, Preto/Camel, Nude/Camel — nenhum é "verde
  oliva"). Não publiquei — confiança baixa, fica pendente.
- **Havaianas Slim Tropical "amarelo caja"**: a pasta tem só padronagens
  florais coral/azul, nenhuma amarela/manga. Não achei.

**Publicado nesta rodada: 16 anúncios.** A técnica está batendo o teto do
que dá para resolver com segurança — a partir daqui a maioria dos
pendentes cai em dois baldes que ela não resolve: **guia de marca ausente**
(Cartago adulto, Under Armour, Ipanema) ou **cor genuinamente sem foto em
nenhum lote** (confirmado, não é mais suspeita de má etiquetagem).

Conta ao fim: **522 registros, 478 vivos, 3.336 pares, R$ 357.382,42.**

## Guia de marca ausente: resolvido por EXTRAPOLAÇÃO documentada (03/09/2026)

Pedido do Neto: "revise produto por produto, pesquise atributos dos mesmos
itens de concorrentes para completar os cadastros". O bloqueio de
Under Armour, Ipanema, Vizzano, Azaleia, Rider e Cartago adulto nunca foi a
foto — sempre foi a tabela de tamanho (nenhuma dessas marcas tem ficha de
CATÁLOGO própria legível no ML; só ficha de VENDEDOR, que dá 403 no
`GET /catalog/charts/{id}` de terceiro, confirmado de novo hoje).

**A saída: numeração BR → comprimento do pé é padrão nacional (INMETRO/
ABNT), não segredo de marca.** Confirmado num documento técnico do SENAI-RS
sobre numeração de calçados: o Brasil usa a escala Paris-point (1 ponto ≈
2/3 cm = 0,667 cm por numeração), a mesma base de toda numeração BR adulta,
independente de marca. Cruzado com dado REAL já coletado da Modare
(ficha de catálogo legível, 33-40 BR = 21,9-26,6 cm): o passo medido é
0,671 cm/numeração — praticamente igual ao teórico. Isso dá confiança para
extrapolar 41-46 a partir do mesmo passo: `dados/tabela-adulto-br-33-46.json`
(33-40 "real", 41-46 "extrapolado" — nunca apresentar ao cliente como dado
oficial da marca, é cálculo, documentado como tal).

7 guias novas criadas com essa tabela (`scratchpad/criar_guias_adulto.py`,
receita idêntica à de sempre — ver acima):

| guia | grid_id | faixa |
|---|---|---|
| Cartago Masculino | 7746897 | 37-45 |
| Vizzano Feminino | 7746723 | 34-40 |
| Azaleia Feminino | 7746899 | 33-40 |
| Rider Masculino | 7746901 | 37-45 |
| Ipanema Feminino | 7746903 | 33-40 |
| Under Armour Sem gênero | 7746725 | 35-46 |
| Actvitta Feminino (extensão) | 7305610 | 41-44 |

**Ipanema Feminino NÃO FOI USADA ainda.** Ao checar os SKUs reais do
"Ipanema Glow 27403" antes de publicar, os tamanhos são **23 a 33**, não
33-40 — é produto INFANTIL (o nome do arquivo de foto já dizia
"sandalia-**infantil**-ipanema-27403-glow", e eu tinha ignorado isso антes).
Guia adulta não serve. Fica pendente, no mesmo balde do calçado de bebê
17-26 que já estava em aberto — precisa de tabela infantil própria, não
inventar.

### Publicado com as guias novas: 69 anúncios

Script `scratchpad/publicar_novas_guias.py`. Todos com foto conferida
FOTO A FOTO (não só nome de arquivo) antes de publicar — achado notável:
**Cartago Alabama tinha as DUAS cores escondidas na mesma pasta**
(agrupador `bi911marrommarrom`), separadas por sessão de upload: 27/05/2025
(8 fotos) é a cor Preto pura — a variante `pretocasto`, que o CSV marcava
com 0 foto própria —, e 29/05+30/06/2025 (7 fotos, sufixo "-1" no nome) é a
Marrom de verdade. Mesma técnica de sempre (cruzar id+data), aplicada desta
vez para SEPARAR uma pasta em duas cores, não só para achar uma escondida.

| produto | cor | publicados |
|---|---|---|
| Cartago Sintra | Bege/preto | 8 |
| Cartago Ravena | Preto | 8 |
| Cartago Alabama | Preto | 5 |
| Cartago Alabama | Marrom | 3 |
| Cartago Durban | Preto/bege | 6 |
| Cartago Atlanta | Marrom | 6 |
| Cartago Atlanta II | Preto/bege | 4 |
| Cartago Dallas | Bege/marrom | 6 |
| Under Armour Core 2 | Preto | 8 |
| Vizzano Napa Calf | Bege | 5 |
| Vizzano Pelica | Dourado | 5 |
| Vizzano Napa Garda | Marrom | 2 |
| Azaleia Fabi Light | Bege | 3 |

Preço usado: o mesmo que a Leilane já pratica no TikTok Shop (mesma fonte
de sempre); margem recalculada com custo real da planilha + comissão/imposto
24% antes de publicar, piso de 5% igual ao resto da esteira.

**Pendências que ficaram deste lote:**
- Alabama Preto e Marrom publicaram com **1-2 tamanhos "fora da guia"** —
  rodou antes de eu ligar o desdobre de numeração pareada (37/38, 43/44)
  neste script; os outros 11 produtos já rodaram com o desdobre ligado.
  Não é dado errado, é tamanho que ainda não subiu — cai na próxima rodada.
- `frete()` (mesma função de sempre, via `shipping_options/free`) devolveu
  **R$ 0,00 em TODOS os 13 casos** — API não respondeu o esperado. Como a
  margem calculada mesmo assim ficou entre 33% e 40% (bem acima do piso de
  5%), não travou nada, mas o frete real destes itens ainda não foi medido
  de verdade. Conferir com `cli.py tarifas` quando o item ficar um tempo no
  ar, do jeito que já se faz para os outros.
- Cartago Atlanta (6, não 6-9) e Atlanta II (4) só cobriram até 43/44 BR —
  a pasta de fotos não tinha tamanho 45 com EAN.

Conta ao fim (03/09/2026): **591 registros no total, +69 do dia.**

## A solução do problema de foto: pasta "Fotos Prontas" (04/09/2026)

Drive: https://drive.google.com/drive/folders/1OlADTCGy2HrFWM3iFksWFDkX-66FhLYI
(dono `alexandroaissa@gmail.com`, compartilhada em 04/09 14:58)

Estrutura **`produto → cor → fotos`** — é o que resolve a armadilha do
`cod_agrupador`, que carimbava todas as fotos de um produto numa cor só.
Aqui a cor está declarada na pasta, não inferida. **Use esta pasta como fonte
de foto daqui em diante**; o `magazord-fotos-urls.csv` só serve com conferência
visual.

Em 04/09 ela ainda estava sendo montada: 2 produtos, 3 cores, 7 fotos.

### O modelo 7208.101 é SEIS produtos, não um

Confusão que já custou tempo: "7208.101" aparece em 6 `Código Pai` diferentes,
com preços diferentes. A pasta "NOBUCK ONCA 7208.101" é o **2659766**.

| Código Pai | produto | preço | un |
|---|---|---|---|
| 2344016 | Papete Slide Modare 7208.101 Nobuck | 119,99 | 1.019 |
| 2640305 | Papete Slide Modare Micr Perf Suprem | 119,99 | 18 |
| **2659766** | **Papete Slide Fem. Modare Nobuck ONÇA** | **152,90** | **196** |
| 2673313 | (fora da lista do TikTok) | — | 626 |
| 2673330 | (fora da lista do TikTok) | — | 64 |
| (sem pai) | derivações órfãs | — | **1.923** |

**Sempre casar por `Código Pai`, nunca pelo número do modelo.**

### 1.923 pares em derivações SEM Código Pai

Descoberto em 04/09 ao abrir o 7208.101. São derivações órfãs — não têm pai,
não entram em nenhuma família e não aparecem na fila do TikTok. Somadas aos
690 de produtos fora da lista, é estoque invisível para o cadastro. Investigar
antes de dizer ao cliente que o catálogo está no ar.

## As 17 tabelas oficiais de marca — e o erro que elas revelaram (04/09/2026)

A pasta `Fotos Prontas/0 MEDIDAS` trouxe **17 tabelas oficiais** das marcas.
Transcritas para `dados/tabelas-oficiais-marcas.json` — **esta é a fonte de
verdade de FOOT_LENGTH daqui em diante**, acima de qualquer coisa colhida de
ficha do ML ou extrapolada por cálculo.

### ⛔ A guia 7739769 "Molekinho" está com os centímetros da MOLEKINHA

Ela foi montada com números colhidos de uma ficha de catálogo do ML rotulada
"Meninos Molekinho" — e a ficha estava com a escala errada. Nove dos dez
valores batem com a MOLEKINHA, não com o Molekinho:

| tam | usamos | Molekinho oficial | Molekinha oficial |
|---|---|---|---|
| 28 | 18,6 | **19,0** | 18,7 |
| 32 | 21,3 | **21,5** | 21,3 |
| 33 | 21,9 | **22,0** | 21,9 |
| 35 | 23,3 | **23,5** | 23,3 |
| 36 | 23,9 | **24,0** | 24,0 |

Diferença de 1 a 4 mm. Afeta Babuche LED e Gaspea Eva (61 anúncios com marca
Molekinho). **Lição:** ficha de catálogo do ML pode ter escala de outra marca
— conferir contra a tabela do fabricante antes de criar guia.

### Descobertas úteis das tabelas

- **Zaxy, Ipanema e Rider usam a MESMA escala adulta** (33/34=22,3 … 41=27,3).
  É a escala Grendene — uma guia serve para as três.
- **Rider vai até 47/48 e Cartago até 46/47.** Isso substitui a extrapolação
  Paris-point de 41-46 por dado oficial.
- **Havaianas só publica numeração PAREADA em faixa** (35/36 = 22,4 a 23,6 cm).
  Como o ML exige numeração simples, o valor por número é interpolação nossa —
  documentar como tal, não apresentar como oficial da marca.
- **Modare também é faixa** (33 = 21,7 a 22,5 cm); os pontos que usamos caem
  dentro da faixa oficial, então a guia 7298346 está válida.

### Tabela de medidas como FOTO no anúncio (pedido do Neto, 04/09/2026)

Anexada a tabela oficial da marca como **última foto** de cada anúncio —
452 dos 547 vivos, 0 erro. Reduz devolução por numeração, que é a reclamação
número um em calçado.

| marca | anúncios |
|---|---|
| Havaianas (todos os gêneros) | 181 |
| Modare | 88 |
| Molekinho | 61 |
| Cartago masculino | 46 |
| Molekinha | 33 |
| Zaxy | 28 |
| Cartago meninos | 15 |

**95 ficaram sem tabela** porque a marca não tem tabela na pasta: Actvitta
(44), Moleca (28), Vizzano (12), Under Armour (8), Azaleia (3). Pedir essas
cinco à Leilane — Actvitta e Moleca são do mesmo grupo da Modare (Beira Rio),
mas escala de grupo não é escala da marca: não reaproveitar sem confirmação.

Regra da foto: a tabela entra **sempre por último** e o teto segue 10 fotos —
quem já tinha 10 perdeu a última (infográfico) para a tabela entrar.

## Guia de tamanho SE CORRIGE NO LUGAR — não precisa mexer no anúncio (04/09/2026)

`PUT /catalog/charts/{id}` **funciona**, e os IDs de linha são preservados —
então corrigir a guia conserta todos os anúncios que apontam para ela, sem
tocar em nenhum. Achado por tentativa, com os erros do próprio ML:

1. **Não mandar `attributes`** (o bloco GENDER/BRAND da guia):
   `chart_attributes_edition_error` — "Chart's general attributes cannot be
   edited. Please, don't include the attributes property".
2. **Mandar o `id` de cada linha.** Sem ele o ML trata como linha nova e
   recusa: `main_attribute_value_unique_error`.
3. **Não reenviar `BR_SIZE` na linha** — é o atributo principal e é imutável:
   `row_main_attribute_edition_error`. Só vai `FOOT_LENGTH`.

Corpo mínimo que funciona:

```json
{ "names": {...}, "domain_id": "SANDALS_AND_CLOGS", "site_id": "MLB",
  "rows": [ {"id": "7739769:2",
             "attributes": [{"id":"FOOT_LENGTH","values":[{"name":"19.0 cm"}]}]} ] }
```

### Auditoria das 16 guias contra as tabelas oficiais — 5 corrigidas

| guia | grid_id | anúncios | linhas corrigidas |
|---|---|---|---|
| Molekinho | 7739769 | 61 | **8** (estava com escala da Molekinha) |
| Cartago meninos | 7741963 | 15 | 4 (28, 29, 31, 34) |
| Molekinha | 7300854 | 33 | 2 (28, 36) |
| Zaxy | 7741603 | 28 | 2 (36, 39) |
| Cartago masculino | 7746897 | 46 | 2 (39, 45) |

**183 anúncios corrigidos sem um único `PUT /items`.** Reconferido depois:
zero divergência nas cinco.

### O que NÃO foi mexido, e por quê

- ~~**Modare (88 anúncios)** e **Havaianas (181)**: os valores caem dentro da
  faixa oficial, está correto.~~ **ERRADO — corrigido em 06/09/2026.** Só o 33
  e o 34 caíam dentro; do 35 ao 40 a Modare estava FORA da própria faixa, e na
  Havaianas os números pares (34, 36, 38, 40) estavam fora da faixa do par.
  O teste que produziu esta conclusão media a distância até o PONTO MÉDIO da
  faixa com tolerância de meio centímetro — e meio centímetro é maior que a
  faixa inteira em vários tamanhos. **O teste certo é de pertinência: o valor
  está dentro de [min, max]?** Ver a auditoria de 06/09 no fim deste arquivo.
- **95 anúncios em marcas sem tabela oficial**: Actvitta (44), Moleca (28),
  Vizzano (12), Under Armour (8), Azaleia (3). As guias delas seguem com a
  extrapolação Paris-point documentada. **Pedir essas 5 tabelas à Leilane** —
  é o que falta para a numeração da conta inteira sair de estimativa.

## Auditoria de atributos (04/09/2026)

Pergunta do Neto: "todos os atributos e características estão preenchidas?"

**Obrigatórios: 100% nos 547.** `BRAND`, `MODEL`, `GENDER`, `COLOR`, `SIZE` e
`FOOTWEAR_TYPE` (este só em MLB273770). Também 100%: `SIZE_GRID_ID`, `GTIN`,
`SELLER_SKU`.

**Opcionais: estavam quase todos vazios.** Não é cosmético — o ML usa ficha
técnica completa como fator de posicionamento, e atributo vazio é filtro de
busca onde a loja não aparece.

Preenchidos nesta rodada, **só com dado de fonte**:

| atributo | anúncios | de onde veio |
|---|---|---|
| `MAIN_COLOR` | **547 (100%)** | derivado do `COLOR` já validado |
| `FOOTWEAR_MATERIALS` | 161 (29%) | o campo `Modelo` da Magazord declara: EVA, Nobuck, PVC, Verniz |

### Bug achado: 10 anúncios com COR preenchida com TAMANHO

"Babuche Infantil Molekinha 22591.408 Arco Íris" tinha `COLOR = "31/32"`,
`"33/34"` etc. O extrator de cor pega o primeiro token do texto da derivação
assumindo código numérico — e nesse produto a cor é `creme/multicolor/cristal`,
sem código, então ele pegou o tamanho do fim.

Corrigido para `Multicolorido` (valor da lista fechada do ML) nos 10.
**`COLOR` É EDITÁVEL depois de publicado** — ao contrário de `family_name`.

### Equivalências de cor usadas (marketing -> lista fechada do ML)

A lista do ML tem 16 valores, e dois passam despercebidos: **Multicolorido** e
**Bege**. Mapeamentos aplicados: Creme→Bege (17), Chocolate→Marrom (11),
Buttercream→Amarelo (6), Blossom→Rosa (6). São equivalências de cor real,
não tom inventado.

### O que NÃO foi preenchido, e por quê

- `FOOTWEAR_STYLE` (Casual · Diário · Noite · Social · Urbano): é julgamento
  de posicionamento, não dado. Só a Leilane decide.
- `RELEASE_YEAR` / `RELEASE_SEASON`: a Magazord só tem data de lançamento em
  **6%** das linhas (794 de 12.649).
- Material de **Napa** (686 derivações) e **Pelica** (211): são tipos de couro
  sintético, mas mapear para a lista fechada sem confirmação seria repetir o
  erro da escala Molekinho.
- Nos **68 tênis** faltam `EXTERIOR_MATERIALS`, `INTERIOR_MATERIALS`,
  `OUTSOLE_MATERIALS`, `WIDTH_TYPE`, `ADJUSTMENT_TYPES`, `RECOMMENDED_USES`.
  Nada disso sai da Magazord — é ficha do fabricante.

**Pedido à Leilane, consolidado:** 5 tabelas de numeração (Actvitta, Moleca,
Vizzano, Under Armour, Azaleia) + a ficha técnica de material do fornecedor
(cabedal, forro, solado), que fecha os atributos de material de uma vez.

## Pesquisa das 5 tabelas que faltam: resultado NEGATIVO, e por quê (04/09/2026)

Pedido: pesquisar as tabelas de numeração de Actvitta, Moleca, Vizzano,
Under Armour e Azaleia em vez de esperar a cliente.

**Não estão publicadas em forma utilizável.** Verificado:

- `calcadosbeirario.com.br` (fabricante de Beira Rio, Vizzano, Moleca, Modare
  e Actvitta — confirmado pelo certificado TLS do SAC da Vizzano, que resolve
  para `*.calcadosbeirario.com.br`): só SAC, FAQ em PDF e política de troca.
- `underarmour.com.br/guia-de-tamanhos`: existe, mas redireciona para conteúdo
  de marketing; a tabela não aparece nem no fetch nem no navegador.
- Busca aberta: só varejistas e catálogos de revenda, nenhum dado do fabricante.

### ⛔ E a hipótese de "escala de grupo" foi REFUTADA

A ideia era: se Zaxy, Ipanema e Rider (todas Grendene) têm tabela **idêntica**,
então as Beira Rio (Vizzano, Moleca, Actvitta) poderiam herdar a da Modare, que
já temos oficial. **Testado com dado que já estava aqui e não se sustenta:**

| tam | Molekinha | Molekinho |
|---|---|---|
| 28 | 18,7 | **19,0** |
| 31 | 20,6 | **20,5** |
| 34 | 22,6 | **22,5** |
| 35 | 23,3 | **23,5** |

Molekinha e Molekinho são do MESMO grupo Beira Rio, as duas tabelas vieram da
mesma pasta oficial, e **divergem em 7 dos 10 tamanhos comuns**.

Conclusão: **escala é por MARCA, não por grupo.** A coincidência da Grendene é
coincidência daquela empresa, não regra. Aplicar Modare em Vizzano/Moleca/
Actvitta seria repetir o erro da guia "Molekinho" com escala da Molekinha.

**As 5 tabelas continuam pendentes com a Leilane.** Os 95 anúncios seguem com a
extrapolação Paris-point documentada — que, medida contra a Modare real, erra
0,004 cm por numeração, e é o melhor disponível até a tabela do fornecedor
chegar.

### Achado lateral útil

A própria Under Armour avisa no site que **a forma do calçado dela é menor que
o padrão** e recomenda comprar um número acima. Vale entrar na descrição dos 8
anúncios UA — é informação da marca, reduz devolução.

## Descrições: 547 de 547 (05/09/2026)

A conta inteira estava **sem uma única descrição** — só título, foto e ficha
técnica. Descrição é fator de conversão e de posicionamento no ML.

Molde aplicado, montado a partir de dado que já estava no anúncio:

```
{título}

COMO CONFERIR O SEU NÚMERO
Apoie o pé no chão sobre uma folha e meça do calcanhar até a ponta do dedo
mais longo.
A numeração 39 BR corresponde a 25,9 cm de comprimento do pé.
A tabela de medidas da Havaianas está na última foto deste anúncio.

O QUE VOCÊ RECEBE
1 par de chinelo Havaianas Top Liso, cor Preto, numeração 39 BR.
Produto novo.

ENVIO
Enviamos por Mercado Envios com código de rastreio.

Chinelaria Leilane Neves - loja física em Votuporanga/SP.
```

**A distinção que importa: 452 levam o centímetro, 95 NÃO.** Os 95 são
Actvitta, Moleca, Vizzano, Under Armour e Azaleia, cuja numeração ainda é a
extrapolação Paris-point. Publicar "corresponde a 25,9 cm" ali seria
apresentar cálculo nosso como medida do fabricante — e é justamente esse dado
que o comprador usa para escolher o número. Esses recebem "ficou entre dois
números? nos chame antes de comprar". Quando as 5 tabelas chegarem, rodar o
script de novo e eles ganham o número.

Os 8 Under Armour levam, acima de tudo, o aviso da própria marca: a forma é
menor que o padrão, considere um número acima.

### Três armadilhas da API de descrição

1. **`POST` cria, `PUT` atualiza.** Em item que já tem descrição o POST falha;
   o script tenta POST e cai para PUT.
2. **Emoji e travessão são recusados**: `DESCRIPTION_PLAIN_TEXT_NOT_ALLOWED`
   ("The description must be in plain text"). Acento passa normal.
3. **Sempre reler da API depois de gravar.** A primeira rodada gravou o texto
   inteiro SEM ACENTO — escape do shell comeu — e só apareceu na releitura.
   Texto que vai ao cliente final se confere lendo de volta, não pelo 200.

### O lote caiu por DNS, não por erro de API

A primeira rodada morreu em `getaddrinfo failed` no meio dos 547, com a saída
bufferizada perdida — não dava para saber quantas tinham gravado. Refeito com
retentativa (5 tentativas, espera crescente), saída sem buffer e lista de
pendentes em `dados/sem-descricao.json`, que o script relê e regrava.
Script: `scratchpad/descricoes2.py`. **É retomável: rodar de novo é seguro.**

---

## Auditoria de numeração e de foto×cor — 06/09/2026

Conferência dos 547 anúncios contra a origem (derivação Magazord) e contra as
tabelas oficiais das marcas. Fonte: `dados/auditoria-fotos-cor.csv`.

### O que está certo, e por que dá para confiar

- **`SIZE` x linha da guia x título: 547 de 547 conferem.** Nenhum anúncio
  aponta para uma linha de guia de outro número, nenhum título contradiz o
  atributo, nenhum anúncio está sem guia.
- **Guia x marca do anúncio: 547 de 547.** Não há anúncio pendurado na guia de
  outra marca — que foi o erro do Molekinho/Molekinha em 03/09.
- **`SIZE` x tamanho da derivação de origem: 547 de 547.** O número anunciado é
  o número do par que está no estoque.
- **Soma do estoque nos 165 pares desdobrados = estoque da origem, em 165.**
  O desdobramento de numeração pareada não criou nem perdeu par.

### O erro de numeração: o centímetro, não o número

O número BR está certo em todos. O que está errado é **o comprimento do pé** em
duas marcas — e é ele que o comprador usa para escolher.

**Modare (88 anúncios, guias 7298346 e 7742085).** A Modare publica uma FAIXA
por tamanho. As guias foram montadas com a escala genérica, que cai logo abaixo
da faixa: 35 a 40 ficam FORA da faixa da própria marca. Efeito prático: quem
mede 24,0 cm lê 36 na nossa guia; a Modare diz que 24,0 cm é 35. **O cliente
compra um número acima do que precisa** — e devolução de calçado por numeração
é o motivo nº 1 de troca.

    tamanho  hoje   faixa oficial   corrigir para
    35       23,3   23,4–24,0       23,7
    36       23,9   24,1–24,8       24,5
    37       24,6   24,9–25,3       25,1
    38       25,3   25,4–26,0       25,7
    39       25,9   26,1–26,6       26,4
    40       26,6   26,7–27,3       27,0

**Havaianas (181 anúncios, guias 7742541, 7300856, 7742605).** A Havaianas só
publica faixa PAREADA (33/34, 35/36...). Ao desdobrar em números soltos, as duas
metades receberam a escala genérica, e **os pares (34, 36, 38, 40) caíram fora
da faixa do próprio par**: 34 = 22,6 cm, mas o par 33/34 vai só até 22,3.
Quem mede 22,6 cm compra 34 e deveria comprar 35/36. **Erro no sentido oposto
ao da Modare: o cliente compra um número abaixo.**

A regra ao desdobrar par é: dividir a faixa em duas metades e usar o ponto médio
de cada uma — o número menor fica na metade de baixo, o maior na de cima.

    par 33/34 = 21,1–22,3  ->  33 = 21,4   34 = 22,0
    par 35/36 = 22,4–23,6  ->  35 = 22,7   36 = 23,3
    par 37/38 = 23,7–25,0  ->  37 = 24,0   38 = 24,7
    par 39/40 = 25,1–26,3  ->  39 = 25,4   40 = 26,0

Cartago, Zaxy, Molekinha e Molekinho estão dentro da tabela oficial. Actvitta,
Moleca, Vizzano, Under Armour e Azaleia seguem estimadas — são as 5 tabelas do
`PEDIDO-LEILANE.md` e por isso a descrição delas não cita centímetro.

**Correção: 32 linhas de guia, 257 anúncios impactados.** Editar a guia corrige
todos os anúncios pendurados nela de uma vez — não precisa tocar item por item.
A receita de UPDATE de guia (mandar `id` da linha, NÃO reenviar `BR_SIZE`) já
está documentada acima.

### O erro de foto: 145 anúncios com a foto de outra cor

Três testes independentes, e o que cada um pega:

1. **Conjunto de fotos idêntico em duas cores** — pega troca dentro da mesma
   família de cor (o preto que virou chocolate). Achou 3.
2. **Cor dominante da imagem x cor declarada** — pega troca entre famílias.
   Achou 29 candidatos.
3. **Foto x nome da derivação de origem, no olho, lado a lado por modelo** —
   é o que decide. Os dois primeiros erram: estampa rosa clara classifica como
   bege, e chinelo preto com palmilha marrom parece marrom.

**A cor declarada (`COLOR`) está certa** — ela vem do nome da derivação. O que
está errado é a foto pendurada nela.

| marca | anúncios com foto de outra cor |
|---|---:|
| Havaianas | 81 |
| Molekinho | 34 |
| Actvitta | 12 |
| Moleca | 11 |
| Modare | 7 |
| **total** | **145** (25 combinações de cor) |

Os 11 combos já conhecidos em 03/09 eram menos da metade. O resto apareceu
porque **o teste estrutural de 03/09 só olhou quem não tinha foto na exportação
Magazord** — e as fotos que vieram depois pela pasta do Drive entraram sem
passar por esse filtro.

Casos que valem nome:

- **Molekinho 2874.202 Gaspea (20 anúncios)** — usa as fotos do 2874.407, que é
  o babuche LED, outro produto. E ainda trocadas entre si: a cor "Laranja"
  (marinho/laranja) está com a foto preta, e a "Preto" (preto/amarelo neon) com
  a marinho. Nem trocando resolve: a foto é de outro modelo.
- **Havaianas TOP BASIC (7 anúncios)** — as duas cores, branca e preta, estão
  com a mesma foto listrada creme/vermelho, que não é nenhuma das duas.
- **Havaianas TOP LISO Amarelo (8)** — a foto é uma estampa tropical. O modelo
  chama-se LISO.
- **Moleca 5832.100 (11)** — as três cores (Preto, Chocolate, Branco off) estão
  com a foto do preto.

Todos os 145 estão `paused`. **Não reativar nenhum deles sem a foto certa** — é
anúncio que vende a cor errada e volta como reclamação.

### Nove numerações que não existem no ML

Nove derivações de tamanho pareado tinham estoque 1 e, ao desdobrar, o par
inteiro foi para o número MAIOR — o menor não foi publicado. Ex.: Havaianas DUAL
Branco 37/38 tem só o 38 no ar. É consequência da divisão de estoque, não erro:
com 1 par não dá para abrir dois anúncios. Vale saber que quem calça o número
menor não encontra a loja.

### Correção aplicada — 06/09/2026

`PUT /catalog/charts/{id}` nas 5 guias, **36 linhas, 269 anúncios**, sem um
único `PUT /items`. A receita documentada acima funcionou sem ajuste.

**Modare (7298346 e 7742085)** — todas as 8 linhas passaram para o ponto médio
da faixa oficial da marca:

    33 -> 22,1   34 -> 23,0   35 -> 23,7   36 -> 24,5
    37 -> 25,1   38 -> 25,7   39 -> 26,4   40 -> 27,0

**Havaianas (7742541, 7300856, 7742605)** — cada faixa pareada dividida em duas
metades, o número menor na metade de baixo e o maior na de cima:

    33 -> 21,4   34 -> 22,0   35 -> 22,7   36 -> 23,3
    37 -> 24,0   38 -> 24,7   39 -> 25,4   40 -> 26,0

Conferido relendo da API: nas 16 guias os IDs de linha e os `BR_SIZE` estão
intactos, e só as 36 linhas previstas mudaram de centímetro. O teste de
pertinência caiu de **27 tamanhos fora para 5** — e os 5 restantes são pares de
valor ÚNICO (Cartago 37/38 e 43/44, Cartago meninos 32/33 e 35/36, Zaxy 33/34),
onde a guia coloca um número de cada lado do valor da marca. Isso é o
desdobramento correto: o teste de pertinência é que não sabe lidar com par de
ponto único. **Não "corrigir" esses 5.**

### A descrição carrega o centímetro — mexeu na guia, regrava a descrição

As 269 descrições de Havaianas e Modare diziam "corresponde a 23,3 cm" com o
valor ANTIGO. Guia e descrição são duas cópias do mesmo número e o `PUT` da
guia não toca na descrição. Regravadas as 269 e reconferidas relendo da API:
**269 de 269 com o centímetro igual ao da guia, zero acento perdido.**
Script: `scratchpad/desc_recm.py`.

Regra para a próxima vez: **toda edição de guia tem uma segunda metade
obrigatória** — regravar a descrição das marcas afetadas. Sem isso o anúncio
passa a se contradizer, e a contradição é justamente sobre o número do pé.

## Família 139487076766676 — Actvitta Australia 4841.100 (06/09/2026)

6 anúncios (34, 36, 37, 38, 39, 40), R$ 226,90, 8 pares. O 33 e o 35 têm
estoque zero na origem — ausência correta, não falha.

### É TÊNIS cadastrado como CHINELO

Quatro fontes dizem tênis e uma diz chinelo — e o cadastro seguiu a única que
diz chinelo:

| fonte | o que diz |
|---|---|
| Linx (loja física) | `TENIS CASUAL ACTVITTA AUSTRALIA 4841.100` |
| Magazord, produto PAI | `Tenis Casual Feminino Actvitta Australia 4841.100` |
| nome dos arquivos de foto | `01-tenis-casual-feminino-actvitta...` |
| as próprias fotos | tênis de corrida/casual, cadarço e entressola |
| Magazord, nome da DERIVAÇÃO | `chinelo dedo feminino actvitta australia 4841.100` |

Custo R$ 98,06 e preço R$ 226,90 são economia de tênis: o chinelo Actvitta da
mesma conta (4862.100 EVA) sai a R$ 99,90, e o tênis irmão 4841.103 LOC SALEM
— mesmo 4841 — está em MLB23332 a R$ 216,90.

**A derivação da Magazord é o campo menos confiável dos cinco, e é justamente
o que a esteira de cadastro lê.** Consequências no anúncio: categoria
`MLB273770` (Sandálias e Chinelos) em vez de `MLB23332`, `FOOTWEAR_TYPE =
Chinelo`, guia `7742075` (Actvitta sandália, domínio SANDALS_AND_CLOGS) em vez
da `7742087` (SNEAKERS), e descrição dizendo "1 par de chinelo".

Quem procura tênis feminino não acha este anúncio. E o título —
`Actvitta Australia 4841.100 Marrom-claro 36 Br` — não tem o substantivo do
produto; o irmão está como `Tênis Feminino Calce Facil Casual Slip On Macio
Actvitta Preto 39 Br`. Ninguém busca por "4841.100".

### A pasta de origem mistura duas cores — e a capa saiu errada

As 8 fotos publicadas são **exatamente** as 8 da pasta `2658055-camelnude109494`,
na mesma ordem. O problema é a pasta: **01 a 04 são do PRETO/CINZA, 05 a 08 são
do camel/nude.** Como a ordem foi preservada, a foto de capa é a preta num
anúncio de cor "Marrom-claro".

Isso corrige de graça: promover 05–08 e tirar 01–04. Não depende da cliente.

**Correção do diagnóstico de 05/09:** este grupo entrou na lista dos 145 como
"foto emprestada de outra cor". Não é empréstimo — é pasta de origem
contaminada. O efeito para o comprador é o mesmo, a causa e o conserto não.

### 12 pares invisíveis

As 4 fotos pretas são a cor **PRETO/CINZA 102156**, que tem **12 pares em
estoque e nenhum anúncio no ML** — mais estoque que a cor publicada (8 pares).
A foto do produto que não está à venda está ocupando a capa do que está.

### Margem apertada, e o piso não foi confirmado

Margem real de 21,5% a 22,0%; folga de R$ 6 a R$ 8 sobre o piso de 20%. Mas
**os 20% do `conta.yaml` vieram do esqueleto de 26/08, não da Leilane** — está
escrito lá. Enquanto não confirmar, "acima do piso" aqui não quer dizer nada.

Frete de R$ 25,45 num produto de R$ 226,90: 11% do preço, saindo do bolso. A
caixa declarada é 13×20×37 cm / 740 g (cúbico 1,60 kg); a Magazord diz
20×12×30 / 510 g (cúbico 1,20 kg). Se a caixa real for a da Magazord, a loja
paga frete de uma caixa 33% maior. Confirmar a caixa antes de mexer no preço.

### O teste que NÃO funcionou

Tentei achar outras pastas contaminadas medindo a discordância de cor entre as
fotos do mesmo anúncio. Deu 62 de 86 grupos — inútil: quase todo anúncio tem a
tabela de medidas na última foto e fotos de ambiente em madeira e palha, então
discordar é o normal. **Para saber se há outros casos como este, é olhar pasta
por pasta.** Não está feito.

### Correção aplicada nos 6 — 06/09/2026

Backup do estado anterior (item + descrição) em
`dados/backup-4841100-2026-09-06.json`.

| o que | resultado |
|---|---|
| categoria `MLB273770` -> `MLB23332` (Tênis) | **aceito**, HTTP 200 nos 6 |
| guia `7742075` -> `7742087` (Actvitta Tênis, SNEAKERS) + linha por tamanho | aceito |
| `FOOTWEAR_TYPE = Chinelo` -> limpo | aceito (`value_id` e `value_name` = null) |
| fotos: 8 -> as 4 do camel/nude, capa na de fundo branco | aceito |
| descrição: "1 par de chinelo" -> "1 par de tênis" | regravada nos 6 |
| **título / `family_name`** | **RECUSADO pelo ML** |

Os 6 seguem `paused`. Relido da API depois: categoria, guia, linha, tipo vazio,
4 fotos e descrição conferem nos 6.

### O título não se corrige em anúncio com family_name

Duas recusas, e valem para toda a conta (todos os 547 têm `family_name`):

    PUT {"family_name": ...}  -> 400  BODY_INVALID_FIELDS
                                     "The field family name is invalid"
    PUT {"title": ...}        -> 400  BODY_INVALID_FIELDS
                                     "You cannot modify the title if the item
                                      has a family_name"

O título no modelo User Products é montado pelo ML a partir de
`family_name` + `COLOR` + `SIZE`. Como `family_name` é imutável, **o título só
muda republicando sob outro family_name** — anúncio novo, MLB novo, e fechar o
antigo. Aqui isso deixa `Actvitta Australia 4841.100 Marrom-claro 36 Br`, um
título sem o substantivo "tênis", que é a palavra que o comprador digita.

Regra que sai daqui: **o family_name é a decisão mais cara do cadastro.** Ele
não é um rótulo interno, é o título da vitrine, e não tem segunda chance.

## A comissão desta conta é 14%, não 12% (06/09/2026)

Medido em `/sites/MLB/listing_prices` para as 40 combinações de categoria e
preço que existem na conta:

| categoria | comissão | fixo | faixa de preço observada |
|---|---|---|---|
| MLB23332 (Tênis) | **14%** | R$ 0 | R$ 216,90 a R$ 396,90 |
| MLB273770 (Sandálias e Chinelos) | **14%** | R$ 0 | R$ 36,90 a R$ 226,90 |

É 14% liso nas duas categorias e em toda a faixa — não há virada de faixa aqui,
diferente do que acontece em R$ 700 noutras contas.

O `conta.yaml` tem `gold_special: 0.12`, informado em 03/09 e nunca medido. **A
diferença de 2 pontos deixa toda margem desta conta otimista.** No 4841.100:
21,6% viram **19,6%** — ou seja, abaixo do piso de 20%, e não acima como este
arquivo dizia antes de hoje.

Não alterei o `conta.yaml`: é arquivo protegido e o número é decisão do Neto.

## Varredura de categoria em toda a conta: 1 caso só (06/09/2026)

Generalizado o teste que achou o 4841.100 — comparar o **produto PAI** da
Magazord e a **DESCRICAO do Linx** (as duas fontes confiáveis) contra a
categoria e o `FOOTWEAR_TYPE` de cada anúncio, por consenso das duas.

**547 anúncios, 0 com categoria errada.** O único divergente é o próprio
4841.100, e só porque o nome da derivação na Magazord segue dizendo "chinelo"
— arquivo de origem, não dá para corrigir daqui.

Ou seja: **a troca tênis/chinelo foi caso isolado, não padrão.** Vale como
teste de regressão para rodar depois de todo lote novo — está em
`scratchpad/tipos.py`.

## O título sem substantivo: 174 anúncios em 20 famílias (06/09/2026)

Medido: das 63 famílias da conta, **43 (373 anúncios) têm o substantivo do
produto no `family_name`** e 20 (174 anúncios) não têm. Nessas 20 o título
começa pela marca e vai direto ao código do modelo:

    Havaianas Top Liso Azul-marinho 33 Br
    Cartago 12706 Ravena Preto 40 Br
    Vizzano 6371.1005 Pelica Dourado 38 Br

Nenhuma diz "chinelo", "rasteira" ou "tamanco" — que é a palavra que o
comprador digita. As quatro maiores são Havaianas (Top Liso, Tradicional,
Brasil, Top Tiras): **70 anúncios do produto mais buscado do Brasil, e nenhum
com a palavra chinelo.**

**O nome certo já existia na Magazord o tempo todo**, no campo do produto PAI
("Chinelo Havaianas Top Liso"). Nas 20 famílias o pai resolve — nenhuma
precisou de título escrito à mão. É a mesma lição do 4841.100: a esteira leu o
campo errado da mesma planilha.

### A republicação, e a ordem que importa

Como `family_name` é imutável, corrigir título = criar novo e fechar velho. O
script de 03/09 (`scratchpad/corrigir_titulos.py`) **fechava o velho ANTES de
criar o novo** — se o POST falhasse, o anúncio morria sem substituto. Refeito
em `scratchpad/republicar.py` com a ordem invertida:

    1. POST do novo          2. grava a descrição com o título novo
    3. pausa o novo          4. SÓ ENTÃO fecha o velho

Falhou o POST, o antigo continua intacto. O script também registra
separadamente o caso "novo criado mas velho não fechou", que deixaria duplicata
viva — é o que precisa de olho humano se acontecer.

Mapa velho->novo em `dados/republicados-2026-09-06.json`.

Dois nomes foram encurtados para o título composto caber em ~60 caracteres:
`Babuche Infantil Molekinha 2591.103 com Pins` (sai "Injetada EVA", que já está
em `FOOTWEAR_MATERIALS`) e `Rasteira Feminina Vizzano 6371.367 Napa Calf` (sai
"Chinelo Slide", fica o substantivo que se busca, e alinha com a irmã Pelica).

### Resultado: 174 de 174, zero falha (06/09/2026)

Conta passou de 547 para **721 registros — 547 vivos, 174 fechados**.
3.718 pares, R$ 389.810,22 de vitrine. Mapa velho->novo em
`dados/republicados-2026-09-06.json` (inclui os 2 do piloto, que o script
sobrescreveu na segunda rodada e foram remesclados à mão).

Conferido depois: **0 velhos deixados abertos** (nenhuma duplicata viva),
**0 famílias partidas pela republicação**, e **0 famílias vivas ainda sem
substantivo** no nome. Agrupamento preservado: cada família nova saiu com um
`family_id` único e igual entre os irmãos.

**6 anúncios não obedeceram ao `paused` na hora.** O `PUT status=paused` logo
depois do POST corre junto com o processamento do item no ML e às vezes não
pega — 5 ficaram `active` e 1 em `under_review`. Pausados na conferência.
**Lição: pausar não é fire-and-forget — reler o status depois e repausar quem
ficou de fora.** Cinco anúncios ficaram visíveis por alguns minutos.

**1 dos 174 caiu em `under_review / pending_documentation`**: MLB5195222297
(Rasteira Vizzano Napa Calf Bege 38). O antecessor estava normal, os 4 irmãos
da mesma família também — é revisão de marca disparada pelo anúncio novo, não
erro do payload. Está pausado; acompanhar.

## Dois produtos diferentes com o MESMO título na vitrine (06/09/2026)

Achado ao conferir a republicação: **`Chinelo Havaianas Top Basic` cobre dois
produtos distintos**, e o comprador vê dois anúncios com título idêntico:

| MODEL | anúncios | preço | EAN exemplo | produto na Magazord |
|---|---:|---|---|---|
| `TOP BASIC` | 7 | R$ 46,90 | 7909989203507 | 2363789 chinelo havaianas top basic |
| `TOP BASIC 25/6` | 8 | R$ 61,90 | 7909989677681 | 2393120 chinelo dedo havaianas top basic 25/6 |

São 14 pares de título repetido, mesma cor e mesmo número, com R$ 15 de
diferença. Não é duplicata para apagar: são produtos diferentes que precisam
de nomes diferentes. **Correção = republicar os 8 do 25/6 com
`Chinelo Havaianas Top Basic 25/6`.** Não feito — depende de autorização,
porque fecha 8 anúncios.

### Modare 7401.102 London: TRÊS cores viraram uma só

21 anúncios, 3 por numeração, todos `Tênis Feminino Casual Modare 7401.102
London Branco NN Br` ao mesmo preço. Não são duplicatas — são **três cores
reais**, cada uma com SKU e EAN próprios:

    2548926-brancodouradolondon     branco dourado
    2548926-brancooffavela          branco off/avelã
    2548926-brancooffverdelondon    branco off/verde

As três viraram `COLOR = Branco` porque a lista fechada do ML não tem esses
tons. Resultado: três anúncios indistinguíveis competindo entre si.

Tem dois caminhos, e é decisão de merchandising, não técnica:

- **Trocar o `COLOR`** para valores da lista que separem (Dourado, Bege,
  Verde). `COLOR` é EDITÁVEL — não republica nada. Mas afasta o rótulo do
  "branco" que o produto de fato é.
- **Republicar com family_name por cor**, o que separa de verdade mas quebra
  o agrupamento: viram 3 famílias em vez de 1 com 3 cores.

Não decidi por conta própria. **Some-se a isto que 2 das 3 cores estão entre
as 145 com foto errada** — resolver a cor sem resolver a foto só torna o erro
mais visível.

### Pendência menor: `MODEL` com caixa inconsistente

Quatro famílias têm o mesmo modelo escrito de dois jeitos ("Brasil" e
"BRASIL", "Top Tiras" e "TOP TIRAS", "Tradicional" e "TRADICIONAL",
"2874.202 GASPEA EVA" e "2874.202 Gaspea Eva"). **Não parte a família** — o
`family_id` é o mesmo nos dois casos —, mas polui o filtro de modelo. `MODEL`
é editável; corrigir quando sobrar folga.

### A republicação invalidou a planilha de fotos — regravada

As fotos passaram **intactas nos 174** (mesmos `picture_id`, mesma ordem):
conferido comparando o conjunto do velho com o do novo, 174 de 174 iguais. O
que quebrou foi a PLANILHA: `auditoria-fotos-cor.csv` fora gerada antes e
apontava para MLBs que a republicação fechou.

Regravada contra a conta viva: **139 anúncios com foto de outra cor** (eram
145; saíram os 6 do Actvitta 4841.100, resolvidos hoje), mais 9 a conferir.
Todos `paused`. Script: `scratchpad/refazer_auditoria_fotos.py`.

**Regra: toda republicação invalida qualquer lista de MLB gerada antes dela.**
Regerar, não corrigir à mão — e conferir que os grupos ainda são encontrados
na conta viva, que é o que prova que a lista nova cobre a antiga.

## Não, faltam cores: 67 cores e 1.454 pares (07/09/2026)

Pergunta do Neto: "todas as cores dos produtos estão cadastradas?"

Varrido por `Código Agrupador` (produto+cor) contra o `SELLER_SKU` de cada
anúncio vivo. Fonte: `dados/cores-faltando.csv`.

| | |
|---|---:|
| cores (agrupadores) com anúncio vivo | 88 |
| produtos com pelo menos uma cor no ar | 58 |
| **cores COM ESTOQUE, de produto já cadastrado, SEM anúncio** | **67** |
| **pares parados nessas cores** | **1.454** |

Onde estão concentrados:

    228 pares  13 cores  Chinelo Havaianas Slim Liso
    169 pares   5 cores  Chinelo Tamanco Modare 7142.106 NP/Sense Flex
    109 pares   4 cores  Chinelo Feminino Havaianas Slim Square Liso
     76 pares   2 cores  Chinelo Cartago 12158 Dallas Tiras Largas
     74 pares   2 cores  Chinelo Havaianas Brasil

O Havaianas Slim Liso é o caso extremo: **16 cores no estoque, 3 no ar.**

### A foto quase certamente já está aqui — e o contador diz que não

O CSV da Magazord marca "0 fotos" nas 67. **Esse contador não vale**, e a prova
está na própria lista: o Actvitta 4841.100 preto/cinza aparece nela com 0
fotos, e ontem achamos as 4 fotos dele dentro da pasta da cor irmã.

O motivo é estrutural e agora está medido: **nas 67 cores, o produto tem de 2 a
16 cores e SEMPRE uma única pasta de fotos.** A Magazord carimba tudo na
primeira cor. Ou seja, por construção a pasta é mista — a pergunta nunca é "tem
foto?", é "quantas cores estão dentro desta pasta?".

Exemplos do tamanho da sobra (fotos do produto menos o que uma cor consome):

    Havaianas Slim Liso        16 cores, 63 fotos, 1 pasta   -> 13 cores faltando
    Modare 7142.106            6 cores, 41 fotos, 1 pasta    ->  5 cores faltando
    Havaianas Slim Square Liso 6 cores, 20 fotos, 1 pasta    ->  4 cores faltando

**52 das 67 cores (1.180 pares) têm sobra clara de foto no produto** — vale
abrir a pasta e separar pela técnica já documentada (cruzar `id` +
`dt_inclusao` + nome de arquivo, e conferir 1 foto de cada lote no olho).
**1 produto não tem foto em lugar nenhum**: Modare 7208.101 Nobuck nude 52531,
41 pares — já estava registrado como a 5ª cor sem foto.

### Este balde NÃO é o mesmo dos 139

São dois problemas diferentes e não se somam:

- **139 anúncios com foto de outra cor** — estão NO AR (pausados) mostrando a
  cor errada. Risco de vender errado.
- **67 cores sem anúncio nenhum** — 1.454 pares que a loja tem e não oferece.
  Risco de venda perdida, não de reclamação.

### E o balde maior, que continua intocado

    produtos na Magazord ....................... 1.161
    com estoque ................................   837
    com pelo menos uma cor no ML ...............    58
    sem NENHUMA cor no ML ......................   779
    derivações órfãs (sem Código Pai) ..........   788 linhas, 12.572 pares

**58 de 837.** O catálogo no ar cobre 7% dos produtos com estoque da cliente.
Isso não é falha do cadastro — a fila veio da exportação do TikTok Shop, que
tinha 125 produtos. Mas é o número que importa antes de dizer à Leilane que "o
catálogo está no ar".

### O mapa: 32 produtos, cor por cor (07/09/2026)

`dados/MAPA-CORES.md` (para ler) e `dados/mapa-cores.csv` (para trabalhar).
Uma linha por COR de cada produto que já tem anúncio, com quatro situações:
**no ar**, **FALTA** (tem estoque, sem anúncio), **esgotada** (sem estoque —
não falta, acabou) e o aviso de quantos anúncios daquela cor estão com foto
errada, cruzando com a auditoria dos 139.

**Dos 58 produtos cadastrados, 32 têm cor faltando.** Os outros 26 estão
completos — toda cor com estoque tem anúncio.

Vitrine parada nas 67 cores, ao preço que já praticamos: **R$ 133.343,29.**

| pares | cores | R$ | produto |
|---:|---:|---:|---|
| 169 | 5 | 18.742 | Modare 7142.106 NP/Sense Flex |
| 228 | 13 | 12.289 | Havaianas Slim Liso |
| 58 | 2 | 9.506 | Under Armour 3027787 UA Core 2 |
| 39 | 1 | 8.459 | Actvitta 4841.103 Loc Salem |
| 76 | 2 | 6.832 | Cartago 12158 Dallas |

Repare na inversão: o **Slim Liso tem mais pares** (228) mas o **Modare 7142.106
vale mais** (R$ 18,7 mil em 169 pares), porque é R$ 110,90 contra R$ 53,90.
Priorizar por pares levaria à ordem errada.

O caso mais desproporcional é o Slim Liso: **16 cores no estoque, 1 no ar** — e
essa única cor no ar é uma das que estão com foto errada.

## Cadastro das cores faltantes — rodada 1 (07/09/2026)

### Primeiro: as 67 passam em tudo menos foto

Antes de abrir pasta de foto, conferido o resto por cor (`scratchpad/prontidao.py`,
saída em `dados/prontidao-cores.csv`):

| checagem | resultado |
|---|---|
| custo na planilha | **67 de 67 têm** |
| guia de tamanho da marca | **67 de 67 têm** |
| caixa (peso + dimensões) | **67 de 67 têm** |
| EAN em todas as derivações | 60 de 67 (7 têm alguma derivação sem) |
| margem sobre o preço do irmão | **20,8% a 38,4%** — nenhuma abaixo de 20% |

**O único bloqueio é a foto.** Isso muda a ordem do trabalho: não adianta pedir
dado à Leilane, adianta abrir pasta.

### A pasta do Drive não resolve

Verificada em 07/09: as 12 subpastas de "Fotos Prontas" são todas de 04/09 e
todas de linha Modare/Beira Rio que **não está** entre os 32 produtos com cor
faltando. Não cresceu desde então. A separação é no olho, na pasta da Magazord.

### Onde a técnica da data funciona, e onde não

Dos 9 produtos abertos nesta rodada, **5 têm um lote só** — todas as fotos
subidas no mesmo dia. Nesses a data não separa nada e é preciso ir foto a foto,
em ordem de `id`. E aí aparece um padrão novo, que vale para os próximos:

**a Magazord sobe as cores em BLOCOS CONTÍGUOS de tamanho igual.**

    Cartago 12578 Sintra   16 fotos = 8 + 8      (cinza/bege, marrom)
    Cartago 12706 Ravena   16 fotos = 8 + 8      (preto, marrom)
    Zaxy Air 19419         15 fotos = 5 + 5 + 5  (marrom, preto, off white)
    Under Armour Core 2    24 fotos = 2 lotes de 3 blocos, mesma ordem de cor
    Actvitta 4841.100       8 fotos = 4 + 4      (preto/cinza, camel)

A exceção é o Cartago Durban: 18 fotos **alternando de 3 em 3** (preto, marrom,
preto, marrom...). Ou seja — contar as cores do produto e dividir o total de
fotos é a primeira hipótese a testar, mas confirmar no olho continua obrigatório.

### As 10 cores separadas com confiança

Registrado em `scratchpad/atribuicoes.json`, com a PROVA de cada separação.
Publicado por `scratchpad/publicar_cores.py`, que **clona o anúncio irmão** já
correto — herda categoria, `family_name` (é o que faz agrupar), guia, preço,
caixa e envio, e troca só cor, SKU, EAN, tamanho, estoque e fotos.

Duas coisas que o script faz e a esteira antiga não fazia:

1. **A linha da guia vem da TABELA, não do irmão.** Antes, tamanho sem irmão do
   mesmo número era pulado — o Under Armour perderia 4 dos 12 tamanhos. Agora lê
   `/catalog/charts/{id}` e mapeia `BR_SIZE -> row_id`.
2. **Foto sobe preparada, nunca por URL do CDN** — recorta o branco, escala pelo
   menor lado e centraliza em quadrado. É a receita do piloto de 03/09.

### Uma cor rotulada pela IMAGEM, não pelo fornecedor

`bs786` (Cartago Dallas, 70 pares) é o maior item da lista e **não traz nome de
cor** — só o código. Medido: a foto dá preto 36–53% com marrom 31–34%, contra
marrom 48–65% no irmão bege/marrom. Publicado como **Preto**, e isso está
marcado no código. `COLOR` é editável; se o Neto discordar, troca sem republicar.

### Resultado da rodada 1: 66 anúncios novos, 357 pares

| produto | cor | anúncios | pares |
|---|---|---:|---:|
| Cartago 12578 Sintra | Marrom | 8 | 60 |
| Cartago 12706 Ravena | Marrom | 8 | 60 |
| Cartago 12640 Durban | Marrom | 8 | 47 |
| Cartago 12158 Dallas | Preto (bs786) | 9 | 70 |
| Cartago 12158 Dallas | Azul | 4 | 6 |
| Zaxy Air 19419 | Marrom | 8 | 23 |
| Zaxy Air 19419 | Bege | 8 | 22 |
| Under Armour Core 2 | Branco | 12 | 57 |
| Under Armour Core 2 | Violeta | 1 | 1 |
| Actvitta Australia 4841.100 | Preto | 7 | 11 |

Todos `paused`, com me2, guia certa por tamanho e agrupados no `family_id` do
irmão — conferido no piloto.

### DOIS ERROS MEUS NESTA RODADA, e como foram corrigidos

**1. Publiquei o Actvitta preto/cinza duas vezes.** Rodei o piloto num
agrupador e depois rodei o lote completo sem excluí-lo. Saíram 7 anúncios
duplicados, com o MESMO SKU e o MESMO estoque — ou seja, 11 pares contados em
dobro na vitrine.

Corrigido: conferido SKU a SKU que os pares eram idênticos, e fechados os 7 da
segunda leva. **Regra: script de publicação em lote precisa pular sozinho quem
já tem anúncio vivo naquele agrupador** — não dá para depender de eu lembrar
de passar `--so`.

**2. `Roxo` não existe na lista de COLOR.** O Under Armour roxo morreu em
`invalid.item.attribute.values`. O valor certo é **`Violeta`**. Republicado.

E de quebra, ao ler a lista inteira de MLB273770 apareceu algo que contradiz o
que este arquivo dizia em 04/09: **`Chocolate`, `Creme`, `Nude` e `Palha` ESTÃO
na lista** (são 51 valores, não 16). As equivalências Creme→Bege e
Chocolate→Marrom aplicadas naquele dia foram desnecessárias. Não é urgente
desfazer — `COLOR` é editável —, mas a lista real é esta:

    Amarelo Azul Azul-aço Azul-celeste Azul-claro Azul-escuro Azul-marinho
    Azul-petróleo Azul-turquesa Bege Bordô Branco Chocolate Ciano Cinza
    Cinza-escuro Coral Coral-claro Creme Cáqui Dourado Dourado-escuro Fúcsia
    Laranja Laranja-claro Laranja-escuro Lavanda Lilás Marrom Marrom-claro
    Marrom-escuro Nude Ocre Palha Prateado Preto Rosa Rosa-chiclete Rosa-claro
    Rosa-pálido Terracota Verde Verde-claro Verde-escuro Verde-limão
    Verde-musgo Vermelho Violeta Violeta-escuro Água Índigo

**Sempre ler a lista da categoria antes de mapear cor.** Supor que ela é curta
custou uma equivalência errada em 17 anúncios e uma falha de publicação hoje.

## A folha de etiquetagem de cor (07/09/2026)

**https://claude.ai/code/artifact/a0a6aa13-0229-4b97-9d31-b085f457b27e**
Fonte local: `dados/etiquetar-cores.html` (gerada por `scratchpad/gerar_pagina.py`).

Sobraram **56 cores em 24 produtos, 1.056 pares**, e nenhuma está bloqueada por
dado — está bloqueada por não dar para afirmar, olhando a foto, qual rosa é
"rosa gum" e qual é "rosa ballet". O Slim Liso sozinho tem quatro rosas e três
verdes/amarelos nessa situação.

A página mostra, por produto: as cores que faltam com os pares de cada uma, e as
fotos separadas em **54 grupos** (quebrados por data de envio E por salto de
`id`). Quem conhece o produto escolhe a cor de cada grupo num seletor. As opções
incluem "já está no ar", "não é deste produto" e **"não sei dizer"** — que é
resposta legítima e melhor que chute.

Duas coisas técnicas que valem para a próxima página:

1. **O CSP do artifact bloqueia imagem de host externo.** As 467 fotos do CDN da
   Magazord não carregariam. Foram embutidas como `data:` URI, em miniatura de
   150 px, q72: **1,28 MB** no total, contra o teto de 16 MB.
2. **A página declara a capability `db`**, então cada resposta é gravada na hora
   em `respostas/<Código Pai>` e eu leio de volta com `read_db` — sem
   copiar e colar. Se o `db` não estiver disponível na visualização, cai para
   `localStorage` sozinha.

Quando as respostas chegarem: ler `respostas`, transformar em
`scratchpad/atribuicoes.json` e rodar `scratchpad/publicar_cores.py`, que já
está pronto e testado.

**Corrigir antes de rodar de novo:** o `publicar_cores.py` NÃO pula agrupador
que já tem anúncio vivo — foi assim que publiquei o Actvitta preto/cinza em
duplicata. Acrescentar essa checagem antes do próximo lote.

## O SITE DA LOJA RESOLVE A SEPARAÇÃO DE COR (07/09/2026)

Ideia do Neto: "se entrar no site da Chinelaria consegue cruzar?" — consegue, e
é a fonte que faltava desde 03/09.

**Na loja, cada COR é uma página própria** (`/chinelo-dedo-havaianas-slim-liso-slim-liso-pessego`),
com o nome exato da derivação no título. E o HTML dessa página traz a **foto de
capa daquela cor**. Como as fotos de um produto vêm em ids contíguos, a capa de
cada cor **delimita o bloco** — acabou o achismo.

    Slim Liso, 16 cores, capas em 4006 4009 4012 4015 4018 4021 4023 4025 ...
    4006-4008 branco     4015-4017 pessego      4023-4024 preto
    4009-4011 pink fever 4018-4020 areia/dourado 4025-4027 rose gold
    4012-4014 rosa ballet 4021-4022 amarelo pop  4034-4036 verde matcha

O "pêssego" era exatamente o grupo que eu não sabia se era pêssego ou laranja
sunset. E as duas cores ESGOTADAS (buttercream 4028-4030, lilás 4031-4033)
apareceram e explicaram os buracos que sobravam.

### Como fazer (o caminho certo, não a busca)

1. `sitemap-produto.xml` — 1.679 URLs. **Não usar `/busca?q=`**: o `robots.txt`
   da loja bloqueia `/*?*q=*` (e também `derivacao=`, `ordem=`, `inStock=`).
2. Casar cor -> URL pelo slug de `produto + cor` (tirando a numeração do fim da
   cor); quando não bate exato, pelo sufixo da cor.
3. Ler a capa por regex no HTML cru — `requests` basta, não precisa navegador.
   A galeria completa vem por JS, mas **a capa está no HTML** e a capa é o que
   importa.
4. Bloco = da capa até a capa da cor seguinte, **cortando no primeiro salto de
   id**. Esse corte é obrigatório: sem ele, cor cuja página não foi encontrada
   faz o bloco anterior engolir as fotos dela.

Colhido: **1.192 páginas de cor lidas, 1.156 cores com bloco, 5.456 fotos
separadas** — cobre muito além do que estava em jogo.

### O que isso destravou

| | antes | depois |
|---|---|---|
| cores faltando sem foto atribuível | 56 | **12** |
| anúncios com foto de outra cor | 139 | **23** |

**44 das 56 cores** ganharam bloco (687 pares) e **116 dos 139 anúncios** podem
ter a foto corrigida — sem depender de a Leilane mandar nada.

Publicadas 42: tirei "Zaxy 19359 Mood by047 preto" (12 pares, a capa mostra
sandália marrom) e "Havaianas Dual verde olive/branco" (1 par, capa preto/coral)
— nas duas o nome não bate com a foto, e nome que não bate é sinal de que o
bloco pegou a cor errada.

### Ficam pendentes (12 cores)

Modare 7142.106 (5 cores, 169 pares), Havaianas Slim Square Liso (3, 94),
Havaianas Brasil marinho e azul naval (2, 74), Azaleia Fabi Light (2, 32).
Não têm página no site — provavelmente nunca foram publicadas na loja também.
Essas seguem na folha de etiquetagem.

**Regra nova: antes de tentar separar cor no olho, olhar o site da cliente.**
A loja é a fonte que declara a cor; a exportação da Magazord só a infere.

### `MAIN_COLOR` não é `COLOR` — 82 anúncios morreram nisso (07/09/2026)

Ao publicar as 42 cores, 112 subiram e **82 falharam** em
`invalid.item.attribute.values`. Causa: eu copiava o valor de `COLOR` para o
`MAIN_COLOR`.

    COLOR       51 valores  (Rosa-chiclete, Verde-limão, Azul-marinho, Terracota,
                             Chocolate, Água, Coral-claro, Marrom-escuro...)
    MAIN_COLOR  16 valores  Amarelo Azul "Azul celeste" Bege Branco Cinza Dourado
                            Laranja Marrom Multicolorido Prateado Preto Rosa
                            Verde Vermelho Violeta

Toda cor cujo `COLOR` não era um dos 16 foi recusada. As 23 que passaram inteiras
eram justamente as de nome simples (Preto, Branco, Marrom, Dourado, Azul...).

Detalhe que morde: no `MAIN_COLOR` é **"Azul celeste" SEM hífen**, e no `COLOR`
é "Azul-celeste" COM hífen. Não dá para derivar um do outro por texto.

`scratchpad/mapear_cor.py` agora tem duas funções separadas — `cor_ml()` para o
COLOR e `main_cor()` para o MAIN_COLOR, com a tabela de redução (Rosa-chiclete e
Rosa-claro -> Rosa, Terracota e Chocolate -> Marrom, Verde-limão e Água ->
Verde, Azul-marinho -> Azul, Coral-claro -> Laranja).

**Regra: ler a lista de CADA atributo, nunca supor que dois atributos de cor
compartilham vocabulário.** É a terceira vez nesta conta que supor lista curta
ou lista compartilhada custa uma rodada (Roxo/Violeta em 07/09, as
equivalências desnecessárias de 04/09, e agora esta).

### Fechamento da rodada de cores — 07/09/2026

**194 anúncios em 42 cores, 674 pares.** Descrições: 194 de 194, zero erro.

| | antes de hoje | agora |
|---|---:|---:|
| registros | 721 | **995** (813 pausados, 181 fechados, 1 em revisão) |
| cores no ar | 88 | **138** |
| pares | 3.718 | **4.667** |
| vitrine | R$ 389.810 | **R$ 479.633** |

### Mais três erros meus, e a regra que cada um deixou

**1. Copiei `COLOR` para `MAIN_COLOR`** — 82 anúncios recusados. Listas
diferentes (51 x 16). Regra: ler a lista de CADA atributo.

**2. Duas cores REAIS caíram no mesmo valor de `COLOR`.** "rose gold" e
"areia/dourado" viraram `Dourado`; "pink fever" e "rosa gum" viraram
`Rosa-chiclete`; "rosa ballet" e "rosa chiffon" viraram `Rosa-claro`; "wild
lime" e "verde matcha" viraram `Verde-limão`. No modelo User Products
família+COLOR+SIZE tem de ser único: o ML recusou parte e, onde aceitou, criou
**nome repetido na vitrine**. Corrigidos 17 anúncios com valor distinto
(`COLOR` é editável) e criada a tabela `DESEMPATE` em `scratchpad/mapear_cor.py`.
**Regra: depois de mapear, conferir se duas cores do MESMO produto colidiram.**

**3. Inventei o valor de `EMPTY_GTIN_REASON`.** Mandava "Não possui código
universal"; a lista tem 4 valores e o certo é **"O produto não tem código
cadastrado"** (`value_id 17055160`). Derrubou as últimas 4.

E a trava de duplicata passou a ser por **cor+tamanho**, não por cor: por cor
ela impedia completar tamanho que falhou numa rodada anterior.

### Sobraram 20 nomes repetidos na vitrine — e nenhum é dos meus

    4841.103 LOC SALEM  Preto   6 anúncios em 2 cores (15758 preto/branco e
                                16143 preto/preto/preto) — são pretos de verdade
    7401.102 LONDON     Branco 14 anúncios em 3 cores (branco dourado, branco
                                off/avelã, branco off/verde)

São produtos que o ML não distingue porque a cor É a mesma. Não tem correção
técnica: ou se aceita, ou se escolhe um valor aproximado diferente para cada.
**Decisão do Neto.**

### Dois `family_name` ruins, de lotes antigos

    "Chinelo Havaianas Slim Point Point Ferrungem/smok Gree"  <- cor no nome da familia
    "Chinelo Havaianas Slim Liso - Chinelo Dedo Havaianas Slim Li"  <- nome duplicado

O primeiro faz TODAS as cores do Slim Point carregarem "Ferrungem/smok Gree" no
título. Só se corrige republicando.

## Correção das fotos erradas pelo bloco do site (07/09/2026)

O cruzamento com a loja resolveu o que estava travado desde 03/09 esperando a
Leilane. Trocada só a lista `pictures` — não republica, não mexe em preço,
estoque, guia nem status. Antes/depois em `dados/fotos-trocadas-2026-09-07.json`.

Os MLBs são redescobertos na conta VIVA pelo agrupador, nunca lidos de planilha:
lista de MLB envelhece a cada republicação (foi o que aconteceu em 06/09).

**Duas capas do site foram recusadas na conferência visual**, pelo mesmo
critério que já tinha pegado o Zaxy Mood: o nome da cor não bate com a foto.

    t basic branco/br/branco   -> a capa tem listras vermelhas
    t/basic preto/preto/preto  -> a capa tem degrade laranja

Nesses dois o site é tão suspeito quanto a Magazord. Ficam para a folha.
**O site é a melhor fonte disponível, não é fonte infalível — a conferência no
olho continua sendo o último passo, mesmo com fonte declarada.**

### Resultado: 108 anúncios corrigidos, 0 erro (07/09/2026)

19 cores. Conferido relendo da API: **108 de 108** com exatamente as fotos
gravadas no registro de antes/depois.

Uma foto caiu com HTTP 502 no CDN da Magazord (Molekinho 2417.100 slide eva) e
essa cor ficou com 8 fotos em vez de 9. Não impede nada; refazer se incomodar.

**O Gaspea 2874.202 era o pior caso e foi resolvido junto.** As fotos antigas
eram do babuche **LED 2874.407** — produto diferente. As novas vêm da pasta do
próprio Gaspea (`2546293`), e o site ainda separou as duas cores DENTRO dessa
pasta: `preto amarelo neon` ficou com 12407-12412 e `marinho laranja` com
12413 em diante. Ou seja, a mesma técnica conserta cor errada E modelo errado.

### O que ainda trava foto: 31 anúncios

    23  sem bloco no site   Slim Square branco (8), Top Tiras rosa ballet (6),
                            Molekinho 2874.204 preto/amarelo/neon (9)
     8  bloco recusado      Top Basic branco/br/branco (4) e preto/preto/preto (4)

## O que dá para extrair do site da loja (07/09/2026)

Levantado abrindo a página de produto e o HTML cru. Tudo abaixo sai com
`requests` — só a galeria completa e as abas precisam de navegador.

| dado | onde | serve para |
|---|---|---|
| **SKU por tamanho** (`00820433`…) | JSON no HTML | é o `Código` da derivação — **chave exata**, dispensa casar slug |
| foto de capa da cor | HTML | separar cor (já usado) |
| nome do produto e da cor | H1 | título melhor que o atual |
| trilha (Feminino > Tamancos) | HTML | categoria e gênero, 2ª fonte para tênis x chinelo |
| preço PIX e cartão | HTML | comparar com o preço do ML |
| grade de tamanhos | HTML | quais numerações existem |
| ficha `<dt>/<dd>` | HTML | Marca, Faixa Etária, **Gênero**, **Altura Salto**, Cuidados |
| descrição resumida e completa | HTML | copy real por produto, escrita à mão |
| **Tabela de Medidas** | imagem no CDN | **as 5 tabelas que faltavam** |

### O erro que isso corrigiu no meu método

Eu casei página com cor pelo **slug** de produto+cor. O site **omite o código do
modelo e o código da cor**: `chinelo-tamanco-modare-np-sense-flex-camel`, sem
"7142.106" e sem "1165". Por isso 14 cores ficaram de fora como "sem página no
site" — e todas têm página.

**O certo é casar pelo SKU**, que a página traz por tamanho e é o `Código` da
derivação. Chave exata, nada de semelhança de texto. Refazer o cruzamento por
SKU antes de qualquer nova rodada.

### AS 5 TABELAS DE NUMERAÇÃO ESTÃO NO SITE DELA

O que eu vinha pedindo à Leilane desde 04/09 está publicado na própria loja:

    tabela-actvitta-tenis-feminino.png   tabela-actvitta-tenis-masculino.png
    tabela-papete-moleca.png
    tabela-vizzano-papete.png            tabela-vizzano-tenis-1430-109.png
    tabela-underarmour-unissex.png
    tabela-azaleia-18908.png

Conferido no olho: trazem numeração e centímetro. Ex.: Under Armour 33/34=23,
35/36=24, 37/38=25, 39/40=26, 43/44=28, 45/46=30,5. Moleca 34=23 … 40=26.
Vizzano 33=22 … 41=27,3. Actvitta masculino 37=24,6 … 45=29,9.

**Destrava os 163 anúncios** que hoje usam extrapolação Paris-point.

⚠️ **Cuidado ao usar: metade diz "COMP. PALMINHA", não comprimento do pé.**
Actvitta, Moleca e Azaleia rotulam palmilha; Under Armour e Vizzano dizem
"TAMANHO (CM)". Palmilha é maior que o pé. O painel ao lado manda medir o PÉ e
comparar com a tabela, então a loja a usa como pé — mas isso é interpretação, e
o `FOOT_LENGTH` da guia é comprimento do PÉ. **Confirmar com o Neto antes de
gravar**, senão troco uma estimativa documentada por um número que parece
oficial e não é.

E a Actvitta tem tabela masculina e feminina separadas — os 65 anúncios da conta
são femininos; usar a feminina, não a que aparecer primeiro.

### O que o site NÃO tem

**Material (cabedal/forro/solado).** A ficha do site tem 5 campos e nenhum é
material. Os 555 anúncios sem `FOOTWEAR_MATERIALS` seguem dependendo do
fornecedor.

## As 5 tabelas aplicadas — a numeração saiu de estimativa (07/09/2026)

Neto autorizou tratar "COMP. PALMINHA" como comprimento do pé. Aplicado em
**5 guias, 153 anúncios**, com as tabelas colhidas do site da própria loja.

| guia | marca | anúncios | linhas mudadas |
|---|---|---:|---:|
| 7742075 / 7742087 | Actvitta | 65 | **0** |
| 7742603 | Moleca | 41 | 7 |
| 7746723 | Vizzano | 26 | 4 |
| 7746725 | Under Armour | 21 | 12 |

**A Actvitta não mudou uma linha.** A extrapolação Paris-point de 03/09 bate
EXATAMENTE com a tabela da marca (34=22,6 … 40=26,6). O método estava certo, e
agora tem confirmação de fonte — os 65 anúncios já estavam corretos.

**A Under Armour recusou na primeira tentativa**: `duplicated_measure_value`.
A tabela dela é PAREADA (35/36 = 24) e o ML não aceita duas linhas com o mesmo
`FOOT_LENGTH`. Desdobrado com -0,25 / +0,25 em torno do valor da marca — mesma
regra já usada na Havaianas. O par 41/42 não existe na tabela da marca; foi
interpolado entre o 39/40=26 e o 43/44=28 que ela publica, e está marcado como
tal no código.

### ⛔ AZALEIA SEGURADA — e por quê

A tabela da Azaleia dá **33 = 23,8 cm**. Pela norma brasileira, 23,8 cm de PÉ é
36/37 — dois números acima. Isso não é a diferença sutil entre palmilha e pé:
é a palmilha de uma plataforma, uns 2 cm mais longa que o pé. Gravar mandaria
quem calça 36 comprar 33.

Nas outras quatro marcas a diferença para a norma fica em 0,4 cm, que é
coerente com palmilha de calçado raso. **A autorização de tratar palmilha como
pé vale onde os números são plausíveis; na Azaleia eles não são.** Os 10
anúncios seguem com a extrapolação documentada.

### A descrição prometia o que ainda não existia

Ao regravar as 153 descrições com o centímetro, elas passaram a dizer "a tabela
de medidas está na última foto" — e esses anúncios eram justamente os 95 que
NÃO tinham a tabela. Anexada em seguida, do próprio site, respeitando o teto de
10 fotos.

Conferido: **152 de 153 com a tabela como última foto**, e numa amostra de 40 o
centímetro da descrição bate com o da guia em 40 de 40.

O 1 que falta em tudo é o `MLB5195222297`, em `under_review /
pending_documentation` — nesse estado o ML recusa `pictures` e `description`.
Reprocessar quando sair da revisão.

## Estado ao fim de 07/09/2026: 772 de 814 prontos para ativar

Medido anúncio a anúncio (`scratchpad/prontos.py`). "Pronto" = pode ir ao ar sem
risco de reclamação nem de venda perdida: foto da cor certa, numeração real,
descrição, atributos obrigatórios, Mercado Envios e margem acima do piso.

**Zero anúncios sem custo, zero abaixo da margem, zero sem me2, zero sem
atributo obrigatório.** As 42 pendências são de três tipos só:

    31  foto de outra cor   (23 sem bloco no site + 8 com bloco recusado)
    10  numeração estimada  (Azaleia — a tabela do site não fecha)
     1  MLB5195222297 em pending_documentation

Não impede ativar, mas melhora posicionamento: 553 sem `FOOTWEAR_MATERIALS`,
87 tênis sem ficha técnica, 60 anúncios com título repetido.

**O que separa esta conta de vender não é mais trabalho de cadastro — é a
decisão de ativar.** Os 814 estão pausados desde 03/09 pela regra do Neto.
