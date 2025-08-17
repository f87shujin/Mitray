## Mitray Discord Bot (minimal)

1. Create your env file:
   - Copy `.env.example` to `.env`
   - Paste your token into `DISCORD_TOKEN=`

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the bot:
```bash
python main.py
```

Notes:
- `.env` is git-ignored so your token stays local.
- Default command prefix is `!`. Try `!ping` in a server where your bot is present.
- Make sure the Message Content Intent is enabled in the Discord Developer Portal for your application.
