import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
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
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import io
import wave

async def create_audio_source(stream_url: str) -> discord.AudioSource:
    """Create an FFmpegOpusAudio source for the given stream URL."""
    # FFmpeg options optimized for low latency - use direct streaming without probe
    ffmpeg_options = {
        'options': '-vn',  # Minimal options for fastest startup
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
                         '-protocol_whitelist file,http,https,tcp,tls,crypto '
                         '-tls_verify 0 -analyzeduration 0 -probesize 32768 '
                         '-fflags +nobuffer+fastseek -flags low_delay'  # Ultra low latency
    }
    
    # Use FFmpegPCMAudio directly instead of from_probe to avoid delay
    return discord.FFmpegOpusAudio(stream_url, **ffmpeg_options)


class Music(commands.Cog):

    @commands.command(name="spotify")
    async def spotify(self, ctx: commands.Context, url: str):
        """Play all tracks from a Spotify playlist URL using YouTube search."""
        # Check for Spotify credentials in environment
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        if not client_id or not client_secret:
            await ctx.send("❌ Spotify API credentials not set. Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your .env file.")
            return

        # Validate playlist URL
        if "playlist" not in url:
            await ctx.send("❌ Please provide a valid Spotify playlist URL.")
            return

        await ctx.send("🔎 Fetching playlist tracks from Spotify...")
        try:
            sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
            playlist_id = url.split("playlist/")[-1].split("?")[0]
            results = sp.playlist_tracks(playlist_id)
            tracks = results["items"]
            # Handle pagination if >100 tracks
            while results["next"]:
                results = sp.next(results)
                tracks.extend(results["items"])
        except Exception as e:
            await ctx.send(f"❌ Failed to fetch playlist: {e}")
            return

        if not tracks:
            await ctx.send("❌ No tracks found in the playlist.")
            return

        guild_id = ctx.guild.id
        self._ensure_queue(guild_id)
        count = 0
        for item in tracks:
            track = item.get("track")
            if not track:
                continue
            name = track.get("name")
            artists = ", ".join([a["name"] for a in track.get("artists", [])])
            search_query = f"{name} {artists}"
            self.guild_queues[guild_id].append(search_query)
            count += 1

        await ctx.send(f"✅ Enqueued {count} tracks from the playlist! Starting playback...")
        # If nothing is playing, start playback
        voice = ctx.guild.voice_client or discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if not voice or (not voice.is_playing() and not voice.is_paused()):
            self.bot.loop.create_task(self._play_next(ctx))
    """Simple music cog using pytube to download audio and ffmpeg to play."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_queues: dict[int, Deque[str]] = {}
        self.current_files: dict[int, str] = {}
        self.play_locks: dict[int, asyncio.Lock] = {}
        self.loop_tracks: dict[int, str] = {}  # Store looped tracks by guild ID
        self.current_playing: dict[int, str] = {}  # Store currently playing track URL/query
        self.log = logging.getLogger("mitray.music")
        
        # Configure SSL context with certifi certificates
        try:
            self.ssl_context = ssl.create_default_context(cafile=certifi.where())
            urllib3.disable_warnings()
        except Exception as e:
            self.log.warning(f"Failed to configure SSL context: {e}")
            self.ssl_context = None

        # Try to load opus
        if not self._load_opus():
            self.log.warning("Opus is NOT loaded; voice audio will be silent until libopus is available")

    def _load_opus(self) -> bool:
        """Try to load opus library from various possible locations."""
        try:
            if discord.opus.is_loaded():
                return True
        except Exception:
            pass

        try:
            # Try common opus DLL names
            opus_names = [
                'libopus-0.dll',
                'opus.dll',
                str(Path.cwd() / 'libopus-0.dll'),
                str(Path.cwd() / 'opus.dll'),
                str(Path(__file__).parent.parent / 'libopus-0.dll'),
                str(Path(__file__).parent.parent / 'opus.dll'),
            ]
            
            for name in opus_names:
                try:
                    discord.opus.load_opus(name)
                    self.log.info(f"Successfully loaded Opus from: {name}")
                    return True
                except Exception:
                    continue

            return False
        except Exception as e:
            self.log.error(f"Failed to load Opus: {e}")
            return False

    def _ensure_queue(self, guild_id: int):
        if guild_id not in self.guild_queues:
            self.guild_queues[guild_id] = deque()
            self.play_locks[guild_id] = asyncio.Lock()

    async def _search_youtube(self, query: str) -> tuple[str, str]:
        """Search YouTube and return the best matching video URL and title."""
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'default_search': 'ytsearch1',  # Only get 1 result (was default which gets 5)
            'extract_flat': 'in_playlist',  # Faster extraction
            'socket_timeout': 10,  # Reduced timeout
        }

        def _search():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    result = ydl.extract_info(f"ytsearch1:{query}", download=False)
                    if not result or not result.get('entries'):
                        raise RuntimeError("No results found")
                    video = result['entries'][0]
                    return f"https://www.youtube.com/watch?v={video['id']}", video.get('title', 'Unknown title')
                except Exception as e:
                    self.log.error(f"Search failed: {e}")
                    raise

        loop = asyncio.get_event_loop()
        url, title = await loop.run_in_executor(None, _search)
        return url, title

    async def _download_audio(self, url: str) -> tuple[str, dict]:
        """Return a direct audio stream URL and basic info (uses yt-dlp extract_info without downloading)."""
        self.log.info("Extracting stream URL for %s", url)

        ydl_opts = {
            'format': 'ba[ext=webm]/ba[ext=m4a]/ba',  # Best audio, prefer webm/m4a for speed
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'no_check_certificate': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            },
            'socket_timeout': 8,  # Reduced timeout
            'retries': 1,  # Minimal retries for speed
            'age_limit': None,
            'extractor_retries': 1,
        }
        
        # Add SSL context if available
        if hasattr(self, 'ssl_context') and self.ssl_context:
            ydl_opts['ssl_context'] = self.ssl_context

        def _extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    raise RuntimeError('yt-dlp returned no info')
                
                stream_url = info.get('url')
                if not stream_url:
                    # Fallback to formats
                    formats = info.get('formats') or []
                    if formats:
                        stream_url = formats[-1].get('url')
                    if not stream_url:
                        raise RuntimeError('No playable stream URL found')
                
                # Return URL and minimal info for display
                return stream_url, {
                    'title': info.get('title', 'Unknown'),
                    'thumbnail': info.get('thumbnail'),
                    'duration': info.get('duration')
                }

        loop = asyncio.get_event_loop()
        stream_url, info = await loop.run_in_executor(None, _extract)
        self.log.info("Extracted stream URL successfully")
        return stream_url, info

    async def _play_next(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        self._ensure_queue(guild_id)
        async with self.play_locks[guild_id]:
            # if nothing in queue, nothing to do
            if not self.guild_queues[guild_id]:
                return

            query = self.guild_queues[guild_id].popleft()
            # Store the current playing track
            self.current_playing[guild_id] = query
            
            # Get voice channel info
            channel = None
            if ctx.author and getattr(ctx.author, 'voice', None):
                channel = ctx.author.voice.channel
            
            if channel is None:
                await ctx.send("❌ Can't join voice channel: author is not in a voice channel.")
                return
            
            # STEP 1: START AUDIO EXTRACTION AND VOICE JOIN IN PARALLEL
            async def prepare_audio():
                """Prepare audio stream URL in parallel"""
                try:
                    # If it's not a URL, search for it
                    if not (query.startswith("http://") or query.startswith("https://")):
                        url, title = await self._search_youtube(query)
                        video_info = {'title': title}
                    else:
                        url = query
                        video_info = None
                    
                    # Get the direct audio URL from YouTube
                    stream_url, info = await self._download_audio(url)
                    if not video_info:
                        video_info = info
                    
                    return url, stream_url, video_info
                except Exception as e:
                    raise RuntimeError(f"Failed to prepare audio: {e}")
            
            async def join_voice():
                """Join voice channel in parallel"""
                try:
                    voice = ctx.guild.voice_client or discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
                    if not voice or not voice.is_connected():
                        self.log.info("Connecting to voice channel %s", channel.name)
                        voice = await channel.connect()
                        # Minimal wait for connection
                        await asyncio.sleep(0.3)
                        self.log.info("Connected to voice channel %s", channel.name)
                    return voice
                except Exception as e:
                    raise RuntimeError(f"Failed to connect to voice: {e}")
            
            # Run both tasks in parallel - this is the key optimization!
            try:
                (url, stream_url, video_info), voice = await asyncio.gather(
                    prepare_audio(),
                    join_voice()
                )
                
                # Create FFmpeg Opus audio source (fast, no probe)
                source = await create_audio_source(stream_url)
                self.log.info("Created audio source for %s", url)
                
            except Exception as e:
                self.log.exception("Failed to prepare audio for %s", url)
                await ctx.send(f"❌ Failed to prepare audio: {e}")
                # try next track if available
                self.bot.loop.create_task(self._play_next(ctx))
                return

            # Store source for cleanup
            self.current_files[guild_id] = source

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
                        # If this guild has a looped track, play it again
                        if guild_id in self.loop_tracks:
                            self.guild_queues[guild_id].appendleft(self.loop_tracks[guild_id])
                        # play next track if any
                        await self._play_next(ctx)

                coro = _cleanup_and_next()
                fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
                try:
                    fut.result()
                except Exception:
                    pass

            # STEP 3: Start playback immediately (no retry loop needed)
            try:
                voice = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
                if not voice or not voice.is_connected():
                    raise RuntimeError("Voice client disconnected before playback")
                
                voice.play(source, after=_after)
                self.log.info("Started playback for %s in guild %s", url, guild_id)
                
                # STEP 4: Send notification immediately using cached info
                async def _send_now_playing():
                    try:
                        # Create an embed with thumbnail using already-fetched info
                        embed = discord.Embed(
                            title="🎵 Now Playing",
                            description=f"[{video_info.get('title', 'Unknown Track')}]({url})",
                            color=0x1DB954
                        )
                        
                        if video_info.get('thumbnail'):
                            embed.set_thumbnail(url=video_info['thumbnail'])
                        
                        if video_info.get('duration'):
                            minutes, seconds = divmod(video_info['duration'], 60)
                            embed.add_field(name="Duration", value=f"{minutes}:{seconds:02d}")
                        
                        await ctx.send(embed=embed, view=MusicControls(self, ctx))
                    except Exception:
                        # Fallback if embed fails
                        await ctx.send(f"🎶 Now playing: <{url}>", view=MusicControls(self, ctx))
                
                # Run notification in background
                self.bot.loop.create_task(_send_now_playing())
                
            except Exception as e:
                self.log.exception("Failed to start playback for %s: %s", url, e)
                await ctx.send(f"❌ Failed to play audio: {e}")
                # cleanup
                try:
                    if guild_id in self.current_files:
                        source = self.current_files.pop(guild_id)
                        if hasattr(source, 'cleanup'):
                            await source.cleanup()
                except Exception:
                    pass

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
        self.current_playing.pop(guild_id, None)  # Clear currently playing track
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
        """Play music from YouTube. You can use a URL or search terms."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ You are not in a voice channel.")
            return

        # If it's not a URL, treat it as a search query
        if not (query.startswith("http://") or query.startswith("https://")):
            try:
                search_msg = await ctx.send(f"🔍 Searching YouTube for: `{query}`")
                url, title = await self._search_youtube(query)
                await search_msg.edit(content=f"✅ Found: `{title}`")
            except Exception as e:
                await ctx.send(f"❌ Search failed: {e}")
                return
        else:
            url = query

        guild_id = ctx.guild.id
        self._ensure_queue(guild_id)
        self.guild_queues[guild_id].append(query)
        await ctx.send(f"✅ Enqueued: {query}")
        # If nothing is playing, start the process which will download first then connect and play
        voice = ctx.guild.voice_client or discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if not voice or (not voice.is_playing() and not voice.is_paused()):
            # schedule _play_next as a background task to avoid blocking the command
            self.bot.loop.create_task(self._play_next(ctx))

    @commands.command(name="loop")
    async def loop(self, ctx: commands.Context, *, query: str = None):
        """Loop the current track or play and loop a new track.
        Use without arguments to loop the current track, or with a query/URL to play and loop a new track."""
        guild_id = ctx.guild.id

        if not query:
            # If no query provided, try to loop the currently playing track
            voice = ctx.voice_client
            if voice and voice.is_playing() and guild_id in self.current_playing:
                current_track = self.current_playing[guild_id]
                self.loop_tracks[guild_id] = current_track
                await ctx.send("🔁 Now looping the current track!")
            else:
                await ctx.send("❌ Nothing is currently playing!")
            return

        # Stop any existing playback and clear queue
        voice = ctx.voice_client
        if voice and voice.is_playing():
            voice.stop()
        
        # Clear the queue and add new track
        self._ensure_queue(guild_id)
        self.guild_queues[guild_id].clear()
        
        # If it's not a URL, treat it as a search query
        if not (query.startswith("http://") or query.startswith("https://")):
            try:
                search_msg = await ctx.send(f"🔍 Searching YouTube for: `{query}`")
                url, title = await self._search_youtube(query)
                await search_msg.edit(content=f"✅ Found: `{title}`")
            except Exception as e:
                await ctx.send(f"❌ Search failed: {e}")
                return
        else:
            url = query

        # Store the track for looping and add it to queue
        self.loop_tracks[guild_id] = url
        self.guild_queues[guild_id].append(url)
        await ctx.send(f"🔁 Now playing and looping: {url}")
        
        # Start playback if not already playing
        if not voice or not voice.is_playing():
            self.bot.loop.create_task(self._play_next(ctx))

    @commands.command(name="unloop")
    async def unloop(self, ctx: commands.Context):
        """Stop looping the current track."""
        guild_id = ctx.guild.id
        if guild_id in self.loop_tracks:
            del self.loop_tracks[guild_id]
            await ctx.send("✅ Stopped looping!")
        else:
            await ctx.send("❌ No track is currently looping!")

    @commands.command(name="next")
    async def next(self, ctx: commands.Context):
        """Skip to the next track in the queue."""
        voice = ctx.voice_client
        if not voice:
            await ctx.send("❌ Not connected to a voice channel.")
            return
        
        guild_id = ctx.guild.id
        if not self.guild_queues.get(guild_id):
            await ctx.send("❌ No more tracks in the queue.")
            return

        if voice.is_playing():
            voice.stop()  # This will trigger the _after callback which will play the next song
            await ctx.send("⏭️ Skipping to next track...")
        else:
            await ctx.send("❌ Nothing is currently playing!")

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
        # Clear queue and loop status
        self.guild_queues.pop(guild_id, None)
        self.loop_tracks.pop(guild_id, None)  # Stop looping when stopping playback
        self.current_playing.pop(guild_id, None)  # Clear currently playing track
        if guild_id in self.current_files:
            try:
                source = self.current_files.pop(guild_id)
                if hasattr(source, 'cleanup'):
                    await source.cleanup()
            except Exception:
                pass
        await ctx.send("⏹️ Stopped and cleared the queue.")

class MusicControls(discord.ui.View):
    def __init__(self, music_cog, ctx):
        super().__init__(timeout=None)
        self.music_cog = music_cog
        self.ctx = ctx

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.success, row=0)
    async def play_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice = interaction.guild.voice_client
        if voice and voice.is_playing():
            voice.pause()
            await interaction.response.send_message("⏸️ Paused!", ephemeral=True)
        elif voice and voice.is_paused():
            voice.resume()
            await interaction.response.send_message("▶️ Resumed playback!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nothing is playing right now.", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.primary, row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.next(self.ctx)
        await interaction.response.send_message("⏭️ Skipped to next track!", ephemeral=True)
    
    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, row=0)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.stop(self.ctx)
        await interaction.response.send_message("⏹️ Stopped playback and cleared the queue!", ephemeral=True)
    
    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary, row=0)
    async def loop_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        if guild_id in self.music_cog.loop_tracks:
            del self.music_cog.loop_tracks[guild_id]
            await interaction.response.send_message("✅ Stopped looping!", ephemeral=True)
        else:
            voice = interaction.guild.voice_client
            if voice and voice.is_playing() and guild_id in self.music_cog.current_playing:
                current_track = self.music_cog.current_playing[guild_id]
                self.music_cog.loop_tracks[guild_id] = current_track
                await interaction.response.send_message("🔁 Now looping the current track!", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Nothing is currently playing to loop!", ephemeral=True)
                
    @discord.ui.button(emoji="📋", style=discord.ButtonStyle.secondary, row=1)
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        queue = self.music_cog.guild_queues.get(guild_id, deque())
        
        if not queue:
            await interaction.response.send_message("📋 Queue is empty!", ephemeral=True)
            return
        
        queue_text = "\n".join([f"{i+1}. {track}" for i, track in enumerate(queue)])
        embed = discord.Embed(
            title="📋 Queue",
            description=queue_text[:4000] if len(queue_text) > 4000 else queue_text,
            color=0x1DB954
        )
        
        # Add count of tracks
        embed.set_footer(text=f"Total tracks: {len(queue)}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
