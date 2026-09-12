# O formato exato do cofre

O cofre segue o contrato do `claude-obsidian` v2.2.0. Isso não é preciosismo:
é o que faz o `lint` validar, e o que faria um `adopt` funcionar sem atrito se
o WSL entrar um dia.

## Layout

```text
zion-cofre/
├── .claude-obsidian.json          identidade do workspace
├── inbox/                         entrada visível — nada é apagado sozinho
├── .raw/                          bytes imutáveis, nome = SHA-256, create-only
├── wiki/
│   ├── index.md   log.md   hot.md   overview.md
│   ├── contas/ bloqueios/ regras/ decisoes/ experimentos/ questions/ canvases/
│   ├── Painel do cofre.base
│   └── meta/ledgers/{source-ledger,claim-ledger}.json
└── .vault-meta/                   runtime descartável, gitignored
```

## As rotas, e o que vai em cada uma

| Rota | `type` | Guarda |
|---|---|---|
| `contas/` | `entity` | Uma por slug: modelo de anúncio, banda, travas de escrita |
| `bloqueios/` | `concept` | Porta fechada da API, com data de verificação |
| `regras/` | `concept` | Comissão, piso, frete, catálogo — a régua e o porquê dela |
| `decisoes/` | `concept` | O que foi decidido, por quem, quando e por quê |
| `experimentos/` | `source` | O teste que sustenta a regra, com os números crus |
| `questions/` | `question` | Pergunta com resposta e estado de evidência visível |

Regra de roteamento: se a coisa é **uma medição**, vai para `experimentos/` e
vira fonte. Se é **uma conclusão** tirada dela, vai para `regras/` e vira
afirmação. Uma não substitui a outra — a regra aponta para o experimento.

## Frontmatter

YAML plano, datas `YYYY-MM-DD`, listas em bloco, wikilink entre aspas. Nada
aninhado.

```yaml
---
type: concept
title: Frete segue a caixa gravada no anúncio
status: evergreen
created: 2026-09-11
updated: 2026-09-11
revisar_ate: 2026-10-11
tags:
  - frete
  - "2026"                       # tag só-número entre aspas, senão vira número
domain: mercado-livre
related:
  - "[[O frete do vendedor é o list_cost do free]]"
sources:
  - "[[Levantamento de 13 anúncios SFBENY140]]"
claim_ids:
  - clm-caixa-decide-frete
---
```

Obrigatórios: `type`, `title`, `status`, `created`, `updated`, `tags`.

`status` em uso: `seed`, `active`, `developing`, `evergreen`, `answered`,
`provisional`, `contested`, `deprecated`, `archived`.

Duas propriedades são **deste cofre**, não do produto: `revisar_ate` (espelha o
`refresh_due` da fonte, para o painel) e, em `decisoes/`, `decidido_em` +
`decidido_por`.

> O rótulo no frontmatter **não é evidência**. Quem determina suporte é o
> claim-ledger. O frontmatter existe para navegação e para o `.base`.

## Âncoras

Toda afirmação aponta para um parágrafo específico da página, por âncora de
bloco. O validador **verifica que a âncora existe** — não dá para citar um
trecho que não está lá.

```markdown
A tarifa acompanha a caixa gravada no anúncio, monotonicamente. ^caixa-decide
```

No ledger: `"location": {"path": "wiki/regras/…md", "anchor": "^caixa-decide"}`.

## O livro-razão de fontes

```json
"src-ed33dcdbb974a671a2f5": {
  "origin": { "kind": "manual", "locator": "wiki/experimentos/….md" },
  "content_kind": "dataset",
  "title": "Levantamento de 13 anúncios SFBENY140 (JB + JELC)",
  "authority": "primary",
  "content_sha256": null,
  "ingested_at": "2026-09-11",
  "retrieved_at": "2026-09-11",
  "refresh_due": "2026-10-11",
  "review_status": "active",
  "independence_key": "medicao-api-ml",
  "pages": ["wiki/experimentos/….md"],
  "supersedes": null
}
```

- `kind` ∈ `file` · `url` · `manual`
- `content_kind` ∈ `document` `webpage` `dataset` `image` `audio` `video`
  `code` `conversation` `synthetic` `other`
- `authority` ∈ `official` `primary` `secondary` `community` `synthetic`
  `unknown`
- `review_status` ∈ `unreviewed` `active` `superseded` `rejected`
- Fonte `active` exige `retrieved_at` **e** `refresh_due`.

### O ID é derivado, não escolhido

```python
import sys
sys.path.insert(0, "<caminho>/claude-obsidian")
from claude_obsidian.ledgers import stable_source_id

sid = stable_source_id(kind, locator, content_sha256)   # -> "src-ed33dcdb…"
```

Trabalhe com apelidos legíveis enquanto monta e remapeie no fim. Se errar, o
lint diz exatamente qual ID seria o correto. O `source_id` no frontmatter da
página de experimento tem que ser o canônico também.

## O livro-razão de afirmações

```json
"clm-caixa-decide-frete": {
  "text": "A tarifa de frete que o vendedor paga acompanha a caixa gravada no anúncio, de forma monotônica.",
  "risk": "high",
  "assessment": "accepted",
  "confidence": "high",
  "reviewed_at": "2026-09-11",
  "location": { "path": "wiki/regras/….md", "anchor": "^caixa-decide" },
  "notes": "Duas linhas independentes: medição por API e leitura do painel.",
  "supersedes": null,
  "evidence": [
    { "source_id": "src-ed33dcdb…", "relation": "supports" },
    { "source_id": "src-8e149a99…", "relation": "supports" },
    { "source_id": "src-4f21bb0c…", "relation": "context" }
  ]
}
```

- `risk` ∈ `normal` `high`
- `assessment` ∈ `accepted` `provisional` `contested` `unsupported`
  `deprecated`
- `confidence` ∈ `high` `medium` `low` `unknown`
- `relation` ∈ `supports` `contradicts` `context`
- `accepted` **exige** `reviewed_at`.
- `context` não conta como suporte. Uma afirmação cujas evidências são todas
  `context` não tem suporte nenhum, e o lint reprova se ela estiver `accepted`.

O texto precisa ser **falsificável**. "O frete está caro" não é afirmação;
"a tarifa acompanha a caixa gravada, monotonicamente" é.

## O `.base`

`wiki/Painel do cofre.base` tem três views: tudo que o cofre sabe, o que vence,
e as perguntas abertas. Ao criar propriedade nova que mereça coluna, acrescente
lá — e lembre que subtrair duas datas devolve **milissegundos**, então divida
por `86400000` antes de arredondar.
