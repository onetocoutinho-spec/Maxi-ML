# Alertas no WhatsApp

O objetivo é você **não abrir arquivo nenhum**. O que precisa de ação te procura;
o resto fica no painel para quando você quiser olhar.

## Como funciona

A rotina roda a cada 3 horas. Em cada rodada:

- **Alerta crítico e novo** → mensagem na hora.
- **Alerta não-crítico** → guardado, entra só no resumo das 8h.
- **Alerta já enviado** → nunca reenviado. Cada alerta é marcado no banco depois
  de sair. Sem isso, o mesmo aviso chegaria 5 vezes por dia e você silenciaria
  o número na primeira semana — que é o jeito mais comum de um sistema de
  alertas morrer.
- **Entre 22h e 7h** → nada é enviado. Fica acumulado para a primeira rodada
  da manhã. Concorrente que baixou preço às 3h não é acionável às 3h.

Existe teto de 8 alertas por mensagem. Se um dia algo der errado e gerar 200,
você recebe os 8 mais graves e um "… e mais 192" — uma mensagem útil em vez de
duzentas inúteis.

## Telegram (o que está em uso)

Duplo clique em `telegram.bat`. Ele te guia:

1. Você cria o bot no **@BotFather** (`/newbot`, escolhe nome e usuário) e cola
   o token que ele devolve.
2. O script valida o token e mostra o nome do bot — confira se é o seu.
3. Você manda qualquer mensagem para o bot; ele captura o `chat_id` sozinho.
   Essa é a parte que normalmente dá trabalho e some aqui.
4. Ele grava o `.env`, aponta o provedor e manda uma mensagem de teste.

Se a mensagem de teste chegar, acabou. Duplo clique em `agendar.bat` e o
sistema passa a te procurar sozinho.

As mensagens usam `*negrito*` (sintaxe do WhatsApp). No Telegram isso é
convertido para HTML automaticamente, com escape — título de produto com `&`
ou `<` não quebra a mensagem. Quando você migrar para WhatsApp, o mesmo texto
funciona sem mudar nada.

## Migrar para WhatsApp depois

Uma linha: troque `provedor: telegram` por `zapi`, `evolution` ou `meta` em
`config/notificacoes.yaml`, preencha as credenciais no `.env` da raiz e o
`destino` com o número. Nada mais muda — regras, horários, dedupe e formato
continuam iguais.

## Os provedores de WhatsApp

WhatsApp não tem API aberta: precisa de um intermediário. Os três suportados,
com o trade-off honesto de cada um:

| Provedor | Custo | Esforço | Observação |
|---|---|---|---|
| **Evolution API** | Grátis (você hospeda) | Alto — precisa de um servidor | Open source, muito usada no Brasil. Sem mensalidade, mas a manutenção é sua. |
| **Z-API** | Mensalidade | Baixo — cadastro e pronto | Serviço brasileiro. É o caminho mais curto se você não quer administrar servidor. |
| **Meta Cloud API** | Grátis até um limite | Médio — exige conta business verificada | Oficial. Restrição séria: fora da janela de 24h desde a sua última mensagem, só envia *template* aprovado. Para alerta espontâneo isso atrapalha. |

Se quiser começar hoje sem custo e sem servidor, **Telegram** também está
implementado e leva 2 minutos (crie um bot no @BotFather). Não é onde você já
olha, mas funciona enquanto você decide o WhatsApp.

## Configurar

1. Em `config/notificacoes.yaml`, troque `provedor: console` pelo escolhido e
   preencha o `destino` (55 + DDD + número, só dígitos).

2. Copie `.env.example` para `.env` **na raiz** e preencha as credenciais do
   provedor. Esse `.env` é diferente dos das contas — aqui não tem nada do
   Mercado Livre.

3. Teste antes de confiar:

```
.venv\Scripts\python.exe cli.py testar-notificacao
```

Se a mensagem chegar no seu WhatsApp, está pronto. Se não chegar, o comando
mostra o erro exato do provedor.

## Agendar

Duplo clique em `agendar.bat`. Ele registra a tarefa no Agendador do Windows
rodando a cada 3 horas a partir das 8h. Para desfazer: `agendar.bat /remover`.

A máquina precisa estar ligada na hora. Se ela costuma ficar desligada, vale
considerar rodar isso num servidor pequeno em vez do seu desktop.

## Calibrar

Tudo isso se ajusta em `config/notificacoes.yaml` e `config/alertas.yaml`, sem
tocar em código:

- Recebendo demais? Suba `concorrente_cruzou_preco.tolerancia_percentual` para
  3–5% e desligue `meu_preco_caiu_ou_subiu`.
- Quer o resumo em outro horário? `hora_do_resumo`.
- Quer silêncio maior? `janela_ativa`.

Alerta que você aprende a ignorar é pior que alerta que não existe. Se em duas
semanas um tipo de alerta nunca gerou ação, desligue.
