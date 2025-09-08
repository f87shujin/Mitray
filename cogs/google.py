import discord
from discord.ext import commands
import os
import random
import aiohttp
import logging
from dotenv import load_dotenv
import json

class Google(commands.Cog):
    """Google search commands for images and GIFs"""
    
    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger("mitray.google")
        load_dotenv()
        self.api_keys = [
            os.getenv("GOOGLE_API_KEY_1"),  # Custom_Search_JSON_API_1
            os.getenv("GOOGLE_API_KEY_2")   # Custom_Search_JSON_API_2
        ]
        self.current_key_index = 0
        self.search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
        
        # Check if keys and search engine ID are configured
        if not self.api_keys[0] or not self.api_keys[1]:
            self.log.warning("Google API keys not set. Set GOOGLE_API_KEY_1 and GOOGLE_API_KEY_2 in .env")
        if not self.search_engine_id:
            self.log.warning("Google Search Engine ID not set. Set GOOGLE_SEARCH_ENGINE_ID in .env")

    async def fetch_image(self, query, search_type="image"):
        """Fetch an image or GIF from Google using CSE API"""
        # Build the search URL
        api_key = self.api_keys[self.current_key_index]
        search_url = "https://www.googleapis.com/customsearch/v1"
        
        # Set up search parameters
        params = {
            'q': query,
            'cx': self.search_engine_id,
            'key': api_key,
            'searchType': 'image',
            'num': 1,  # Request just 1 image to save quota
            'start': random.randint(1, 10),  # Random starting point to get different results each time
        }
        
        # Add specific parameters for GIFs if needed
        if search_type == "gif":
            params['fileType'] = 'gif'
            params['hq'] = 'animated'
            params['tbs'] = 'itp:animated'
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, params=params) as response:
                    data = await response.json()
                    
                    # Check for quota exceeded error
                    if response.status == 403 or 'error' in data and data['error'].get('code') == 403:
                        self.log.warning("Google API quota exceeded on key %s, trying next key", self.current_key_index)
                        # Try the second key
                        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
                        return await self.fetch_image(query, search_type)  # Retry with new key
                    
                    if response.status != 200:
                        error_msg = data.get('error', {}).get('message', f"API returned status {response.status}")
                        self.log.error("Google search error: %s", error_msg)
                        return None, error_msg
                    
                    # Check if we have search results
                    if 'items' not in data or not data['items']:
                        return None, "No images found"
                    
                    # Get the single result
                    result = data['items'][0]
                    image_url = result.get('link')
                    title = result.get('title', 'Image')
                    
                    return {"url": image_url, "title": title, "source": result.get('image', {}).get('contextLink')}, None
        
        except Exception as e:
            self.log.exception("Error fetching image: %s", e)
            return None, f"Error: {str(e)}"

    @commands.command(name="img")
    async def image_search(self, ctx, *, query: str):
        """Search for an image on Google
        
        Example: mit img cute cat"""
        await ctx.typing()
        
        if not self.search_engine_id or not any(self.api_keys):
            await ctx.send("❌ Google Search is not configured. Please set GOOGLE_API_KEY_1, GOOGLE_API_KEY_2, and GOOGLE_SEARCH_ENGINE_ID in .env file.")
            return
        
        async with ctx.typing():
            image, error = await self.fetch_image(query, "image")
            
        if error:
            await ctx.send(f"❌ Search error: {error}")
            return
        
        if not image:
            await ctx.send("❌ No images found.")
            return
        
        # Create an embed with the image
        embed = discord.Embed(
            title=f"🔍 Image Search: {query}",
            color=0x4285F4  # Google blue
        )
        embed.set_image(url=image["url"])
        embed.set_footer(text=f"Image Title: {image['title']}")
        
        # Add source if available
        if image.get("source"):
            embed.description = f"[Source]({image['source']})"
        
        await ctx.send(embed=embed)

    @commands.command(name="gif")
    async def gif_search(self, ctx, *, query: str):
        """Search for a GIF on Google
        
        Example: mit gif cat dancing"""
        await ctx.typing()
        
        if not self.search_engine_id or not any(self.api_keys):
            await ctx.send("❌ Google Search is not configured. Please set GOOGLE_API_KEY_1, GOOGLE_API_KEY_2, and GOOGLE_SEARCH_ENGINE_ID in .env file.")
            return
        
        async with ctx.typing():
            gif, error = await self.fetch_image(query, "gif")
            
        if error:
            await ctx.send(f"❌ Search error: {error}")
            return
        
        if not gif:
            await ctx.send("❌ No GIFs found.")
            return
        
        # Create an embed with the GIF
        embed = discord.Embed(
            title=f"🎬 GIF Search: {query}",
            color=0x34A853  # Google green
        )
        embed.set_image(url=gif["url"])
        embed.set_footer(text=f"GIF Title: {gif['title']}")
        
        # Add source if available
        if gif.get("source"):
            embed.description = f"[Source]({gif['source']})"
        
        await ctx.send(embed=embed)

async def setup(bot):
    """Async setup function for Google cog"""
    await bot.add_cog(Google(bot))
