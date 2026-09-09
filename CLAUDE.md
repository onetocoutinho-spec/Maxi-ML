# zion-ml — contexto para o agente

Operação multi-conta de Mercado Livre da Zion. **Leia isto antes de qualquer ação.**

## A regra que vem antes de todas

Este repositório opera contas de **clientes diferentes**. Operar a conta errada
é o erro mais caro possível aqui — publica produto do cliente A na loja do
cliente B, muda preço de quem não pediu, pausa anúncio que estava vendendo.

Por isso:

- Toda operação é endereçada por **slug de conta**. Não existe conta padrão.
- `MLClient` compara o `user_id` do token com o do registro e **aborta** se
  divergir. Nunca contorne isso, nunca passe `verificar=False`.
- Antes de qualquer **escrita** na API (publicar, alterar, pausar, responder),
  rode `python cli.py checar <slug>` e confirme o nickname devolvido.
- Ao trabalhar dentro de `contas/<slug>/`, leia o `CLAUDE.md` daquela pasta.

## Como está organizado

- `config/clientes.yaml` — única fonte de verdade sobre quem é cliente e quais
  contas ele tem. Nunca contém credencial.
- `contas/<slug>/.env` — credencial isolada. Um por conta. Nunca copiar entre pastas.
- `core/` — código compartilhado, versão única. Corrigiu aqui, corrigiu para todos.
- `data/zion_ml.db` — snapshots imutáveis, todos carimbados com `cliente_id` e `conta_slug`.

## Arquivos que NUNCA devem ser sobrescritos

Estes guardam configuração e credencial do usuário. Ao entregar atualizações,
compare e edite; nunca substitua pelo arquivo de exemplo:

- `.env` (raiz) e `contas/*/.env` — credenciais
- `config/notificacoes.yaml` — provedor, destino, horários, CEP
- `config/clientes.yaml` — user_id das contas autorizadas
- `contas/*/palavras-chave.yaml`, `concorrentes.yaml`, `conta.yaml`

Já aconteceu de uma entrega devolver `provedor: console` por cima de
`provedor: telegram` e as notificações pararem em silêncio.

## Ao mexer no código

- Melhoria de coleta, regra ou relatório vai em `core/` — **nunca** duplicada
  por conta. Se algo é específico de uma conta, vira parâmetro em
  `contas/<slug>/conta.yaml`, não um fork do script.
- Limiar de alerta se ajusta em `config/alertas.yaml`, não no código.
- Snapshots são imutáveis: coleta nova = linha nova. Nunca faça UPDATE em
  `snap_*` — o histórico é o produto.

## Roteiros do projeto

Ficam em `skills/`. Não são skills instaladas — são roteiros que moram aqui e
devem ser seguidos quando o assunto aparecer:

- **`skills/raio-x-conta-ml/SKILL.md`** — diagnóstico completo de uma conta.
  Siga este roteiro sempre que pedirem "raio-x da conta", "analisa a conta do
  <cliente>", "diagnóstico", "auditoria" ou quando uma conta nova for conectada
  e quiserem a primeira leitura. Ele traz as consultas prontas
  (`references/consultas.sql`), as réguas de interpretação
  (`references/interpretacao.md`) e o formato de entrega
  (`references/entrega.md`).

  Comece sempre por `python cli.py diagnostico <slug> --detalhado`, que já
  encontra os padrões mais comuns, e use o roteiro para explicar o porquê e
  montar o relatório.

## Agentes de apoio

Ficam em `.claude/agents/`. São subagentes com contexto próprio: recebem uma
frente, investigam e devolvem a conclusão — sem despejar o banco inteiro aqui.

| Agente | Para quê |
|---|---|
| `ml-margem` | piso, lucro por venda, e a decisão de entrar/sair de campanha |
| `ml-frete` | quanto a loja paga de frete, e por que o ML não libera envio |
| `ml-concorrencia` | ficha de catálogo, buy box, canibalização entre as irmãs |
| `ml-cadastro` | pausado, em revisão, sem envio, sem custo, duplicata |
| `ml-plantao` | o que mudou desde ontem e o que exige decisão hoje |
| `ml-publicar` | recadastra pela esteira: simula, mostra, e só sobe com o seu sim |

Os cinco primeiros **analisam e recomendam** e não escrevem. O `ml-publicar`
escreve, e por isso carrega o protocolo inteiro: `checar` → simular → mostrar →
autorização daquele item → publicar → conferir o que subiu. A
trava não é só instrução: `.claude/hooks/travar-escrita-ml.py` roda antes de
todo Bash e obriga aprovação quando o comando carrega `--publicar`,
`--confirmar`, `--aplicar` ou `--sim`, ou quando tenta UPDATE/DELETE em `snap_*`.
Um subagente trabalha num contexto que você não lê — sem a trava, "analisa a
margem" poderia terminar com anúncio publicado.

Os arquivos de credencial e configuração da lista acima também pedem aprovação
para serem escritos (`permissions.ask` no `.claude/settings.json`), porque o
`ml-publicar` precisa de `Write` para montar fila CSV e o hook só cobre Bash.

As réguas moram em `core/`, não nos agentes: piso em `precificacao.py`, veredito
de campanha em `promocoes.py`. Agente que recalcula por fora passa a discordar
do resto do sistema.

Agentes e hooks são lidos na abertura da sessão — depois de mexer neles, comece
uma sessão nova.

## Conversar com a operação pelo MCP

`mcp_zion.py` é um servidor MCP local (sem dependência nova, stdlib + o próprio
`core/`) que expõe 15 ferramentas de LEITURA: contas, anúncios, margens,
alertas, campanhas abertas, concorrência, mudanças entre coletas. Ligado no
aplicativo, dispensa colar dado no chat.

Nenhuma ferramenta escreve na API do ML. A única que usa rede é
`checar_credencial`, e só para confirmar de quem é o token. Executar tarefa
continua sendo pela fila de pedidos abaixo — o MCP a encomenda pela ferramenta
`encomendar`, reaproveitando a MESMA validação de `scripts/fila.py`.

Conferir: `mcp-testar.bat` (ou `python mcp_zion.py --autoteste`).
Ligar no app e resolver problema: `docs/MCP.md`.
Diagnóstico do servidor: `data/mcp.log` — stdout é só protocolo, nunca log.

## Como pedir uma execução sem terminal

O Claude escreve arquivos nesta pasta mas não roda comandos nesta máquina.
Para encomendar uma tarefa, escreva um arquivo `.pedido` (JSON) em `pedidos/`.
O vigia executa em até 5 minutos e devolve o resultado em `pedidos/feitos/`.

```json
{ "comando": "coletar", "alvo": "enio-toldos-principal" }
```

Só rodam os comandos da lista em `scripts/fila.py`, com argumentos validados
por formato. Não é terminal remoto e não deve virar um: ampliar essa lista
exige pensar no que um arquivo malicioso nessa pasta conseguiria fazer.

## Comandos

```bash
python cli.py contas                # panorama de clientes e contas
python cli.py checar <slug>         # valida credencial (rode antes de escrever)
python cli.py coletar [alvo]        # alvo = slug | cliente_id | todas
python cli.py alertas [alvo]
python cli.py cobertura <slug> --detalhado   # quem tem clássico, premium e catálogo
python cli.py publicar <slug> <MLB-origem>   # recadastra 1 anúncio — SIMULA por padrão;
python cli.py publicar <slug> --lista f.csv  # ou uma fila. Só escreve com --publicar.
# O formulário do ML não oferece Mercado Envios nesta conta; pela API o
# shipping.mode é DECLARADO e o me2 é aceito. Peso nunca é herdado — só por --peso.
python cli.py relatorio [cliente_id]
python cli.py rotina todas          # o que o cron executa

# Painel comparativo: várias contas na MESMA tela (o relatorio acima é por
# cliente). Só lê o banco, não chama a API. Sai em relatorios/painel-metricas.html.
python scripts/painel_metricas.py                    # as três contas de sempre
python scripts/painel_metricas.py --contas a,b       # ou os slugs que quiser

# Página POR loja: o que sobra em cada anúncio, o que a campanha faz com isso,
# e o frete. Usa o piso de core/precificacao.py e o veredito de core/promocoes.py
# — a régua não é duplicada aqui. Sai em relatorios/loja-<slug>.html.
python scripts/painel_loja.py                        # as três
python scripts/painel_loja.py <slug>
```

O visual dos dois painéis mora em `core/painel_visual.py` — tokens, tipografia
e tabela. Mexeu lá, mexeu nos dois; não copie CSS entre os scripts.

## Contexto do negócio

Zion Company é agência de operação de marketplace. Clientes atuais neste repo:
Chinelaria Leilane Neves (calçados, modelo User Products com family_name) e
CASA TAWATY (equipamentos agrícolas, linha STIHL, fluxo de catálogo + tradicional).

## Bloqueios conhecidos da API do Mercado Livre

Verificado com controle em 26/08/2026. Não são bugs do sistema nem permissão
faltando no app — são portas fechadas, e a arquitetura foi desenhada em volta
delas. Antes de "consertar" qualquer coisa aqui, confira se não é isto:

| Endpoint | Resposta | Consequência |
|---|---|---|
| `/sites/MLB/search` (termo ou seller_id) | 403 | não há busca por palavra-chave nem medição de posição |
| `/items/{id}` de terceiro | 403 `access_denied` | não se lê anúncio de outro vendedor por ID |
| `/items?ids=` de terceiro | HTTP 200, **code interno 403** | mesmo bloqueio; o multiget engana quem só olha o status HTTP |

O que continua liberado: `/products/{id}/items` — as ofertas de uma ficha de
catálogo, com preço, vendedor e frete grátis. É por isso que a vigilância
observa FICHAS e não anúncios (`core/vigilancia.py`).

Regra para dizer ao cliente, sem rodeio: concorrente fora do catálogo dá para
DESCOBRIR (busca web, `site:produto.mercadolivre.com.br`), não dá para
ACOMPANHAR. Prometer acompanhamento aí é prometer alerta que nunca chega.
