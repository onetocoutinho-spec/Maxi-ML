# zion-ml — operação multi-conta de Mercado Livre

Estrutura para gerenciar **N clientes × N contas** de Mercado Livre a partir de
um único lugar, acompanhando anúncios próprios e concorrentes, com relatório
diário e alertas imediatos.

## O princípio da estrutura

Duas coisas precisam ser verdadeiras ao mesmo tempo, e elas puxam para lados opostos:

1. **Credencial precisa ser isolada.** O erro mais caro desta operação é mexer
   na conta errada. Por isso cada conta tem sua própria pasta com seu próprio
   `.env`, e o cliente da API é instanciado por slug, com verificação de
   `user_id` que aborta se houver divergência.
2. **Dados precisam ser comparáveis.** Você quer ver todas as contas lado a lado,
   comparar as três contas de um mesmo cliente, cruzar seus anúncios com os
   concorrentes. Isso pede banco único.

A solução é separar por camada: **credencial isolada fisicamente** (uma pasta,
um `.env`, permissão 600), **dados unificados logicamente** (um SQLite, toda
tabela carimbada com `cliente_id` e `conta_slug`), e **um único núcleo de código**
para não ter cinco versões divergentes do mesmo script.

```
zion-ml/
├── config/
│   ├── clientes.yaml        ← registro central: quem é cliente, quais contas tem
│   └── alertas.yaml         ← regras e limiares (ligar/desligar sem tocar em código)
├── core/                    ← núcleo compartilhado — versão única
│   ├── auth.py              ← token por conta, refresh automático, grava o novo par
│   ├── ml_api.py            ← cliente da API + TRAVA de conta
│   ├── db.py                ← SQLite, snapshots imutáveis
│   ├── collectors.py        ← o que coletar
│   ├── rules.py             ← o que é alerta
│   └── report.py            ← painel HTML
├── contas/
│   ├── _template/           ← base para criar conta nova
│   └── <slug>/
│       ├── .env             ← credencial DESTA conta (nunca versionar)
│       ├── conta.yaml       ← margem, comissão, regras do negócio
│       ├── palavras-chave.yaml
│       ├── concorrentes.yaml
│       └── CLAUDE.md        ← trava de contexto para o agente
├── data/                    ← zion_ml.db (histórico completo)
├── relatorios/<cliente>/    ← HTML diário + ultimo.html
├── scripts/
│   ├── nova_conta.py        ← cria conta nova a partir do template
│   └── rotina_diaria.sh     ← para o cron
└── cli.py
```

## Instalação

**Windows:** dê duplo clique em `instalar.bat`. Ele cria o ambiente, instala as
dependências e já lista os clientes registrados.

**Linux / macOS:**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python cli.py contas          # deve listar os clientes do registro
```

Depois de qualquer coleta, `painel.bat` abre os relatórios no navegador.

O passo do OAuth do Mercado Livre está em [docs/SETUP.md](docs/SETUP.md).

## Uso diário

```bash
python cli.py rotina todas          # coleta + alertas + relatório (é isso que o cron roda)
python cli.py alertas               # o que apareceu nas últimas 24h
python cli.py coletar tawaty        # só um cliente
python cli.py coletar chinelaria-principal   # só uma conta
python cli.py relatorio             # regera os painéis
python cli.py testar-notificacao    # confere se o WhatsApp está configurado
python cli.py notificar --resumo    # manda o resumo do dia agora
```

Alertas e agendamento: [docs/NOTIFICACOES.md](docs/NOTIFICACOES.md).

- **`instalar_automacao.bat`** — liga tudo. Um clique, uma vez.
- `status.bat` — confere se a automação está de pé
- `fila.bat` — executa agora o que estiver em `pedidos/`
- `agora.bat` — menu único: coletar, resumo, mapa, alertas, painel
- `vigia.bat` — vigilância contínua de concorrentes (a cada 5 min)
- `autorizar.bat` — conecta uma conta do Mercado Livre
- `concorrentes.bat` — mapa de concorrentes com preço, frete e reputação
- `vigiar.bat` — acrescenta uma ficha de catálogo à vigilância, por link
- `telegram.bat` — configura o canal de alertas (2 minutos, do zero ao teste)
- `agendar.bat` — registra a rotina a cada 3 horas no Agendador do Windows

O alvo de qualquer comando aceita três formas: `todas`, um `cliente_id`, ou um
`slug` de conta. É a mesma gramática em todo lugar.

## Adicionar uma conta

```bash
python scripts/nova_conta.py minha-conta --cliente meu-cliente --nome "Minha Conta"
```

O script cria a pasta, preenche o `CLAUDE.md` e imprime o bloco YAML pronto
para colar em `config/clientes.yaml`. Depois: preencher o `.env`, rodar
`python cli.py checar minha-conta` e confirmar que o nickname devolvido é o certo.

## Cliente com várias contas

Marque `coordenar_preco: true` no cliente em `config/clientes.yaml`. Isso liga
a regra de **canibalização interna**: quando duas contas do mesmo dono aparecem
na mesma palavra-chave, o sistema avisa e mostra a diferença de preço entre elas
— que é exatamente o problema que multi-conta cria quando ninguém está olhando.

## O que é coletado

| Coleta | Fonte | Serve para |
|---|---|---|
| Preço, estoque, vendidos, status, saúde | `/users/{id}/items/search` + `/items` | movimentação dos anúncios próprios |
| Visitas 7 dias | `/items/{id}/visits/time_window` | conversão (visitas ÷ vendas) |
| Pedidos pagos 7 dias | `/orders/search` | receita e velocidade de venda |
| Mais vendidos da categoria | `/highlights/MLB/category/{id}` | ranking real + descoberta de concorrente novo |
| Produtos de catálogo por termo | `/products/search` | achar o produto certo |
| Vendedores de um produto | `/products/{id}/items` | todos os preços do mesmo produto |
| Fichas de catálogo vigiadas | `/products/{id}/items` | quem entra e quem sai do produto, sozinho |
| Buy box | `/items/{id}/price_to_win` | ganhar/perder o catálogo |
| Reputação e métricas | `/users/{id}` | saúde da conta |

> Dois bloqueios do Mercado Livre moldam o sistema: a busca pública por termo
> (`/sites/MLB/search`) e a leitura de **anúncio de terceiro por ID** — tanto
> `/items/{id}` quanto o multiget `/items?ids=` devolvem `access_denied`. Por
> isso concorrente é acompanhado pela **ficha de catálogo**, nunca pelo link do
> anúncio dele. Fora do catálogo dá para descobrir, não dá para acompanhar. Rode `diagnosticar.bat` para ver o que o seu
> app libera hoje — a coleta se adapta ao que estiver aberto e uma fonte
> indisponível não derruba as outras.

Tudo é gravado como **snapshot com carimbo de tempo**. Nada é sobrescrito — é
por isso que o sistema consegue dizer "mudou desde ontem" em vez de só mostrar
o estado atual.
