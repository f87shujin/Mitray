import discord
from discord.ext import commands
import aiohttp
import json
import os
from dotenv import load_dotenv
import random



class BotCommands(commands.Cog):
    """Main commands for the Mitray Discord bot"""
    
    def __init__(self, bot):
        self.bot = bot
        # Load environment variables for API keys
        load_dotenv()

    
    @commands.command(name="clean")
    @commands.has_permissions(manage_messages=True)
    async def clean(self, ctx: commands.Context, n: int):
        """Delete the previous n messages in this channel (usage: mit clean n), with GIF effect."""
        if n < 1:
            await ctx.send("Please specify a positive number of messages to delete.")
            return
        # Send the GIF as an embed
        gif_url = "https://cdn.discordapp.com/attachments/1295012071494127627/1409400308131561553/The_Hand_JoJo_erasing_space.webp?ex=68ad3dd2&is=68abec52&hm=57be99671520f13526ffe2d94dd1c1b20952fe8fb58bc8d83fa7c009462b36e8&"
        embed = discord.Embed()
        embed.set_image(url=gif_url)
        gif_msg = await ctx.send(embed=embed)
        # Wait 1.3 seconds
        import asyncio
        await asyncio.sleep(1.3)
        # Delete messages (including the command itself)
        deleted = await ctx.channel.purge(limit=n+1)
       

    @commands.command(name="hello")
    async def hello(self, ctx: commands.Context):
        """Responds with a greeting when just 'mit hello' is typed"""
        await ctx.send("Hello! 👋")

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Simple ping command to test if the bot is responsive"""
        await ctx.send("Pong!")

    @commands.command(name="r34")
    async def fetch_img(self, ctx: commands.Context, *args):
        """Fetch random images from Gelbooru based on tags and number of results.
        Usage: mit r34 tag1 tag2 ... [n]
        Example: mit r34 cat 5 (gets 5 random cat images)
        If no number is provided, defaults to 1 image.
        
        Note: You need to set GELBOORU_API_KEY and GELBOORU_USER_ID in your .env file"""
        
        # Check if user provided arguments
        if len(args) < 1:
            await ctx.send("❌ **Usage:** `mit r34 tag1 tag2 ... [n]`\n**Example:** `mit r34 cat 5` (gets 5 random cat images)")
            return

        # Check if last argument is a number
        if args[-1].isdigit():
            # Extract tags and number of results from user input
            *tags, num_results_str = args
            try:
                num_results = int(num_results_str)
                if num_results < 1 or num_results > 100:
                    await ctx.send("❌ **Error:** Number of results must be between 1 and 100.")
                    return
            except ValueError:
                await ctx.send("❌ **Error:** Please provide a valid number of results (1-100).")
                return
        else:
            # If last argument is not a number, use all args as tags and default to 1 result
            tags = args
            num_results = 1

        # Get API credentials from environment variables
        api_key = os.getenv("GELBOORU_API_KEY")
        user_id = os.getenv("GELBOORU_USER_ID")
        
        if not api_key or not user_id:
            await ctx.send("❌ **Error:** Gelbooru API credentials not configured. Please set GELBOORU_API_KEY and GELBOORU_USER_ID in your .env file.")
            return

        # Construct the API URL with authentication and random sorting
        # Fetch more results than requested to ensure better randomization
        fetch_limit = min(100, max(50, num_results * 3))  # Fetch at least 50, or 3x requested amount
        tags_query = '+'.join(tags) + '+sort:random'
        api_url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&tags={tags_query}&limit={fetch_limit}&json=1&api_key={api_key}&user_id={user_id}"

        # Send initial message
        loading_msg = await ctx.send(f"🎲 **Searching for random:** `{' '.join(tags)}` | **Results:** {num_results}")

        try:
            # Fetch data from Gelbooru
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    if response.status != 200:
                        await loading_msg.edit(content=f"❌ **Error:** Failed to fetch data from Gelbooru (Status: {response.status})")
                        return
                    data = await response.json()

            # Check if any posts were found
            if not data or 'post' not in data:
                await loading_msg.edit(content=f"❌ **No results found** for tags: `{' '.join(tags)}`")
                return

            # Get all fetched posts and randomly select the requested number
            all_posts = data['post']
            
            if len(all_posts) < num_results:
                # If we got fewer results than requested, use all available
                selected_posts = all_posts
                await loading_msg.edit(content=f"⚠️ **Only found {len(all_posts)} results** for tags: `{' '.join(tags)}` (requested: {num_results})")
            else:
                # Randomly select the requested number of posts
                selected_posts = random.sample(all_posts, num_results)
                # Different message if only one result
                if num_results == 1:
                    await loading_msg.edit(content=f"🎲 **Found a random result** for tags: `{' '.join(tags)}`")
                else:
                    await loading_msg.edit(content=f"🎲 **Found {len(selected_posts)} random results** for tags: `{' '.join(tags)}`")

            # Send the randomly selected images
            for i, post in enumerate(selected_posts, 1):
                image_url = post.get('file_url')
                if image_url:
                    # Create an embed for better presentation
                    embed = discord.Embed(
                        title=f"Random Result {i}/{len(selected_posts)}",
                        description=f"Tags: `{' '.join(tags)}`",
                        color=0x00ff00
                    )
                    embed.set_image(url=image_url)
                    embed.set_footer(text=f"Source: Gelbooru | Post ID: {post.get('id', 'N/A')} | 🎲 Random Selection")
                    
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(f"❌ **Error:** Could not retrieve image {i}")

        except aiohttp.ClientError as e:
            await loading_msg.edit(content=f"❌ **Network Error:** Failed to connect to Gelbooru API")
        except json.JSONDecodeError:
            await loading_msg.edit(content=f"❌ **Error:** Invalid response from Gelbooru API")
        except Exception as e:
            await loading_msg.edit(content=f"❌ **Unexpected Error:** {str(e)}")




async def setup(bot):
    """Async setup function to add the cog to the bot (awaits add_cog)."""
    await bot.add_cog(BotCommands(bot))
