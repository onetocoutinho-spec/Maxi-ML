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

- **`skills/cofre-de-conhecimento/SKILL.md`** — grava e consulta o cofre de
  conhecimento da Zion. Siga sempre que um experimento ou medição produzir
  descoberta nova, quando uma decisão do cliente precisar ficar registrada, ou
  antes de afirmar ao cliente algo que dependa de medição — "o que a gente sabe
  sobre X", "isso ainda vale?", "de onde veio esse número", "guarda isso".

  O cofre é um vault Obsidian em `C:\Users\Maxi do Brasil\Desktop\zion-cofre`,
  **fora deste repositório de propósito**: aqui é produto, lá é dado. A régua
  continua em `core/`; o cofre guarda **por que** a régua é essa, o experimento
  que produziu o número, quanto aquilo sustenta e quando vence. Ele traz o
  formato exato (`references/esquema.md`), a régua de aceitação de evidência
  (`references/portao-de-evidencia.md`) e como validar
  (`references/validar.md`).

  A regra que mais morde: **duas medições nossas pela API do ML não são duas
  linhas de evidência.** É a lição do `list_cost`, que errou de forma estável
  por 200 segundos. Afirmação de alto risco precisa de instrumento diferente —
  a tela do vendedor, a planilha do cliente ou a documentação.

  Valide toda gravação com o `lint`, que é read-only e **roda nativo no
  Windows** mesmo com a escrita do produto bloqueada:
  `python "…\Desktop\claude-obsidian\scripts\claude-obsidian.py" lint --vault "…\Desktop\zion-cofre"`.

## Agentes de apoio

Ficam em `.claude/agents/`. São subagentes com contexto próprio: recebem uma
frente, investigam e devolvem a conclusão — sem despejar o banco inteiro aqui.

| Agente | Para quê |
|---|---|
| `ml-margem` | piso, lucro por venda, e a decisão de entrar/sair de campanha |
| `ml-frete` | quanto a loja paga de frete, e por que o ML não libera envio |
| `ml-concorrencia` | ficha de catálogo, buy box, canibalização entre as irmãs |
| `ml-cadastro` | pausado, em revisão, sem envio, sem custo, duplicata |
| `ml-conversao` | anúncio ativo que não vende: sem exposição, sem conversão ou teto de categoria — e quanto vale consertar |
| `ml-plantao` | o que mudou desde ontem e o que exige decisão hoje |
| `ml-publicar` | recadastra pela esteira: simula, mostra, e só sobe com o seu sim |

Os seis primeiros **analisam e recomendam** e não escrevem. O `ml-publicar`
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

## O orquestrador inicia a conversa sozinho (melhor esforço)

`.claude/hooks/lembrete-orquestrador.py` roda no evento `SessionStart` (toda
vez que uma sessão nova abre neste projeto) e, se o `orquestrador-ml` ainda não
rodou hoje, devolve uma instrução pra sessão rodar sozinha antes de atender o
que for pedido — publicando um Artifact com o relatório completo e mandando um
resumo curto pro Telegram via `core.notify.enviar(texto)`.

Dois arquivos guardam o estado disso, escritos pela própria sessão depois de
cada rodada — não são gerados por nenhum comando do `cli.py`:

- `data/orquestrador.ultima_execucao` — timestamp local da última rodada. É
  isso que o hook compara com "hoje" pra decidir se está devendo.
- `data/orquestrador.artifact_url` — URL do Artifact publicado, pra cada
  rodada **atualizar a mesma página** em vez de criar uma nova por dia.

Isto é melhor esforço, não garantia: nenhum mecanismo aqui acorda o computador
com o app fechado (rotina de nuvem não alcança `.env`/banco local; `CronCreate`
morre com a sessão). O `SessionStart` cobre "abriu o app mais tarde"; um
`CronCreate` de `30 6 * * *`, rearmado a cada sessão nova (o próprio hook lembra
disso), cobre "deixou o app aberto a noite toda" — mas se o app ficar fechado o
dia inteiro, ninguém roda nada sozinho.

### Sincronizar o "Painel de Agentes" (estado ao vivo, melhor esforço)

O artifact "Painel de Agentes" (mapa dos agentes) declara a capability `db` e lê o
documento `estado/sistema` para mostrar dado real em vez de simulação: última
rodada do orquestrador, batimento do Vigia e alertas críticos das últimas 24h.
Uma página publicada não lê arquivo local nem chama `localhost` — por isso
essa leitura só fica fresca quando **a sessão** empurra o dado, o mesmo
melhor-esforço de cima, não uma garantia de tempo real.

`.claude/workflows/orquestrador-ml.js` já devolve esse estado (fase "Estado
real": lê `data/vigia.batimento`, `data/vigia.subiu` e conta `!` vs `·` de
`.venv/Scripts/python.exe cli.py alertas --horas 24`, por conta). Depois que o
workflow retornar, junto com escrever os dois arquivos de estado de cima, a
sessão chama o Artifact tool:

```
action: write_db, url: <URL do Painel de Agentes>, db_op: set,
collection: estado, doc_id: sistema,
data: {
  atualizadoEm: <agora, ISO, pego com `date`>,
  orquestrador: { ultimaExecucaoIso: <o mesmo valor gravado em orquestrador.ultima_execucao> },
  vigia: resultado.estado_real.vigia,
  alertas24h: resultado.estado_real.alertas24h,
}
```

Críticos (`!`) são o que importa mostrar em destaque — médios/informativos
(`·`) hoje passam de 4 mil numa varredura de 24h nas contas Facilita/Maxi
(concorrência ruidosa, já mapeada), então o painel deliberadamente não
manda esse número bruto pra tela.

### Disparo real de agente pelo Painel de Agentes (fila `pedidos`, melhor esforço)

Cada um dos 7 agentes formais tem um seletor de conta e um botão "Invocar
agente" no Painel de Agentes. Isso não é simulação: o clique escreve um pedido real
em `pedidos/<id-do-agente>` (`{agente, conta, status:'pendente', criadoEm}`)
no banco do artifact — a página em si não pode chamar `Task`, só pode
escrever nesse documento e assinar a resposta. Quem lê a fila e executa de
verdade é **uma sessão do Claude Code com o loop de processamento rodando**
(mesmo limite de sempre: sem app aberto, sem execução).

O loop, a cada rodada:

1. `read_db` no artifact (url do Painel de Agentes), `collection: pedidos`,
   `db_op: list` — pega todo mundo com `status: 'pendente'`.
2. Para cada um, **valida antes de tocar em qualquer coisa**: `agente` tem
   que ser um dos 7 ids em `.claude/agents/` e `conta` tem que ser um slug
   com `.env` de verdade (hoje: `chinelaria-principal`,
   `enio-toldos-principal`, `facilita-brasil-principal`,
   `facilita-decoralli`, `jb-moveis-principal`, `jb-moveis-jelcdecor`,
   `jb-moveis-ejprime`, `maxi-brasil-principal`). Qualquer coisa fora dessa
   lista grava `status:'erro'` e pula — nunca invoca agente com dado que a
   página não ofereceu no seletor.
3. Grava `status:'rodando'` (`write_db` `update`), roda `Agent` de verdade
   com `subagent_type: <agente>` e um prompt citando a conta.
   **`ml-publicar` entra nesse fluxo, mas com uma linha extra no prompt:
   simule e mostre, nunca publique de verdade — não há humano acompanhando
   este disparo pra dar o "sim" que o protocolo dele exige.** Isso não é
   só instrução: o próprio agente já para antes de escrever sem
   autorização explícita, então o pior caso é ele simular e ficar esperando.
4. Grava o resultado de volta (`status:'concluido'`, `resultado:<resposta>`,
   `concluidoEm`) — ou `status:'erro'` se o Agent falhar.

A página assina `pedidos/<id>` e reage sozinha (nó pulsa, painel atualiza),
sem precisar recarregar — mas só reflete o que o loop já processou, nunca
o estado real do disco no instante exato do clique.

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
