# Achar concorrente fora do catálogo

O Mercado Livre bloqueou a busca por palavra-chave na API. Os endpoints que
sobraram — destaques de categoria e catálogo — **só enxergam item de catálogo**.
Quem vende igual ao cliente por anúncio tradicional fica invisível.

Existe um caminho que não depende de API nem de ferramenta paga.

## O método

Busca web restrita ao domínio de anúncio tradicional do Mercado Livre:

```
site:produto.mercadolivre.com.br TERMO MEDIDA
```

`produto.mercadolivre.com.br` é o endereço de **anúncio tradicional**.
Ficha de catálogo usa `mercadolivre.com.br/.../p/MLB...`. Restringir ao
primeiro domínio filtra exatamente o ponto cego.

Cada resultado traz o `MLB` no próprio endereço. Com o ID em mãos, a API
oficial volta a funcionar: preço, estoque, frete, vendedor e reputação de
qualquer anúncio, mesmo fora do catálogo. **A busca serve para descobrir; a
API serve para acompanhar.**

## O que buscar

Use os títulos reais do cliente como fonte dos termos — nunca o nome genérico
da categoria. Se ele vende "Toldo Policarbonato 305x100 Pergolado", busque
pela medida e pelo material, não por "toldo".

Varie a grafia da medida: o mercado escreve `305x100`, `3,05x1,00` e
`3,05 x 1,00` para a mesma coisa. Uma busca por formato.

## Depois de achar

Cadastre com `cli.py vigiar SLUG LINK --comparar-com MLB-SEU`.

O vínculo só quando a medida realmente casa. Um 3,00x1,00 contra o 305x100 do
cliente é comparação honesta; um 3,40x1,00 não é — cadastre sem vínculo, para
acompanhar sem gerar alerta de preço enganoso.

## Os limites, e eles importam

**O índice do Google não é o ranking do Mercado Livre.** Você descobre *quem
existe*, não *quem aparece primeiro* quando o cliente busca. A medição de
posição continua perdida.

**A cobertura é parcial.** O Google indexa uma fração dos anúncios, e com
atraso. Anúncio novo pode não aparecer.

**Serve para discovery pontual, não para varredura recorrente em escala.** Com
uma dezena de contas e vários termos cada, a ferramenta certa passa a ser uma
API de SERP dedicada, que devolve a posição real e cobertura completa.

Para uma conta, uma vez por mês, este método resolve — e custa zero.
