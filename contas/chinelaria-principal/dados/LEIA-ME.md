# Fontes de dados da Chinelaria — e a chave que liga uma na outra

Recebidos em 02–03/09/2026.

| arquivo | o que é | grão | linhas |
|---|---|---|---|
| `magazord-derivacoes-2026-09-03.csv` | catálogo completo do e-commerce | derivação (modelo+cor+tamanho) | 12.649 |
| `magazord-anuncios-tiktokshop-2026-09-03.csv` | o que ela JÁ anuncia no TikTok Shop | produto (pai) | 125 |
| `linx-custos-2026-09-01.csv` | custo e estoque da loja física | modelo+cor | 1.505 |
| `linx-precos-estoque-2026-06-30.pdf` / `.csv` | o mesmo, versão de 30/06 em PDF | modelo+cor | 1.366 |
| `candidatos-ml.csv` | **a saída**: os 125 com grade, EAN, custo e margem | produto | 125 |

## As chaves — testadas, não supostas

**TikTok Shop → Magazord:** `Código Produto` (TikTok) = `Código Pai` (Magazord).
**125 de 125.** O anúncio é o produto pai; a derivação é a grade dele.
Não use `Id Derivação` para isso: os dois arquivos usam faixas diferentes e
casam só 70 de 125.

**Linx → Magazord:** `REFERENCIA` (Linx) = `Modelo` (Magazord), refinado por cor:
o primeiro token de `CORX` no Linx é o mesmo código de cor que aparece entre
parênteses no `Nome da Derivação` da Magazord.

    Linx      REFERENCIA "1944.208 BRAVE"  CORX "006 BRAVE SELVA/PRETO"
    Magazord  Modelo     "1944.208 BRAVE"  Nome "... (006 brave selva/preto 41)"

Normalizando (maiúscula, sem acento, `-` vira `.`, só letras e números):
773 modelos casam, **1.168 das 1.505 linhas do Linx (77%)**, e **8.561 das
12.649 derivações (67%)** recebem custo. Nos 125 produtos que ela realmente
anuncia, a cobertura é de **121 (96%)**.

### Correção do que estava escrito aqui antes

A primeira versão deste arquivo dizia que Linx e Magazord não tinham chave
possível e que só restava texto livre, com 29% de cobertura. **Estava errado.**
O erro foi testar `REFERENCIA` contra as colunas de ID da Magazord — quando
`REFERENCIA` não é ID: é o nome do modelo. Contra `Modelo`, casa.

Também caiu por terra o pedido de "exportação do Linx com EAN": não é preciso.

## O que ainda falta

- **Custo por tamanho não existe** — o Linx dá custo por modelo+cor, e a grade
  inteira herda o mesmo valor. Para calçado isso é normal (o par custa igual em
  qualquer numeração), mas confirme com a Leilane antes de tratar como verdade.
- **4 dos 125 ficaram sem custo.** Estão marcados no `candidatos-ml.csv` com a
  coluna `custo` vazia.
- **A margem no `candidatos-ml.csv` é BRUTA** — preço menos custo, sem comissão
  do ML, sem imposto, sem frete. O piso de verdade sai de `core/precificacao.py`
  e depende da margem mínima real, que ainda não foi confirmada com a cliente.
- **Datas diferentes**: custo de 01/09, catálogo de 03/09, e o PDF de 30/06.
  Para cadastrar serve. Para prometer estoque no ML, não.
