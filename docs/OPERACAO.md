# Operação diária

## Com que rapidez você fica sabendo

A rotina roda **de hora em hora**. Cada rodada relê os concorrentes já
conhecidos — preço, frete grátis, custo do frete para o CEP de referência,
estoque e status — e compara com a rodada anterior. Mudou, você recebe.

O que **não** roda de hora em hora, e por quê:

| Tarefa | Frequência | Motivo |
|---|---|---|
| Vigiar concorrente conhecido | toda hora | Barato: um multiget para todos, mais o frete dos prioritários |
| Descobrir concorrente novo | 1× ao dia (04h30) | Caro: uma consulta por produto e por vendedor. Concorrente novo não aparece de hora em hora |
| Visitas dos seus anúncios | 1× ao dia (06h) | Uma chamada por anúncio ativo, e o número mal muda em uma hora |

O frete é conferido para os 40 anúncios prioritários por rodada — primeiro os
que você vinculou aos seus. Ajuste em `max_fretes_por_rodada`.

## O ritual de 5 minutos

```bash
python cli.py alertas --horas 24
```

Leia de cima para baixo. A lista já vem ordenada por criticidade. Depois abra
`relatorios/<cliente>/ultimo.html` do cliente que tiver alerta crítico.

## Como ler cada alerta

| Alerta | O que significa | Ação típica |
|---|---|---|
| `meu_anuncio_mudou` | Mudou algo em um anúncio **seu**: título, foto, tipo de anúncio, frete, modo de envio, categoria, catálogo, qualidade, promoção, infração — ou o anúncio sumiu | Cobre o que o ML altera sozinho e o que alguém com acesso à conta mexe sem avisar. Categoria e tipo de anúncio mudam a comissão: confira a margem. |
| `venda_nova` | Um anúncio vendeu | Informativo. Traz quanto entrou e quanto sobrou de estoque. |
| `concorrente_mexeu` | Um concorrente conhecido mudou **o anúncio dele**: preço, frete grátis, custo do frete, estoque ou status | É o alerta mais acionável do sistema. "Ficou sem estoque" e "saiu do ar" são janelas de venda — não são problema seu, são oportunidade. |
| `concorrente_cruzou_preco` | Um concorrente **vigiado e vinculado** ficou mais barato que o anúncio seu correspondente | Cheque a margem mínima em `conta.yaml` antes de baixar. Nem todo cruzamento merece resposta — se ele está abaixo do seu custo, deixe queimar. |
| `buy_box_no_fio` | Você ainda ganha o catálogo, mas por pouco | Aviso antecipado. Decida com calma agora, em vez de reagir depois de perder. |
| `perdeu_buy_box` | Você não é mais o vencedor do catálogo | O alerta traz o `preco_para_ganhar`. Compare com sua margem mínima. Nem sempre vale. |
| `estoque_zerado` | Anúncio ativo com 0 unidades | Repor ou pausar. Ativo sem estoque queima posição na busca. |
| `anuncio_pausado` | O anúncio saiu do ar sozinho | Veja o `sub_status` — costuma ser infração de política ou falta de estoque. |
| `queda_de_posicao` | Você caiu no ranking de mais vendidos da categoria | Verifique se um concorrente novo entrou ou se sua velocidade de venda caiu. |
| `venda_travada` | Vendia e parou | Cruze com visitas: muitas visitas e nenhuma venda é preço; poucas visitas é posição. |
| `reputacao_caiu` | Termômetro piorou | Prioridade máxima. Reputação afeta todos os anúncios da conta ao mesmo tempo. |
| `canibalizacao_interna` | Duas contas do mesmo cliente na mesma busca | Decida qual conta leva o termo. Duas contas suas competindo entre si só entrega margem ao ML. |

## Diagnóstico rápido: visitas × vendas

O snapshot guarda `visitas_7d` e `vendidos`. A leitura:

- **Visitas altas, vendas baixas** → o problema é a oferta: preço, foto, frete, reputação.
- **Visitas baixas, conversão boa** → o problema é exposição: posição, título, tipo de anúncio, investimento em ads.
- **Ambos caindo** → verifique primeiro se o anúncio saiu do ar ou perdeu buy box.

## Consultas úteis direto no banco

```bash
sqlite3 data/zion_ml.db
```

### De onde vem o dado de concorrência

O Mercado Livre **bloqueou a busca pública** (`/sites/MLB/search`) para
aplicações em geral. O rastreio por palavra-chave em resultado de busca não
existe mais — e com ele foi embora a medição de posição num termo específico.
Em troca, três fontes que continuam abertas:

| Fonte | O que dá | Ponto forte |
|---|---|---|
| **Mais vendidos da categoria** | Ranking real da categoria, com preço e vendas | Descobre concorrente novo sozinho, sem você listar ninguém |
| **Catálogo** (`/products`) | Todos os vendedores de um mesmo produto | Comparação limpa: mesma ficha, só muda preço e vendedor |
| **Fichas vigiadas** | Todos os vendedores de uma ficha que você escolheu, a cada rodada | Concorrente que entra no produto aparece sozinho, sem cadastro |

Para acompanhar um concorrente específico, use a **ficha de catálogo** dele —
o endereço com `/p/MLB...`:

```
python cli.py vigiar SLUG LINK_DA_FICHA --comparar-com SEU_MLB
```

O comando confere na API se aquele link é mesmo ficha antes de gravar. Link de
anúncio solto é recusado, e não por escolha nossa: o Mercado Livre devolve
`access_denied` (403) para leitura de anúncio de terceiro por ID. Quem vende
fora do catálogo aparece na pesquisa de mercado do raio-x como retrato do
momento — descobrir dá, acompanhar não.

**O campo `comparar_com` é o que faz o alerta de preço existir.** Ele liga o
anúncio do concorrente a um anúncio seu. Sem esse vínculo, o anúncio é
acompanhado mas não gera alerta de preço — e isso é proposital: comparar um
toldo 380×100 com um 200×60 só porque apareceram na mesma busca produz alerta
falso, e alerta falso ensina você a ignorar a lista inteira.

As duas comparações confiáveis são o **buy box** (mesmo produto de catálogo,
ficha idêntica) e a **ficha vigiada com vínculo** (você disse quem enfrenta
quem).

Quando o mesmo vendedor mexe na mesma coisa em vários produtos na mesma rodada,
os alertas viram uma mensagem só, com os três maiores movimentos. Concorrente
grande reajusta a tabela inteira de uma vez; vinte mensagens iguais no celular
ensinam a ignorar o alerta. O limite fica em `agrupar_a_partir_de`, em
`config/alertas.yaml`.

```sql
-- Histórico de preço de um anúncio
SELECT coletado_em, preco, estoque, vendidos
FROM snap_anuncio WHERE item_id = 'MLB123456789' ORDER BY coletado_em DESC LIMIT 30;

-- Quem mais aparece no top da minha categoria (candidatos a vigiar de perto)
SELECT seller_nickname, COUNT(*) n, AVG(preco) preco_medio, MIN(posicao) melhor_pos
FROM snap_concorrente
WHERE conta_slug = 'enio-toldos-principal' AND origem = 'destaques'
  AND coletado_em >= datetime('now','-7 days')
GROUP BY seller_nickname ORDER BY n DESC LIMIT 15;

-- Minha posição média por termo na última semana
SELECT termo, AVG(posicao) pos_media, MIN(posicao) melhor, MAX(posicao) pior
FROM snap_posicao
WHERE conta_slug = 'chinelaria-principal' AND coletado_em >= datetime('now','-7 days')
GROUP BY termo ORDER BY pos_media;

-- Anúncios que mais venderam nos últimos 7 dias
SELECT titulo, MAX(vendidos) - MIN(vendidos) AS vendas
FROM snap_anuncio
WHERE conta_slug = 'tawaty-principal' AND coletado_em >= datetime('now','-7 days')
GROUP BY item_id HAVING vendas > 0 ORDER BY vendas DESC LIMIT 20;
```

## Regras de segurança que não se negocia

1. **Um `.env` por pasta.** Nunca copie `.env` entre contas "só para testar".
2. **Nunca desabilite a trava** de `user_id` no `MLClient`. Ela existe para
   transformar um erro caro num erro barato.
3. **Antes de qualquer escrita** (publicar, alterar preço, pausar), rode
   `python cli.py checar <slug>` e confirme o nickname.
4. **`chmod 600`** em todo `.env`.
5. Se um cliente sair, **remova a pasta inteira** e revogue o app na conta dele.

## Calibrando o ruído

Se você está recebendo alerta demais, mexa em `config/alertas.yaml` — não no
código. Os dois ajustes que mais reduzem barulho:

- `concorrente_cruzou_preco.tolerancia_percentual`: suba para 3–5% se
  concorrente pequeno oscilando centavos estiver enchendo a lista.
- `meu_preco_caiu_ou_subiu`: desligue se você usa reprecificador automático,
  senão toda alteração vira alerta.

Alerta que você aprende a ignorar é pior que alerta que não existe.
