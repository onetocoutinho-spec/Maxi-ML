---
name: raio-x-conta-ml
description: Diagnostico completo de uma conta de Mercado Livre a partir dos dados do zion-ml — saude dos anuncios, canibalizacao entre anuncios proprios, conversao, buy box, e comparacao com concorrentes em preco, frete e reputacao. Use quando o usuario pedir "raio-x da conta", "analisa a conta do cliente", "diagnostico do cliente", "como esta a conta", "analise de concorrentes", "o que arrumar nessa conta", "auditoria da conta" ou quando conectar um cliente novo no zion-ml e quiser a primeira leitura. Produz um relatorio priorizado por impacto financeiro, com acoes em ordem, publicado como artifact e resumido no Telegram.
---

# Raio-X de conta do Mercado Livre

Transforma os dados brutos do `zion-ml` em um diagnóstico que o operador consegue
agir hoje. O objetivo não é mostrar números — é **encontrar dinheiro parado** e
dizer em que ordem mexer.

## Antes de tudo: o dado existe?

O banco fica em `data/zion_ml.db`, na raiz do zion-ml. Confira se há coleta
recente para a conta antes de analisar:

```sql
SELECT conta_slug, MAX(coletado_em), COUNT(DISTINCT coletado_em) AS coletas
FROM snap_anuncio GROUP BY conta_slug;
```

- **Sem coleta** → peça para rodar `coletar.bat` e pare aqui.
- **Uma coleta só** → dá para diagnosticar o estado, mas não o que mudou.
  Diga isso explicitamente no relatório em vez de fingir tendência.
- **Sem linhas de origem `confronto`** → o mapa de concorrentes não rodou.
  A parte de concorrência sai vazia; peça `concorrentes.bat`.
- **Concorrência vazia mesmo depois do mapa** → provavelmente o cliente é o
  único vendedor nas fichas dele. Não é falta de dado, é ausência de disputa
  no catálogo — e o concorrente real está fora dele. Veja
  `references/fora-do-catalogo.md`.

## Atalho: o diagnóstico automático

Antes de escrever qualquer coisa, rode:

```
python cli.py diagnostico SLUG --detalhado
```

Ele já encontra sozinho os padrões que mais se repetem: campeão de vendas fora
do ar, canibalização agrupada por medida ou por produto de catálogo, pausados
com estoque somando valor, ativos sem estoque, conversão real e apelido
automático de conta. Use como **ponto de partida**, não como relatório — ele
acha o padrão, você explica o porquê e o que fazer.

Acrescente `--enviar` para mandar o resumo no canal configurado.

## O roteiro

Rode as consultas de `references/consultas.sql` **na ordem**. Elas foram
desenhadas para responder, uma a uma, as perguntas que importam. Leia
`references/interpretacao.md` para saber o que cada resultado significa —
ali estão as réguas: o que é normal, o que é alarme, e o que parece problema
mas não é.

A ordem existe porque os achados se encadeiam: descobrir que o campeão de
vendas está pausado muda como você lê a queda de faturamento depois.

1. **Panorama** — quantos anúncios, ativos, pausados, receita e vendas de 7 dias
2. **Reputação** — nível, reclamações, cancelamentos, atrasos
3. **Campeões e mortos** — quem sustenta a conta e quem só ocupa espaço
4. **Anúncios parados com estoque** — dinheiro em prateleira
5. **Ativos sem estoque** — o pior dos dois mundos
6. **Canibalização** — anúncios próprios disputando entre si
7. **Conversão** — visitas contra vendas
8. **Tipo de anúncio** — Premium contra Clássico
9. **Catálogo e buy box** — onde há disputa e onde ele está sozinho
10. **Concorrentes** — quem disputa, a que preço, com que frete e reputação
11. **Fora do catálogo** — se o passo 10 vier vazio ou raso, use
    `references/fora-do-catalogo.md` para achar quem vende igual por anúncio
    tradicional. É o ponto cego mais comum, e o que mais engana: relatório que
    diz "sem concorrentes" quando na verdade é "sem concorrentes onde eu olhei".

## A regra que separa análise de planilha

Todo achado precisa responder **"e daí?"**. Um número sem consequência não entra
no relatório.

- ❌ "38 anúncios, sendo 28 ativos e 10 pausados."
- ✅ "O campeão de vendas está pausado por falta de estoque. É o anúncio que
  mais vendeu na conta inteira — enquanto estiver parado, o histórico que faz
  ele ranquear esfria."

E todo achado precisa de **evidência numérica ao lado**, não depois. O leitor
não deve precisar procurar o dado que sustenta a frase.

## Ordem de prioridade

Ordene por **dinheiro recuperável no menor prazo**, não por gravidade abstrata:

1. Reposição de estoque em item que já vende — devolve caixa na mesma semana
2. Anúncio pausado que já vendeu — só destravar
3. Canibalização — decisão de meia hora, efeito imediato na exposição
4. Perda ou risco de buy box — reversível com preço, exige conta de margem
5. Conversão — o mais lento e o mais estrutural

## O que nunca fazer neste diagnóstico

**Não recomende baixar preço sem olhar `margem_minima_percentual`** em
`contas/SLUG/conta.yaml`. Concorrente abaixo do custo é para deixar queimar,
não para acompanhar.

**Não compare produtos de tamanhos diferentes.** Em item sob medida — toldo,
móvel planejado, lona — a dimensão está no título. Compare 230×100 com 230×100.
Comparar com um 120×60 produz "o concorrente está 80% mais barato" e destrói a
credibilidade do relatório inteiro.

**Não trate estoque alto como erro.** Muitos vendedores cadastram milhares de
unidades para não ficar sem. Se a conta faz isso, diga que o alerta de estoque
baixo não vale para aquela linha, em vez de inventar um problema.

**Não confunda correlação com causa.** "Premium vende mais" pode ser porque o
operador promoveu justamente o que já vendia. Aponte a correlação e proponha o
teste controlado — não decrete a lei.

## A entrega

Siga `references/entrega.md`. Em resumo: um artifact HTML com o diagnóstico
completo, e um resumo curto no Telegram com os três achados de maior impacto.
O relatório é para o operador **e para o cliente ver** — escreva com essa
plateia dupla em mente.
