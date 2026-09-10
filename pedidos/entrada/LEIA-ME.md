# Entrada de medições

Aqui entram arquivos `.json` com o que foi medido **fora da API** — hoje, a
posição na busca do Mercado Livre e quem aparece nela.

O vigia importa em até 5 minutos, avalia as regras, manda o que mudou no
Telegram e move o arquivo para `pedidos/lidos/`. Para antecipar, clique em
`fila.bat`.

Reimportar o mesmo arquivo duplicaria a medição — por isso ele sai daqui assim
que é lido. Arquivo que não for JSON válido fica onde está, com o motivo
impresso no log.

O formato e o procedimento de medição estão em
`skills/posicao-na-busca/SKILL.md`.
