import os
import sys
import asyncio

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
    bot = commands.Bot(command_prefix="mit ", intents=intents)

    @bot.event
    async def on_ready():
        assert bot.user is not None
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")
        print("Bot is ready.")
        print(f"Command prefix: 'mit '")
        print(f"Loaded commands: {[cmd.name for cmd in bot.commands]}")
        print(f"Total commands: {len(bot.commands)}")

    return bot


async def load_cogs(bot: commands.Bot) -> None:
    """Load all cogs (command modules)"""
    try:
        await bot.load_extension("cogs.commands")
        print("✅ Successfully loaded cogs.commands")
    except Exception as e:
        print(f"❌ Failed to load cogs.commands: {e}")


async def main() -> None:
    """Main function to run the bot"""
    token = load_token()
    bot = create_bot()
    
    # Load all cogs before starting the bot
    await load_cogs(bot)
    
    # Start the bot
    await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
