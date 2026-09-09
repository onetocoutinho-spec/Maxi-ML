# MCP do zion-ml — falar com a operação em vez de abrir relatório

`mcp_zion.py` é um servidor MCP que roda **nesta máquina** e entrega ao Claude
o que o zion-ml já sabe: contas, anúncios, margens, alertas, campanhas abertas
e concorrência. Você pergunta em português, ele consulta o banco de snapshots.

Sem `pip install`. Sem serviço na nuvem. O mesmo Python que já roda a rotina.

---

## O que ele NÃO faz

Está escrito no topo do arquivo e vale repetir:

- **não publica, não altera preço, não pausa, não aceita campanha.** Nenhuma
  ferramenta escreve na API do Mercado Livre;
- **não devolve credencial.** Os `.env` continuam sendo lidos só por
  `core.auth`, e apenas na ferramenta `checar_credencial`, que confirma de quem
  é o token e devolve o apelido da loja — nada além disso;
- **não é terminal remoto.** Executar tarefa continua sendo pela fila de
  pedidos, com a mesma lista fixa de comandos de `scripts/fila.py`.

---

## As 17 ferramentas

| Ferramenta | Para quê |
|---|---|
| `listar_contas` | quem é cliente, quais contas, credencial ok, última coleta |
| `checar_credencial` | pergunta ao ML de quem é o token (única que usa rede) |
| `panorama_conta` | reputação, nível, ativos/pausados, vendas e receita |
| `diagnostico_conta` | dinheiro parado, ativo sem estoque, canibalização, conversão |
| `anuncios` | lista da última coleta, com preço de vitrine |
| `anuncio` | um anúncio: tarifa medida, campanhas, margem, histórico |
| `mudancas` | o que mudou entre as duas últimas coletas |
| `historico_preco` | série de preço/estoque/vendas de um anúncio |
| `alertas` | alertas do motor de regras numa janela de horas |
| `margens` | preço contra o piso, por anúncio |
| `promocoes_abertas` | campanhas `candidate` com veredito e quem banca |
| `concorrencia` | quem disputa suas fichas, e o resumo de 7 dias |
| `cupons` | campanhas de cupom: usos, orçamento queimado, anúncios |
| `custo_de_cupom` | quanto o cupom custou por anúncio, medido nos pedidos |
| `encomendar` | deixa um pedido na fila (coletar, mapear, promoções...) |
| `resultado_do_pedido` | lê a saída de um pedido executado |
| `pedidos_recentes` | o que já rodou e o que está na fila |

---

## Conferir antes de ligar

Duplo clique em `mcp-testar.bat`, ou:

```bat
python mcp_zion.py --autoteste
```

Ele imprime as ferramentas registradas, a lista de contas com a data da última
coleta de cada uma, e roda uma amostra de leituras. Se aparecer `ok` em todas,
está apto.

---

## Ligar no aplicativo

Feche o Claude, edite `%APPDATA%\Claude\claude_desktop_config.json` e acrescente
o bloco `zion-ml` dentro de `mcpServers` (se o arquivo não existir, crie com o
conteúdo inteiro abaixo):

```json
{
  "mcpServers": {
    "zion-ml": {
      "command": "C:\\Users\\Maxi do Brasil\\Desktop\\zion-ml\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\Maxi do Brasil\\Desktop\\zion-ml\\mcp_zion.py"]
    }
  }
}
```

Se não existir `.venv` na pasta, troque `command` por `"python"`.

Abra o Claude de novo. As ferramentas aparecem como `zion-ml`. Numa sessão de
nuvem ligada a esta máquina, elas chegam com o prefixo
`mcp__remote-devices__zion-ml__`.

---

## O que perguntar

- "o que mudou na conta do Ênio desde ontem?"
- "quais anúncios da Facilita estão abaixo do piso?"
- "tem campanha aberta que fura a margem em alguma conta?"
- "as três contas da Facilita estão com a Poltrona Mona no mesmo preço?"
- "manda coletar tudo e me avisa quando terminar"
- "quanto já gastei de cupom este mês?"
- "algum cupom queimando orçamento rápido demais?"

---

## Cupons

`cupons` lê as campanhas de cupom do vendedor (`SELLER_COUPON_CAMPAIGN`) que a
conta tiver: quantos foram usados, quanto do orçamento já queimou, o custo
médio por cupom e quais anúncios participam.

Duas coisas que valem mais que o resto:

- **o orçamento é 100% seu.** Na campanha co-participada o ML entra com 1–4%;
  no cupom, com nada. Cupom é custo direto, não oferta a avaliar.
- **`cupons_usados` é da campanha inteira.** A API não diz em qual anúncio cada
  cupom foi usado. Para atribuir por produto é preciso cruzar com os pedidos —
  `/orders/$ID/discounts` e o `coupon_fee` do pagamento.

### Quanto o cupom custou de verdade

```bat
python cli.py cupons <slug> --vendas --dias 60
```

Lê os pedidos, e para cada um que teve cupom consulta `/orders/$ID/discounts`,
guardando o desconto **por anúncio** com o que saiu do vendedor separado do
que o Mercado Livre bancou.

Essa separação não é detalhe. Na primeira sonda da conta da Maxi, os 40
pedidos examinados tinham `coupon_amount` preenchido e `amounts.seller: 0.0`
em todos — eram campanhas do próprio ML viajando no mesmo campo. Medir custo
por `coupon_amount` cobraria do vendedor um desconto que não foi ele quem
pagou.

Pedido já registrado não é relido e nem gasta chamada; rodar a mesma janela de
novo é barato e não duplica.

A coleta vem do `cli.py cupons <alvo>` (ou `encomendar` com `comando: "cupons"`).
Para descobrir, numa conta real, onde o cupom aparece no pedido antes de
escrever qualquer coleta de venda:

```bat
python cli.py cupons <slug> --sondar-vendas --dias 60
```

Essa sonda só lê e não grava nada. Ela diz se o valor do cupom já vem no
`/orders/search` — se vier, dá para atribuir por anúncio sem uma chamada extra
por pedido.

---

## Quando alguma coisa não responder

- **as ferramentas não aparecem no app** — o caminho do `command` está errado,
  ou o Claude não foi reiniciado. Rode o autoteste para separar as duas coisas:
  se ele passa, o problema é a configuração, não o servidor.
- **"sem coleta"** — aquela conta ainda não tem snapshot. `encomendar` com
  `comando: "coletar"` e o slug resolve na próxima passada do vigia.
- **`margens` volta vazia com `linhas_sem_anuncio` alto** — a planilha de custos
  daquela conta não está casando com os anúncios. É o mesmo casamento do
  `cli.py precos`; olhe a planilha, não o MCP.
- **erro estranho** — `data/mcp.log` guarda tudo que o servidor viu. stdout é
  só protocolo; diagnóstico nunca vai para lá.
