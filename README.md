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
   Password](https://myaccount.google.com/apppasswords)).
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

## Uso

Edite `config.yaml` para ajustar origem, destinos candidatos, datas (fixas
ou janela flexível) e os limites de alerta (teto de preço e % de queda).

A checagem roda automaticamente pelo GitHub Actions a cada 30 minutos (veja
`.github/workflows/check-flights.yml`). Para rodar manualmente e testar, vá
na aba **Actions** do repositório → **Check flight prices** → **Run
workflow**.

## Rodando localmente (opcional, para testes)

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Nota sobre moeda

O `fast-flights` consulta o Google Flights e o preço retornado pode vir em
USD dependendo da região consultada, não necessariamente em BRL. Na primeira
execução manual (veja o plano de testes), confira a moeda retornada e ajuste
`price_ceiling_brl` em `config.yaml` de acordo se for o caso.
