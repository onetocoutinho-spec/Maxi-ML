# Validar o cofre

O `lint` do `claude-obsidian` é determinístico, **read-only**, e — ao contrário
da escrita — **roda nativo no Windows**. Não há desculpa para entregar gravação
sem validar.

## O comando

```bash
python "C:\Users\Maxi do Brasil\Desktop\claude-obsidian\scripts\claude-obsidian.py" lint --vault "C:\Users\Maxi do Brasil\Desktop\zion-cofre" --format markdown
```

Alvo: `Issues found: 0`.

Sem `--format markdown` sai JSON, com `summary.issues_found` e
`summary.category_counts` — melhor quando você só quer o número. Use
`python -X utf8` se o console engasgar com acento.

Confirme também a seleção do cofre quando algo parecer estranho:

```bash
python "C:\Users\Maxi do Brasil\Desktop\claude-obsidian\scripts\claude-obsidian.py" doctor --vault "C:\Users\Maxi do Brasil\Desktop\zion-cofre"
```

Deve voltar `"ok": true` e `"selection_source": "explicit"`.

## Se o validador não estiver lá

Ele mora em `Desktop\claude-obsidian` — é código de terceiro (MIT), irmão do
cofre, e **não é o cofre**. Se sumir:

```bash
cd "C:\Users\Maxi do Brasil\Desktop" && git clone --depth 1 https://github.com/AgriciDaniel/claude-obsidian.git
```

Não precisa instalar nada: o núcleo é biblioteca-padrão.

## O que cada erro significa

### `dead links`

O `[[Alvo]]` não resolve. Quase sempre é página citada no índice antes de
existir, ou acento/hífen diferente do nome do arquivo. Confira o nome exato —
`—` (travessão) e `-` (hífen) são caracteres diferentes.

### `ambiguous targets` / `duplicate basenames`

Dois arquivos com o mesmo basename em pastas diferentes. Ou renomeie um, ou
use caminho relativo ao cofre no link: `[[regras/Nome]]`.

### `orphans`

Página que ninguém aponta. Quase sempre significa que você esqueceu a entrada
em `wiki/index.md`. **Toda página canônica criada entra no índice na mesma
rodada** — é a invariante que impede o cofre de apodrecer.

Órfão pode ser intencional, mas nesse cofre ainda não há caso legítimo.

### `missing frontmatter`

Falta `type`, `title`, `status`, `created`, `updated` ou `tags`. Ver
`esquema.md`.

### `empty sections`

Cabeçalho sem nada embaixo. Ou escreva, ou tire o cabeçalho.

### `stale index entries`

O índice aponta para coisa que mudou de lugar ou sumiu.

### `provenance errors` — os que importam

São os que reprovam raciocínio, não formatação.

| Mensagem | O que fazer |
|---|---|
| `source ID must equal canonical identity src-…` | Você escolheu o ID. Use o valor que a mensagem dá, ou derive com `stable_source_id`. |
| `high-risk acceptance requires two independent sources` | Duas fontes com a mesma `independence_key` são uma linha. Ou ache um instrumento diferente, ou baixe para `provisional`. **Não baixe o `risk` só para passar.** |
| `accepted claims require fresh active support` | A afirmação não tem nenhuma fonte `supports` ativa e fresca. Cheque se você usou `context` onde queria `supports`, ou se o `refresh_due` venceu. |
| `active sources require an explicit refresh_due date` | Fonte ativa sem data de validade. Escolha o prazo pela tabela de `portao-de-evidencia.md`. |
| `accepted claims require an ISO review date` | Falta `reviewed_at`. |
| `anchor does not exist in wiki/…` | A âncora `^id` citada não está na página. O validador confere de verdade — não dá para citar trecho que não existe. |
| `ingested file sources require SHA-256` | Fonte `kind: file` precisa do hash do conteúdo. |

## A regra de ouro sobre esses erros

**Não conserte o erro contornando a régua.**

Baixar `risk: high` para `normal`, trocar `supports` por `context`, ou inventar
uma segunda fonte faz o lint passar e destrói a única coisa que o cofre tem de
valioso. Se a evidência não chega para `accepted`, o estado certo é
`provisional` — e isso é uma informação útil, não uma falha.

Na primeira montagem do cofre o portão reprovou três afirmações que pareciam
boas. As três estavam erradas mesmo. Nenhuma teria sido pega na leitura.

## Depois de validar

Rode uma vez mais **depois** de qualquer conserto, e só então reporte. Diga o
número de páginas, links e issues — é a evidência de que a rodada fechou.
