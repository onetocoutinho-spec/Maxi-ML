# Como entregar o raio-x

Duas peças: um **artifact** com o diagnóstico completo e um **resumo curto no
Telegram**. O artifact é para ler com calma e mostrar ao cliente; o Telegram é
para saber que ele ficou pronto e o que tem de mais urgente.

## O artifact

Carregue a skill `artifact-design` antes de escrever a página. O que segue é o
que este relatório em específico precisa ter — não substitui a orientação de
design.

**Estrutura que funciona**, na ordem:

1. **Nome do cliente e data da coleta.** Uma frase que já entrega a tese —
   "o que os números mostram não é problema de preço, é de arrumação" — em vez
   de "relatório de análise da conta".
2. **Faixa de números** — anúncios, ativos, pausados, vendas e receita de 7
   dias, conversão. Seis no máximo. Logo abaixo, uma linha explicando a
   conversão em palavras: "1.600 visitas resultaram em 8 vendas".
3. **"O que custa dinheiro hoje"** — no máximo três achados, cada um com
   severidade, título afirmativo e dois parágrafos. O primeiro diz o que é com
   o número junto; o segundo diz por que importa.
4. **A evidência em tabela** — o achado mais forte merece a tabela que o
   sustenta. Canibalização pede agrupamento por medida, com a linha vencedora
   destacada.
5. **O que está saudável** — sempre. Um relatório só com problemas perde
   credibilidade e desmotiva o cliente.
6. **O que fazer, em ordem numerada** — aqui a numeração é informação: é
   sequência de prioridade, e a ordem é por dinheiro recuperável no menor prazo.
7. **Ressalvas de leitura do monitoramento** — o que os alertas não vão pegar
   naquela conta e por quê. Isso evita que o operador confie no que não deve.

**Tom.** Escreva para quem opera, não para impressionar. Frase afirmativa,
número ao lado da afirmação, sem adjetivo carregando o que o dado deveria
carregar. "43 vendas, o maior giro da conta" vale mais que "excelente
performance".

**Título do artifact.** Nome curto e específico: `Raio-X NomeDaLoja`. Nada de
"Relatório de Análise de Conta".

## O resumo no Telegram

```
python cli.py notificar --resumo
```

Para um texto próprio, use `core.notify.enviar(texto)`. Formato: `*negrito*`,
no máximo três achados, uma linha cada, e o número junto. Quem lê no celular
decide se abre o artifact agora ou depois.

## Guardar

O artifact fica publicado e pode ser atualizado depois — republicar no mesmo
caminho de arquivo mantém a URL. Para acompanhar a evolução do cliente,
**atualize o mesmo artifact** em vez de criar um novo a cada mês: assim o
cliente tem um link só, sempre atual.
