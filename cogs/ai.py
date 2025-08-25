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
        self.long_term_summary = None  # Optional summary of long-term memory

    def format_conversation_history(self, history: List[Tuple[str, str]]) -> str:
        """Format conversation history into a string"""
        formatted = ""
        for author, msg in history:
            formatted += f"{author}: {msg}\n"
        return formatted.strip()

    async def generate_response(self, prompt: str, channel_id: int, username: str) -> str:
        """Generate a response using Ollama API, with summary and last 10 turns as context."""
        try:
            # Add the new message to history before generating response
            self.conversation_history[channel_id].append((username, prompt))

            # Build context from last 35 messages (short-term memory)
            history = list(self.conversation_history[channel_id])[-35:]
            context = ""
            for author, msg in history:
                context += f"{author}: {msg}\n"
            context = context.strip()

            # Add summary at the top if available
            if self.long_term_summary:
                full_prompt = f"Summary of previous conversation:\n{self.long_term_summary}\n\n{context}\n{username}: {prompt}\nMitray:"
            else:
                full_prompt = f"{context}\n{username}: {prompt}\nMitray:"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base}/generate",
                    json={
                        "model": self.model_name,
                        "prompt": full_prompt,
                        "stream": False
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                bot_response = result.get("response", "Sorry, I couldn't generate a response.")

                # Add bot's response to history
                self.conversation_history[channel_id].append(("Mitray", bot_response))

                return bot_response
        except Exception as e:
            self.logger.error(f"Error generating response: {e}")
            return "Sorry, I encountered an error while processing your request."

    async def load_channel_history(self, channel: discord.TextChannel, limit: int = 10) -> None:
        """Load recent message history from the channel including usernames, print for debug."""
        messages = []
        async for msg in channel.history(limit=limit):
            if msg.content:
                author = f"{msg.author.name}"
                messages.append((author, msg.content))
        messages.reverse()
        self.conversation_history[channel.id] = deque(messages, maxlen=10)

        # Print debug info: last 10 messages and user tags
        print("\n[DEBUG] Last 10 messages in channel:")
        for author, content in self.conversation_history[channel.id]:
            print(f"{author}: {content}")
        if self.conversation_history[channel.id]:
            print(f"[DEBUG] Last user tag: {self.conversation_history[channel.id][-1][0]}")
        else:
            print("[DEBUG] No messages found in channel history.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bot messages and messages from other channels
        if message.author.bot or message.channel.id != self.target_channel_id:
            return

        try:
            async with message.channel.typing():
                response = await self.generate_response(
                    message.content, 
                    message.channel.id,
                    message.author.name
                )
                await message.reply(response)
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")

    async def configure(self, channel_id: int, model_name: str):
        """Configure the AI cog with necessary parameters"""
        self.target_channel_id = channel_id
        self.model_name = model_name
        self.logger.info(f"AI configured for channel {channel_id} using model {model_name}")
        
        # Check if channel exists before loading history
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            self.logger.error(f"Could not find channel with ID {channel_id}")
            return
            
        # Load channel history
        await self.load_channel_history(channel)

async def setup(bot: commands.Bot):
    ai_cog = AI(bot)
    await bot.add_cog(ai_cog)
    
    # Add a listener for when the bot is ready
    @bot.event
    async def on_ready():
        try:
            # Configure the cog after the bot is ready
            await ai_cog.configure(
                channel_id=1407544434408558774,  # Channel ID
                model_name="mitray"  # Using our custom Mitray model
            )
            ai_cog.logger.info("AI cog configured successfully")
        except Exception as e:
            ai_cog.logger.error(f"Failed to configure AI cog: {e}")
