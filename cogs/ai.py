import discord
from discord.ext import commands
import httpx
import json
import asyncio
import logging
from pathlib import Path
from collections import defaultdict, deque
from typing import Dict, Deque, List, Tuple

class AI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_base = "http://localhost:11434/api"
        self.target_channel_id = None  # Will be set from config
        self.model_name = None  # Will be set from config
        self.logger = logging.getLogger("mitray.ai")
        self.conversation_history: Dict[int, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=10))
        self.system_prompt = ""  # Empty since prompt is handled by Ollama model

    def format_conversation_history(self, history: List[Tuple[str, str]]) -> str:
        """Format conversation history into a string"""
        formatted = ""
        for user_msg, bot_msg in history:
            formatted += f"User: {user_msg}\nAssistant: {bot_msg}\n\n"
        return formatted.strip()

    async def generate_response(self, prompt: str, channel_id: int) -> str:
        """Generate a response using Ollama API with conversation history"""
        try:
            # Get conversation history for this channel
            history = list(self.conversation_history[channel_id])
            conversation_context = self.format_conversation_history(history)
            
            # Prepare the full prompt with history
            full_prompt = f"{conversation_context}\n\nUser: {prompt}\nAssistant:"
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base}/generate",
                    json={
                        "model": self.model_name,
                        "prompt": full_prompt,
                        "system": self.system_prompt,
                        "stream": False
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                bot_response = result.get("response", "Sorry, I couldn't generate a response.")
                
                # Add the new exchange to history
                self.conversation_history[channel_id].append((prompt, bot_response))
                
                return bot_response
        except Exception as e:
            self.logger.error(f"Error generating response: {e}")
            return "Sorry, I encountered an error while processing your request."

    async def load_channel_history(self, channel: discord.TextChannel, limit: int = 10) -> None:
        """Load recent message history from the channel"""
        messages = []
        async for msg in channel.history(limit=limit):
            if not msg.author.bot and msg.content:
                # Find the bot's response to this message
                async for response in channel.history(limit=1, after=msg):
                    if response.author.bot and response.reference and response.reference.message_id == msg.id:
                        messages.insert(0, (msg.content, response.content))
                        break
        
        # Update conversation history with loaded messages
        self.conversation_history[channel.id] = deque(messages, maxlen=10)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bot messages and messages from other channels
        if message.author.bot or message.channel.id != self.target_channel_id:
            return

        try:
            async with message.channel.typing():
                response = await self.generate_response(message.content, message.channel.id)
                await message.reply(response)
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")

    def configure(self, channel_id: int, model_name: str):
        """Configure the AI cog with necessary parameters"""
        self.target_channel_id = channel_id
        self.model_name = model_name
        self.logger.info(f"AI configured for channel {channel_id} using model {model_name}")
        
        # Schedule loading of channel history
        asyncio.create_task(self.load_channel_history(self.bot.get_channel(channel_id)))

async def setup(bot: commands.Bot):
    ai_cog = AI(bot)
    # These values will need to be configured after cog is loaded
    ai_cog.configure(
        channel_id=1407544434408558774,  # Chanelle's channel ID
        model_name="mitray"  # Using our custom Mitray model
    )
    await bot.add_cog(ai_cog)
