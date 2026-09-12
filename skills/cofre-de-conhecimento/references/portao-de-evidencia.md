# O portão de evidência

A régua que decide em que estado uma afirmação entra no cofre. Ela é a única
coisa que separa este cofre de uma pasta de anotações bonitas.

## Os cinco estados

| Estado | Quando usar |
|---|---|
| `accepted` | Tem fonte ativa, fresca e não-sintética. Alto risco exige **duas independentes**. |
| `provisional` | Indício real, suporte insuficiente. Tratar como hipótese ao falar. |
| `contested` | Há evidência contraditória. As duas posições ficam, ninguém vence em silêncio. |
| `unsupported` | Não se sabe. Desfecho final legítimo. |
| `deprecated` | Já foi verdade, deixou de ser. Aponte para o que substituiu. |

## Quando uma afirmação é de alto risco

Marque `risk: high` quando errar custa caro de verdade:

- Muda preço, piso ou decisão de campanha em conta de cliente.
- Determina o que se **promete** ao cliente (cobertura, acompanhamento, prazo).
- Leva a encerrar, pausar ou apagar anúncio.
- Vira régua em `core/` e passa a valer para todas as contas.

Se errar só produz um relatório impreciso, é `normal`.

## As chaves de independência em uso

Duas fontes que compartilham `independence_key` contam como **uma linha de
evidência**. É aqui que a maior parte do engano mora.

| `independence_key` | O que é | Vale como |
|---|---|---|
| `medicao-api-ml` | Qualquer leitura nossa pela API do ML, por qualquer script | **Uma linha só**, não importa quantas medições |
| `painel-vendedor-ml` | O que o Neto lê na tela do vendedor | Linha independente da API |
| `planilha-cliente` | Custo e frete que o cliente informou | Linha independente |
| `decisao-cliente` | Determinação do Neto ou do cliente | Autoridade, não medição |
| `documentacao-ml` | Documentação oficial do Mercado Livre | Linha independente |

### Por que duas medições nossas não são duas linhas

Em 11/09/2026 o `list_cost` devolveu R$ 161,78 para quatro duplicatas boas e
**manteve o valor por 5 medições ao longo de 200 segundos**. A tela mostrava
R$ 38,18 nas quatro. Quase apagamos quatro anúncios bons.

Repetir a medição não validou nada, porque o valor errado não muda. O que
salvou foi o **instrumento diferente**. Se o método está errado, ele erra
igual todas as vezes — e a estabilidade da leitura parece confirmação sem ser.

Por isso: uma afirmação de alto risco sustentada só por `medicao-api-ml` é
`provisional`, por mais medições que tenha. Para promover, é preciso a tela, a
planilha ou a documentação.

## Autoridade

| `authority` | Na nossa operação |
|---|---|
| `official` | ML: painel do vendedor, documentação. Cliente: decisão registrada. |
| `primary` | Medição nossa direta — o experimento que a gente rodou. |
| `secondary` | Relatório derivado, resumo de terceiro. |
| `community` | Fórum, grupo, relato de outro vendedor. |
| `synthetic` | Saída de modelo, inferência sem medição. **Nunca sustenta `accepted`.** |
| `unknown` | Não se sabe de onde veio. Trate como não-suporte. |

`synthetic` existe no vocabulário exatamente para **não** poder sustentar
afirmação aceita. Conversa de chat não é evidência independente — nem a minha.

## Frescura

Fonte `active` precisa de `refresh_due`. Prazos que temos usado:

| O que | Prazo | Porquê |
|---|---|---|
| Comportamento de frete e me2 | **1 mês** | Muda sem aviso e já mudou |
| Bloqueio de endpoint da API | **3 meses** | Muda sem aviso, mas devagar |
| Tarifa e comissão | **3 meses** | Segue a política do ML |
| Decisão do cliente | **6 meses** | Reconfirmar a banda faz parte do serviço |
| Comportamento de catálogo | **3 meses** | |

Passou do `refresh_due`, a afirmação que depende dela vira **stale**. Stale não
é falso — é "não confira mais sem remedir". Diga isso ao usar.

## Como decidir o estado, na prática

1. A afirmação é falsificável? Se não, reescreva até ser.
2. Errar custa caro? → `risk: high`.
3. Liste as fontes que **suportam** (`context` não conta).
4. Agrupe por `independence_key`. Quantas linhas distintas sobraram?
5. Alguma fonte é `synthetic` ou `unknown`? Ela não conta.
6. Alguma fonte **contradiz**? → `contested`, e pare aqui.
7. Zero linhas → `unsupported`. Uma linha + alto risco → `provisional`.
   Uma linha + risco normal, fonte fresca e ativa → `accepted`.
   Duas linhas + alto risco → `accepted`.
8. `accepted` exige `reviewed_at`.

## Registre o que faria subir de estado

Sempre que gravar `provisional`, escreva em `notes` **qual medição promoveria**.
É o que transforma o cofre em lista de trabalho em vez de lista de dúvidas.

> "Sondagem com controle, mas uma só linha: nosso app, nosso token. Repetir de
> outro app/token promoveria para accepted."

E quando gravar `contested`, escreva **o teste que decide**:

> "Publicar a receita como primeiro item do dia e medir após 40 min. Se der
> 36,68 com família própria, a posição A cai."

## Dois erros que já custaram caro aqui

**Tratar leitura imediata ao POST como verdade.** O ML troca a caixa declarada
minutos depois, e a tarifa leva até ~40 min para assentar. Medição feita cedo
demais entra no cofre como fato e envenena tudo que depende dela. Se a fonte é
uma leitura pós-publicação, diga na `notes` quanto tempo depois foi medida.

**Confundir ausência de disputa com ausência de concorrente.** `snap_concorrente`
não traz o próprio vendedor, e a busca por palavra-chave está fechada. "Não
achei" é `unsupported`, não `accepted` de "não existe".
