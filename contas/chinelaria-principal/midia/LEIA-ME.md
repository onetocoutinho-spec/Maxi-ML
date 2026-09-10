# Mídia da Chinelaria Leilane Neves

## `fotos/` — entrada das imagens do cliente

Copie aqui a pasta que veio da outra máquina. Não precisa organizar antes:
eu inventario, agrupo por produto e digo o que dá para usar.

O que ajuda muito, se existir:
- **nome de arquivo com modelo/cor/tamanho** (ou a pasta por produto);
- a **planilha** que acompanha (marca, modelo, cor, grade, EAN, custo);
- saber quais fotos são **do fornecedor** (catálogo da marca) e quais são
  **dela** (loja, customizado, artesanal) — muda o que pode ir ao ar.

## `youtube/` — coletado em 02/09/2026

23 vídeos do canal `@chinelarialeilaneneves` (2019 a 2025): capa em .jpg e
metadados em .info.json. Não serve como foto de anúncio — serve como
inventário do que ela vende e de como ela descreve o produto.

## O que o YouTube revelou sobre o negócio

- **Revendedora de marca**, não fabricante: Havaianas, Zaxy, Ipanema, Moleca,
  Modare, Molekinho, Molekinha, Worldcolors, Boaonda.
- **E-commerce próprio**: chinelarialeilaneneves.com.br (páginas de produto
  com URL `/marca/nome-do-produto-pNNNN`).
- Loja física em Votuporanga/SP · atendimento 17 99667-1231 ·
  Instagram @chinelarialeilaneneves.
- Começou no artesanato em 2014; há vídeos de chinelo **customizado** —
  essa linha é dela, não tem ficha de catálogo e é a que mais precisa de
  foto própria.

## A consequência para o cadastro no ML

Anúncio de **catálogo** usa a imagem DA FICHA, não a do vendedor. Em marca
grande com GTIN na caixa (Havaianas, Ipanema, Zaxy), a ficha já existe: ela
entra na ficha e **não sobe foto nenhuma**. Foto própria é obrigatória só no
que não tem ficha — customizado, artesanal, marca pequena.

Ou seja: o gargalo do cadastro provavelmente não é foto, é **EAN e custo por
SKU**. Confirmar isso antes de gastar hora tratando imagem.

Atenção ao que o perfil dela no ML diz: a conta tem a tag
`user_product_seller`, e o `conta.yaml` descreve o modelo "User Products com
family_name" — que é modelo de marca própria. As duas coisas podem conviver
(customizado é dela, marca revendida vai por ficha), mas o `conta.yaml` hoje
descreve só metade do negócio. Revisar quando o catálogo real chegar.
