import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv


def load_token() -> str:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        print("ERROR: DISCORD_TOKEN is not set. Create a .env file (see .env.example).", file=sys.stderr)
        sys.exit(1)
    return token


def create_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True  # Enable reading message content for prefix commands
    bot = commands.Bot(command_prefix="mit", intents=intents)

    @bot.event
    async def on_ready():
        assert bot.user is not None
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")
        print("Bot is ready.")

    @bot.command(name="ping")
    async def ping(ctx: commands.Context):
        await ctx.send("Pong!")

    return bot


def main() -> None:
    token = load_token()
    bot = create_bot()
    bot.run(token)


if __name__ == "__main__":
    main()
