import os
import sys
import asyncio

import discord
from discord.ext import commands
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Logging setup: console + rotating file
log_dir = Path(__file__).resolve().parent
log_file = log_dir / "bot.log"
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(fmt)
fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
fh.setLevel(logging.DEBUG)
fh.setFormatter(fmt)
logger.addHandler(ch)
logger.addHandler(fh)

# reduce overly noisy loggers if needed
logging.getLogger("discord").setLevel(logging.INFO)
logging.getLogger("asyncio").setLevel(logging.INFO)
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
    intents.voice_states = True     # Enable voice state updates
    intents.guilds = True           # Enable guild events
    bot = commands.Bot(command_prefix="mit ", intents=intents)

    @bot.event
    async def on_ready():
        assert bot.user is not None
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")
        print("Bot is ready.")
        print(f"Command prefix: 'mit '")
        print(f"Loaded commands: {[cmd.name for cmd in bot.commands]}")
        print(f"Total commands: {len(bot.commands)}")
        print(f"Available cogs: {[cog_name for cog_name in bot.cogs.keys()]}")
        print(f"Total cogs: {len(bot.cogs)}")

    return bot


def ensure_opus_available() -> bool:
    """Try to ensure the libopus library is available for voice.

    Returns True if an Opus implementation is loaded, False otherwise.
    """
    try:
        if discord.opus.is_loaded():
            logger.info("Opus library already loaded for voice")
            return True
    except Exception:
        # older/alternate builds may not expose is_loaded the same way
        pass

    candidates = [
        "libopus-0.dll",
        "libopus.dll",
        "opus.dll",
        "libopus-0",
        "opus",
    ]
    for cand in candidates:
        try:
            discord.opus.load_opus(cand)
            logger.info("Loaded Opus library from: %s", cand)
            return True
        except Exception:
            continue

    logger.warning("Opus audio library not found. Voice audio will be silent until Opus is installed.")
    logger.warning("On Windows, place a copy of libopus-0.dll on your PATH or into the venv Scripts folder.")
    logger.warning("You can also try: pip install opuslib  (may provide a Python wrapper but a DLL is still typically required)")
    return False


async def load_cogs(bot: commands.Bot) -> None:
    """Load all cogs (command modules)"""
    import importlib
    import inspect

    # list of cog modules to load
    cog_modules = ["cogs.commands", "cogs.music", "cogs.fun", "cogs.ai", "cogs.google"]
    for mod_name in cog_modules:
        # try the normal extension loader first (works with modern discord.py async setup)
        try:
            await bot.load_extension(mod_name)
            print(f"✅ Successfully loaded {mod_name} via bot.load_extension")
            continue
        except Exception as e:
            # extension loader failed; we'll try a manual import + setup fallback
            print(f"⚠️ bot.load_extension failed for {mod_name}: {e}")

        try:
            mod = importlib.import_module(mod_name)
            setup_func = getattr(mod, "setup", None)
            if setup_func:
                # support async and sync setup functions
                if asyncio.iscoroutinefunction(setup_func):
                    await setup_func(bot)
                else:
                    # sync setup may add the cog itself or return a Cog instance
                    result = setup_func(bot)
                    # if the setup returned a Cog instance, register it
                    if isinstance(result, commands.Cog):
                        bot.add_cog(result)
                print(f"✅ Successfully loaded {mod_name} (manual setup)")
                continue

            # no setup found; try to find a Cog subclass in the module and add it
            cog_cls = None
            for obj in vars(mod).values():
                if inspect.isclass(obj) and issubclass(obj, commands.Cog) and obj is not commands.Cog:
                    cog_cls = obj
                    break
            if cog_cls:
                bot.add_cog(cog_cls(bot))
                print(f"✅ Successfully loaded {mod_name} (added {cog_cls.__name__})")
            else:
                print(f"❌ No setup() or Cog subclass found in {mod_name}")
        except Exception as e:
            print(f"❌ Failed to load {mod_name}: {e}")
    # cogs.music removed per repository cleanup; add new music implementation or cog when ready
    # Example for future synchronous loading:
    # try:
    #     bot.load_extension("cogs.music")
    #     print("✅ Successfully loaded cogs.music")
    # except Exception as e:
    #     print(f"❌ Failed to load cogs.music: {e}")


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
