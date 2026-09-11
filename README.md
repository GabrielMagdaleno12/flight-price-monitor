# Flight Price Monitor

Monitora preços de passagens aéreas partindo de São Paulo (GRU/CGH) para uma
lista de destinos que você escolhe, e avisa no Telegram, Discord e e-mail
quando encontra um preço muito bom.

## Configuração (uma vez só)

1. **Telegram**: fale com [@BotFather](https://t.me/BotFather), crie um bot
   com `/newbot` e guarde o token. Envie uma mensagem qualquer para o bot e
   depois acesse `https://api.telegram.org/bot<TOKEN>/getUpdates` para
   pegar o seu `chat_id` (campo `message.chat.id`).
2. **Discord**: nas configurações de um canal do seu servidor, vá em
   Integrações → Webhooks → Novo Webhook, e copie a URL.
3. **E-mail**: gere uma senha de app para sua conta (ex: [Gmail App
   Password](https://myaccount.google.com/apppasswords)). Use a porta
   `587` (STARTTLS) no `SMTP_PORT` — **não** a porta `465` (SSL implícito),
   que muitos guias do Gmail recomendam mas que não funciona com o cliente
   SMTP usado aqui (`smtplib.SMTP` + `starttls()`).
4. No repositório do GitHub, vá em **Settings → Secrets and variables →
   Actions** e adicione:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `DISCORD_WEBHOOK_URL`
   - `SMTP_HOST` (ex: `smtp.gmail.com`)
   - `SMTP_PORT` (ex: `587`)
   - `SMTP_USER` (seu e-mail)
   - `SMTP_PASSWORD` (a senha de app gerada)
   - `EMAIL_TO` (e-mail que vai receber os alertas)
5. O repositório precisa ser **público**. Isso dá minutos ilimitados de
   GitHub Actions; um repositório privado tem só 2.000 min/mês grátis, o
   que não é suficiente para 48 execuções por dia.
6. Em **Settings → Actions → General → Workflow permissions**, selecione
   **"Read and write permissions"**. Sem isso, o passo `git push` do
   workflow falha com erro 403 logo na primeira execução, porque o
   `GITHUB_TOKEN` padrão é somente leitura em repositórios criados depois
   de fevereiro de 2023.
7. Não é preciso criar `data/price_history.json` manualmente — o próprio
   workflow cria e commita esse arquivo automaticamente a cada execução.

## Uso

Edite `config.yaml` para ajustar origem, destinos candidatos, datas (fixas
ou janela flexível) e os limites de alerta (teto de preço e % de queda).

A checagem roda automaticamente pelo GitHub Actions a cada 30 minutos (veja
`.github/workflows/check-flights.yml`). Para rodar manualmente e testar, vá
na aba **Actions** do repositório → **Check flight prices** → **Run
workflow**.

### Sobre o número de requisições por execução

`granularity_days`, o número de destinos e o número de aeroportos de
origem se multiplicam no total de requisições ao Google Flights por
execução (ex: janela de 4 meses com passo de 7 dias × 2 origens × 3
destinos ≈ 108 requisições). Quanto menor o `granularity_days` e quanto
mais origens/destinos, mais requisições — e mais chance de o Google
Flights limitar/bloquear o IP do runner.

CGH (Congonhas) praticamente não tem rotas internacionais, então incluir
`CGH` em `origin` para destinos internacionais desperdiça metade do
orçamento de requisições sem nunca encontrar voos. Para viagens
internacionais, considere usar `origin: [GRU]` apenas.

## Rodando localmente (opcional, para testes)

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Nota sobre moeda

O sistema pede explicitamente a moeda BRL ao Google Flights. Ainda assim,
no primeiro teste manual, confira se os valores retornados parecem
plausíveis em reais — se não, pode ser necessário investigar.
