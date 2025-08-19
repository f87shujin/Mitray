import os
import asyncio
import tempfile
import shutil
from typing import Deque
from collections import deque
import ssl
import certifi

import discord
from discord.ext import commands
import logging
import yt_dlp
import urllib3
from pathlib import Path
import sounddevice as sd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import io
import wave

async def create_audio_source(url: str) -> discord.AudioSource:
    """Create an FFmpegOpusAudio source for the given URL."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extract_audio': True,
        'ignoreerrors': True,
        'no_color': True,
        'geo_bypass': True,
        'nocheckcertificate': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        },
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            raise RuntimeError("Could not extract video information")
        
        url = info.get('url')
        if not url:
            # Try direct URL extraction from formats
            formats = info.get('formats', [])
            if not formats:
                raise RuntimeError("No playable formats found")
            # Get best audio format
            audio_formats = [f for f in formats if f.get('acodec') != 'none']
            if audio_formats:
                url = audio_formats[0]['url']
            else:
                url = formats[0]['url']

    # FFmpeg options for optimal audio quality
    ffmpeg_options = {
        'options': '-vn -bufsize 64k',  # Disable video, set buffer size
        'before_options': (
            '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 '  # Handle network issues
            '-protocol_whitelist file,http,https,tcp,tls,crypto,pipe '     # Allow required protocols
            '-tls_verify 0'                                                # Disable SSL verification
        )
    }
    
    # Create FFmpegOpusAudio source
    return await discord.FFmpegOpusAudio.from_probe(url, **ffmpeg_options)


class Music(commands.Cog):
    """Simple music cog using pytube to download audio and ffmpeg to play."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_queues: dict[int, Deque[str]] = {}
        self.current_files: dict[int, str] = {}
        self.play_locks: dict[int, asyncio.Lock] = {}
        self.log = logging.getLogger("mitray.music")
        
        # Configure SSL context with certifi certificates
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            urllib3.util.ssl_.DEFAULT_CIPHERS += ':HIGH:!DH:!aNULL'
            urllib3.disable_warnings()
            self.ssl_context = ssl_context
        except Exception as e:
            self.log.warning(f"Failed to configure SSL context: {e}")
            self.ssl_context = None

        try:
            if discord.opus.is_loaded():
                self.log.info("Opus is loaded for voice")
            else:
                self.log.warning("Opus is NOT loaded; voice audio will be silent until libopus is available")
        except Exception:
            self.log.warning("Opus availability could not be determined; ensure libopus DLL is available on Windows PATH")

    def _ensure_queue(self, guild_id: int):
        if guild_id not in self.guild_queues:
            self.guild_queues[guild_id] = deque()
            self.play_locks[guild_id] = asyncio.Lock()

    async def _download_audio(self, url: str) -> str:
        """Return a direct audio stream URL (uses yt-dlp extract_info without downloading)."""
        self.log.info("Extracting stream URL for %s", url)

        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,  # Disable SSL certificate verification
            'nocheckcertificate_ffmpeg': True,  # Also disable for FFmpeg
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            },
            'socket_timeout': 15,
            'retries': 3
        }
        
        # Add SSL context if available
        if hasattr(self, 'ssl_context') and self.ssl_context:
            ydl_opts['ssl_context'] = self.ssl_context

        def _extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                # If extract_info provides a direct url, use it
                if info is None:
                    raise RuntimeError('yt-dlp returned no info')
                if 'url' in info and info.get('url'):
                    return info.get('url')
                # otherwise pick the best audio format url
                formats = info.get('formats') or []
                audio_formats = [f for f in formats if f.get('acodec') and f.get('acodec') != 'none']
                if audio_formats:
                    # sort by tbr/abr or bitrate
                    audio_formats.sort(key=lambda f: int(f.get('tbr') or f.get('abr') or 0), reverse=True)
                    return audio_formats[0].get('url')
                if formats:
                    return formats[-1].get('url')
                raise RuntimeError('No playable stream URL found')

        loop = asyncio.get_event_loop()
        out_url = await loop.run_in_executor(None, _extract)
        self.log.info("Extracted stream URL for %s -> %s", url, out_url)
        return out_url

    async def _play_next(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        self._ensure_queue(guild_id)
        async with self.play_locks[guild_id]:
            # if nothing in queue, nothing to do
            if not self.guild_queues[guild_id]:
                return

            url = self.guild_queues[guild_id].popleft()
            try:
                # Get the direct audio URL from YouTube
                stream_url = await self._download_audio(url)
                
                try:
                    # Create FFmpeg Opus audio source
                    source = await create_audio_source(stream_url)
                    self.log.info("Created audio source for %s", url)
                except Exception as e:
                    self.log.exception("Audio setup failed for %s", url)
                    await ctx.send(f"❌ Failed to setup audio source: {e}")
                    self.bot.loop.create_task(self._play_next(ctx))
                    return
                
            except Exception as e:
                self.log.exception("Download failed for %s", url)
                await ctx.send(f"❌ Failed to get audio stream: {e}")
                # try next track if available
                self.bot.loop.create_task(self._play_next(ctx))
                return

            # Store source for cleanup
            self.current_files[guild_id] = source

            # ensure there is a voice client connected to the author's channel
            voice: discord.VoiceClient | None = ctx.guild.voice_client or discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
            channel = None
            if ctx.author and getattr(ctx.author, 'voice', None):
                channel = ctx.author.voice.channel

            if not voice or not voice.is_connected():
                if channel is None:
                    await ctx.send("❌ Can't join voice channel: author is not in a voice channel.")
                    # cleanup audio source if created
                    try:
                        if guild_id in self.current_files:
                            source = self.current_files.pop(guild_id)
                            if isinstance(source, PCMAudioSource):
                                source.cleanup()
                    except Exception:
                        pass
                    return
                try:
                    self.log.info("Connecting to voice channel %s", channel.name)
                    voice = await channel.connect()
                    self.log.info("Connect returned; waiting for stable connection for %s", channel.name)
                    # wait for voice client to report connected state (race avoidance)
                    connected = False
                    for _ in range(20):
                        # small sleep to allow handshake to settle
                        await asyncio.sleep(0.25)
                        voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
                        if voice and getattr(voice, 'is_connected', lambda: False)():
                            connected = True
                            break
                    if not connected:
                        raise RuntimeError('Voice client failed to reach connected state')
                    self.log.info("Connected to voice channel %s", channel.name)
                except Exception as e:
                    self.log.exception("Failed to connect to voice channel %s: %s", channel, e)
                    # try to resolve existing client again
                    voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
                    if not voice or not voice.is_connected():
                        await ctx.send(f"❌ Failed to connect to voice channel: {e}")
                        try:
                            if guild_id in self.current_files:
                                source = self.current_files.pop(guild_id)
                                if isinstance(source, PCMAudioSource):
                                    source.cleanup()
                        except Exception:
                            pass
                        return

            def _after(error):
                # schedule cleanup and next play
                async def _cleanup_and_next():
                    try:
                        if guild_id in self.current_files:
                            source = self.current_files.pop(guild_id)
                            if hasattr(source, 'cleanup'):
                                await source.cleanup()
                    except Exception as e:
                        self.log.error("Error cleaning up audio source: %s", e)
                    finally:
                        # play next track if any
                        await self._play_next(ctx)

                coro = _cleanup_and_next()
                fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
                try:
                    fut.result()
                except Exception:
                    pass
            # Get the FFmpeg source that we stored earlier
            source = self.current_files[guild_id]  # This is our FFmpegOpusAudio instance

            # attempt to start playback, retry if not connected yet
            play_attempts = 0
            while play_attempts < 4:
                try:
                    voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
                    if not voice or not voice.is_connected():
                        self.log.warning("Voice client not connected yet, waiting before play (attempt %s)", play_attempts + 1)
                        await asyncio.sleep(0.5)
                        play_attempts += 1
                        continue

                    voice.play(source, after=_after)
                    await ctx.send(f"🎶 Now playing: <{url}>")
                    self.log.info("Started playback for %s in guild %s", url, guild_id)
                    break
                except discord.ClientException as e:
                    # Not connected to voice or other client exception
                    self.log.warning("ClientException during play: %s (attempt %s)", e, play_attempts + 1)
                    await asyncio.sleep(0.5)
                    play_attempts += 1
                    continue
                except Exception as e:
                    self.log.exception("Failed to start playback for %s: %s", url, e)
                    await ctx.send(f"❌ Failed to play audio: {e}")
                    break
            # cleanup is handled in the _after callback above

    @commands.command(name="join")
    async def join(self, ctx: commands.Context):
        """Join the voice channel the author is in."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ You are not in a voice channel.")
            return
        channel = ctx.author.voice.channel
        if ctx.voice_client and ctx.voice_client.is_connected():
            await ctx.voice_client.move_to(channel)
            await ctx.send(f"Moved to {channel.name}")
            return
        await channel.connect()
        await ctx.send(f"✅ Joined {channel.name}")

    @commands.command(name="leave")
    async def leave(self, ctx: commands.Context):
        """Leave voice channel and cleanup."""
        if ctx.voice_client and ctx.voice_client.is_connected():
            await ctx.voice_client.disconnect()
        guild_id = ctx.guild.id
        if guild_id in self.guild_queues:
            self.guild_queues.pop(guild_id, None)
        if guild_id in self.current_files:
            try:
                source = self.current_files.pop(guild_id)
                if hasattr(source, 'cleanup'):
                    await source.cleanup()
            except Exception:
                pass
        await ctx.send("👋 Left voice channel and cleaned up.")

    @commands.command(name="play")
    async def play(self, ctx: commands.Context, *, query: str):
        """Enqueue a YouTube URL (or direct link). Use full URL for best results."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ You are not in a voice channel.")
            return
        # If query looks like a plain search term, tell user to provide URL
        if not (query.startswith("http://") or query.startswith("https://")):
            await ctx.send("❗ Please provide a YouTube URL. Search is not implemented in this simple player.")
            return

        guild_id = ctx.guild.id
        self._ensure_queue(guild_id)
        self.guild_queues[guild_id].append(query)
        await ctx.send(f"✅ Enqueued: {query}")
        # If nothing is playing, start the process which will download first then connect and play
        voice = ctx.guild.voice_client or discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if not voice or (not voice.is_playing() and not voice.is_paused()):
            # schedule _play_next as a background task to avoid blocking the command
            self.bot.loop.create_task(self._play_next(ctx))

    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context):
        """Stop playback and clear queue."""
        voice = ctx.voice_client
        if not voice:
            await ctx.send("❌ Not connected to a voice channel.")
            return
        if voice.is_playing():
            voice.stop()
        guild_id = ctx.guild.id
        self.guild_queues.pop(guild_id, None)
        if guild_id in self.current_files:
            try:
                source = self.current_files.pop(guild_id)
                if hasattr(source, 'cleanup'):
                    await source.cleanup()
            except Exception:
                pass
        await ctx.send("⏹️ Stopped and cleared the queue.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
