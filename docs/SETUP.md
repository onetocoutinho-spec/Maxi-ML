# Setup — do zero à primeira coleta

## 0. Ambiente

**Linux / macOS:**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**Windows:** duplo clique em `instalar.bat` — faz tudo isso e já testa.

Se preferir na mão (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Se o PowerShell recusar o script de ativação, rode antes:
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

## 1. Criar o app no Mercado Livre

Um app só atende todas as contas. Você não precisa de um app por cliente.

1. Acesse https://developers.mercadolivre.com.br/devcenter e crie uma aplicação.
2. **Redirect URI**: precisa ser um endereço **HTTPS público**. O Mercado Livre
   **não aceita `localhost`** — o DevCenter recusa com "O endereço deve ser válido".

   Não precisa existir uma página de verdade ali; você só vai copiar a URL da
   barra de endereço. Duas opções que funcionam:

   - **Uma rota inexistente do seu próprio domínio**, ex:
     `https://seudominio.com.br/ml-callback-zionml`. O navegador cai num 404 e
     você copia a URL. **Importante:** o caminho não pode ser tratado pelo seu
     backend — se ele processar o retorno, vai consumir o `code` antes de você,
     e o `code` vale um uso só.
   - **`https://oauth.pstmn.io/v1/callback`** — endereço oficial de callback do
     Postman, feito para esse tipo de teste. Só exibe o retorno, não consome nada.

   Se você já tem um app em produção com outro redirect, **crie um app separado
   para este projeto** em vez de reaproveitar. Evita disputa pelo code e
   confusão entre duas Secrets.
3. **Escopos**: marque `read`, `write` e `offline_access`.
   Sem `offline_access` você não recebe `refresh_token` e vai reautorizar a cada 6h.
   O `access_token` vale 6 horas; o `refresh_token` vale 6 meses e é de uso único
   (cada renovação devolve um novo — o sistema já grava o novo par sozinho).
4. Guarde o **App ID** (`ML_CLIENT_ID`) e o **Secret Key** (`ML_CLIENT_SECRET`).

## 2. Autorizar cada conta (repetir por conta)

Este é o único passo manual, e ele existe uma vez por conta.

> **Atalho:** `python scripts/autorizar.py <slug>` faz os passos (a) a (e) abaixo
> de forma guiada — monta a URL, troca o code, mostra em qual conta o token caiu
> e só grava o `.env` depois que você confirmar. Se o app tiver PKCE ativado no
> DevCenter, acrescente `--pkce`. O passo a passo manual fica abaixo como referência.

**a)** Abra no navegador, **logado na conta que vai ser autorizada**:

```
https://auth.mercadolivre.com.br/authorization?response_type=code&client_id=SEU_APP_ID&redirect_uri=https://localhost:8080/callback
```

> Dica: use uma janela anônima por conta. Autorizar a conta B enquanto o
> navegador está logado na conta A é o jeito mais comum de trocar credenciais
> sem perceber.

**b)** Aceite. Você cai numa página de erro (esperado). Copie o `code=` da URL.
Ele vale **10 minutos e um uso só**.

**c)** Troque o code por tokens:

```bash
curl -X POST https://api.mercadolibre.com/oauth/token \
  -H 'accept: application/json' \
  -H 'content-type: application/x-www-form-urlencoded' \
  -d 'grant_type=authorization_code' \
  -d 'client_id=SEU_APP_ID' \
  -d 'client_secret=SEU_SECRET' \
  -d 'code=O_CODE_COPIADO' \
  -d 'redirect_uri=https://localhost:8080/callback'
```

A resposta traz `access_token`, `refresh_token` e `user_id`.

**d)** Preencha o `.env` **da pasta daquela conta**:

```bash
cp contas/<slug>/.env.example contas/<slug>/.env
chmod 600 contas/<slug>/.env
```

Preencha `ML_CLIENT_ID`, `ML_CLIENT_SECRET`, `ML_USER_ID`, `ML_REFRESH_TOKEN`.
Os campos `ML_ACCESS_TOKEN` e `ML_TOKEN_EXPIRA_EM` o sistema preenche sozinho.

**e)** Registre o `user_id` em `config/clientes.yaml`, no lugar de `SUBSTITUIR`.
É esse valor que a trava de segurança compara com o token.

**f)** Valide:

```bash
python cli.py checar <slug>
```

Se o nickname devolvido não for o da conta certa, **pare**: você autorizou a
conta errada. Refaça do passo (a) em janela anônima.

## 3. Configurar o que vigiar

Em `contas/<slug>/palavras-chave.yaml`, liste 5–15 termos. Mais que isso vira
ruído e consome chamada à toa.

Em `contas/<slug>/concorrentes.yaml`, liste os vendedores que você acompanha de
perto. Para achar o `seller_id`, abra um anúncio dele e chame:

```bash
curl https://api.mercadolibre.com/items/MLB1234567890 | grep seller_id
```

## 4. Primeira coleta

```bash
python cli.py coletar <slug>
```

A primeira coleta **não gera alertas** — não existe estado anterior para
comparar. É esperado. Da segunda em diante o sistema passa a ter memória.

## 5. Agendar

**Linux / macOS:**

```bash
crontab -e
# 0 8 * * *  /caminho/absoluto/zion-ml/scripts/rotina_diaria.sh
```

**Windows** — duplo clique em `agendar.bat` (registra a cada 3 horas).

Se preferir configurar à mão no Agendador de Tarefas:

```
Programa/script:  C:\caminho\zion-ml\scripts\rotina_diaria.bat
Iniciar em:       C:\caminho\zion-ml
Disparador:       diariamente, 08:00
```

Marque "Executar estando o usuário conectado ou não" se quiser que rode com a
máquina ligada mas sem sessão aberta.

Ou peça ao Claude para criar uma tarefa agendada que roda o script e te manda o
resumo.

## Notas sobre limites

- **Rate limit**: o cliente já trata 429 com espera progressiva. Com 5 contas e
  ~15 termos cada, uma rotina completa fica bem abaixo do limite.
- **`--sem-visitas`**: pular visitas reduz drasticamente o número de chamadas
  (uma por anúncio ativo). Para a rotina diária de contas grandes, use.
- **`refresh_token`**: é de uso único e expira em 6 meses de inatividade. Como
  a rotina roda todo dia, ele se renova sozinho. Se ficar mais de 6 meses parado,
  refaça o passo 2.
- **Escopo de pedidos**: se `/orders/search` falhar, a coleta continua sem
  receita — só confirme que o app tem escopo `read` e que a conta autorizou.
