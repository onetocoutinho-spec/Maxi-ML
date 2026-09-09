# Fila de pedidos

Deixe aqui um arquivo `.pedido` (JSON) e ele será executado na próxima rodada
do vigia — em até 5 minutos — ou na rotina da próxima hora, o que vier antes.
O resultado aparece em `feitos/` com o mesmo nome, extensão `.log`.

Serve para encomendar tarefas sem abrir nada: o Claude escreve o pedido, a
sua máquina executa, e ele lê o resultado depois.

## Formato

```json
{
  "comando": "mapear",
  "alvo": "enio-toldos-principal",
  "opcoes": { "--cep": "80010000" },
  "flags": ["--detalhado"]
}
```

## O que pode ser pedido

`coletar` · `mapear` · `diagnostico` · `relatorio` · `notificar` · `alertas`
· `contas` · `checar` · `vigiar`

Nada além disso roda. Não é um terminal remoto: cada comando declara quais
opções aceita e o formato de cada valor, e o que não casa é **recusado e
arquivado**, nunca interpretado. Um pedido com `"comando": "rm"` vira uma
linha de log dizendo que foi recusado.

## Exemplo pronto

Copie `exemplo.pedido.txt` para `coletar-agora.pedido` e espere.
