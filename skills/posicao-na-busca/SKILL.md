---
name: posicao-na-busca
description: Mede em que posição os anúncios de uma conta aparecem na busca do Mercado Livre e quem mais aparece ali, incluindo quem vende fora do catálogo. Siga este roteiro quando pedirem posição na busca, ranking, "em que lugar apareço", concorrente fora do catálogo, ou pesquisa de mercado de uma conta.
---

# Posição na busca do Mercado Livre

## Por que este roteiro existe

O endpoint de busca da API (`/sites/MLB/search`) devolve 403, e ler anúncio de
terceiro por ID também está bloqueado. Sem isso, o sistema mede tudo que
acontece **dentro** do anúncio — preço, estoque, qualidade, buy box — e nada
sobre **exposição**. Um anúncio pode estar perfeito e invisível ao mesmo tempo.

A busca do próprio Mercado Livre responde as duas perguntas de uma vez: em que
posição o cliente aparece, e quem mais está ali — inclusive quem vende fora do
catálogo, que é justamente quem a API se recusa a mostrar.

## A escolha da fonte, e por que as outras não servem

| fonte | mede posição real? | por quê |
|---|---|---|
| API do ML | não | 403 |
| WebFetch da página | não | `mercadolivre.com.br` bloqueia por robots.txt |
| Busca no Google (`site:produto.mercadolivre.com.br`) | **não** | descobre quem existe, não quem aparece primeiro. O índice do Google não é o ranking do ML |
| **Navegador do usuário (Claude in Chrome)** | **sim** | é a página de busca do ML de verdade, com o CEP e a sessão dele |

Use o navegador. A busca no Google continua servindo só para **descobrir**
anúncios fora do catálogo — nunca apresente resultado de Google como posição.

## Procedimento

1. **Pegue os termos** de `contas/<slug>/palavras-chave.yaml`. São os termos já
   calibrados nos títulos reais do cliente. Não invente termos genéricos: em
   toldo, "toldo articulado" devolve manivela.

2. **Abra a busca no Chrome do usuário**, um termo por aba:
   `https://lista.mercadolivre.com.br/<termo-com-hifens>`

3. **Leia a página** e anote, para cada termo:
   - a posição de cada anúncio do cliente que aparecer (procure pelo apelido da
     loja no resultado);
   - os 10 primeiros resultados: posição, título, preço, vendedor e link;
   - o total de resultados que a página informa.

   Anúncio patrocinado **não conta** como posição orgânica. Se não der para
   distinguir, registre a posição e diga isso ao usuário — número com ressalva
   é melhor que número errado sem ressalva.

4. **Escreva o arquivo** em `pedidos/entrada/posicoes-<slug>-<data>.json`:

```json
{
  "conta": "enio-toldos-principal",
  "medido_em": "2026-08-27T12:00:00+00:00",
  "termos": [
    {
      "termo": "toldo policarbonato pergolado",
      "total_resultados": 1240,
      "meus": [{"item_id": "MLB6920349886", "posicao": 7, "preco": 1932.99}],
      "concorrentes": [
        {"posicao": 1, "titulo": "...", "preco": 899.0,
         "vendedor": "TOLDOSBRASIL", "link": "https://..."}
      ]
    }
  ]
}
```

   Só `termo` é obrigatório em cada bloco. Campo que você não conseguiu ler
   fica de fora — **nunca preencha por estimativa**. Uma posição inventada vira
   alerta de queda inventado, e alerta falso custa mais que dado faltando.

5. **Deixe a fila importar.** O vigia roda `cli.py posicoes` em até 5 minutos.
   Ele grava o histórico, avalia as regras e manda o que mudou no Telegram.
   Para antecipar, o usuário clica em `fila.bat`.

## O que isso liga

Duas regras que já existiam e estavam paradas desde o bloqueio da busca:

- **`queda_de_posicao`** — "Seu anúncio caiu da posição 4 para 11 em toldo
  policarbonato pergolado." Precisa de pelo menos duas medições para existir.
- **`concorrente_novo_no_topo`** — quem entrou no top N desde a medição
  anterior, com posição e preço.

Os concorrentes encontrados entram no histórico com origem `palavra-chave`,
separados da vigilância de catálogo. É assim que quem vende fora do catálogo
finalmente ganha série histórica: não pela API, pela medição repetida.

## Cadência honesta

Isto não roda de 5 em 5 minutos — depende de alguém conduzir o navegador.
Semanal por cliente já entrega tendência; diário em campanha ou disputa de
preço. Diga a cadência ao usuário em vez de deixar implícito, para ninguém
achar que posição está sendo vigiada em tempo real como preço e estoque.

## Erros que já foram cometidos aqui

- **Rodar `cli.py posicoes` chamando `rules.avaliar()`** — a avaliação completa
  compara os anúncios do carimbo novo, e uma importação de posição não traz
  anúncio nenhum. Resultado: 41 alertas de "sumiu da conta". O comando usa
  `avaliar_busca()`, que só roda as duas regras de busca.
- **Apresentar resultado de Google como posição** — o índice do Google não é o
  ranking do Mercado Livre. Serve para descobrir, não para medir.
