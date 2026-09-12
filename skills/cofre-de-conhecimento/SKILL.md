---
name: cofre-de-conhecimento
description: Grava e consulta o cofre de conhecimento da Zion (vault Obsidian em Desktop\zion-cofre) — o que ja foi medido, quem mediu, quando vence e o que ainda nao se sabe. Use quando um experimento ou medicao produzir descoberta nova, quando uma decisao do cliente precisar ficar registrada, quando for afirmar algo ao cliente e precisar checar se a afirmacao sustenta, ou quando pedirem "guarda isso", "registra essa descoberta", "o que a gente sabe sobre X", "isso ainda vale?", "de onde veio esse numero".
---

# Cofre de conhecimento da Zion

O cofre fica em `C:\Users\Maxi do Brasil\Desktop\zion-cofre`. É um vault
Obsidian comum — Markdown e JSON — **fora deste repositório, de propósito**.

Ele guarda o que nenhum banco de snapshot guarda: **a afirmação e o quanto ela
se sustenta**. Quem mediu, quando, por qual via, o que contradiz, e quando o
número para de valer.

## A linha que separa o cofre do repositório

Este repo é **produto**: código, régua, esteira. O cofre é **dado**: o que se
sabe e de onde veio. Confundir os dois é o jeito mais rápido de estragar os dois.

| Fica no repo | Fica no cofre |
|---|---|
| A régua de piso em `core/precificacao.py` | **Por que** a régua é essa, e o experimento que produziu o número |
| O snapshot em `data/zion_ml.db` | A **conclusão** tirada dos snapshots, apontando para a medição |
| O veredito de campanha em `core/promocoes.py` | A decisão do cliente que mudou o limiar, com data e autor |

O cofre **não duplica dado que o banco já tem**. Se a resposta é uma consulta
SQL, ela não vira página — vira, no máximo, a conclusão que a consulta sustentou.

**Nunca entram no cofre:** credencial de qualquer tipo, transcrição de conversa,
e número que o banco já guarda melhor.

## Duas direções, e só uma delas escreve

### Consultar — antes de afirmar qualquer coisa ao cliente

Leia, nessa ordem: `wiki/index.md` para achar a rota, a página da rota, e
`wiki/meta/ledgers/claim-ledger.json` para o estado real da afirmação.

Ao responder, **carregue o estado junto com o fato**:

- ❌ "A busca da API está fechada, não dá para acompanhar concorrente fora do
  catálogo."
- ✅ "Medimos em 26/08 que a busca está fechada — evidência `provisional`, uma
  linha só (nosso app). Suficiente para não prometer acompanhamento ao cliente;
  insuficiente para afirmar como fato técnico se alguém contestar."

Nunca apresente `provisional` como estabelecido, nem resolva um `contested`
escolhendo um lado. Se a afirmação estiver `unsupported`, diga que não se sabe —
é um desfecho legítimo e melhor que inventar.

Consulta **não escreve**. Guardar o resultado é um segundo ato, explícito.

### Gravar — quando algo novo foi medido ou decidido

Dispare quando aparecer: um experimento com resultado, uma medição que muda a
régua, uma decisão do Neto ou do cliente, ou uma crença antiga que caiu.

Uma gravação é **uma rodada só**, com estas peças juntas:

1. **A fonte** — o experimento, a medição, a decisão. ID derivado, nunca
   escolhido. Ver `references/esquema.md`.
2. **A afirmação** — falsificável, com o estado que a evidência sustenta. Ver
   `references/portao-de-evidencia.md`.
3. **A página** — em `regras/`, `bloqueios/`, `decisoes/`, `contas/`,
   `experimentos/` ou `questions/`, com âncora `^id` no parágrafo que a
   afirmação cita.
4. **O índice** — `wiki/index.md` ganha a entrada. Página canônica sem entrada
   no índice vira órfã, e o lint reprova.
5. **O log** — uma linha no topo de `wiki/log.md` com o que a rodada fez.

Página nova sem os cinco não é uma gravação completa.

## O portão de evidência, em uma frase

`accepted` exige fonte ativa, fresca e não-sintética. Afirmação de **alto
risco** exige **duas linhas independentes** — e duas medições nossas pela API do
ML **não são duas linhas**.

Essa é a lição do `list_cost`: ele errou de forma estável por 200 segundos, e
repetir a medição não corrigiu nada, porque o valor errado não muda. Quem salva
é o instrumento diferente — a tela do vendedor.

As chaves de independência em uso e como classificar estão em
`references/portao-de-evidencia.md`. Leia antes de marcar qualquer coisa como
`accepted`.

## Valide sempre — roda nativo no Windows

O motor de escrita do claude-obsidian é recusado no Windows nativo, mas o
**lint é read-only e roda**. Use-o depois de toda gravação:

```bash
python <caminho>/claude-obsidian/scripts/claude-obsidian.py lint --vault "C:\Users\Maxi do Brasil\Desktop\zion-cofre" --format markdown
```

Alvo: `Issues found: 0`. O que cada erro significa e como consertar está em
`references/validar.md`, junto com como obter o clone se ele não estiver por
perto.

Não entregue gravação sem ter rodado. O lint já reprovou três afirmações que
pareciam boas na primeira montagem do cofre.

## O que nunca fazer neste roteiro

**Nunca invente localizador, data, citação ou nível de confiança.** Uma recusa
fundamentada é melhor que uma invenção confiante. Se a evidência não sustenta a
conclusão pedida, grave `unsupported` e diga o que falta.

**Nunca marque `accepted` porque "eu medi e deu certo".** Medição própria é uma
linha de evidência, e alto risco precisa de duas.

**Nunca resolva uma contradição em silêncio.** Duas explicações concorrentes
viram um `contested` com as duas posições, suas evidências, e o teste que
decidiria. Escolher a mais provável e apagar a outra destrói a única coisa que o
cofre tem de valioso.

**Nunca grave fonte ativa sem `refresh_due`.** Conhecimento de marketplace
vence: bloqueio de API muda sem aviso, tarifa muda, banda muda. Fonte sem data
de validade é dívida.

**Nunca escolha o ID de uma fonte.** Ele é derivado de
`stable_source_id(kind, locator, sha256)`. Importe a função do produto; o lint
recusa qualquer outro valor e diz qual seria o certo.

**Nunca reescreva entrada antiga do log.** O histórico é o produto — aqui vale
o mesmo que vale para `snap_*`.

## A entrega

Depois de gravar, diga em três linhas: o que entrou, em que estado ficou, e o
que faria subir de estado. Se o portão reprovou alguma coisa, **conte** — foi o
sistema funcionando, não um erro a esconder.

Se a rodada mudou algo que o cliente vê ou que muda uma recomendação anterior,
avise explicitamente qual recomendação mudou.
