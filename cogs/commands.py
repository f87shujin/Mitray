import discord
from discord.ext import commands
import aiohttp
import json


class BotCommands(commands.Cog):
    """Main commands for the Mitray Discord bot"""
    
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Simple ping command to test if the bot is responsive"""
        await ctx.send("Pong!")

    @commands.command(name="r34")
    async def fetch_img(self, ctx: commands.Context, *args):
        """Fetch images from Gelbooru based on tags and number of results.
        Usage: mit r34 tag1 tag2 ... n
        Example: mit r34 cat 5 (gets 5 cat images)"""
        
        # Check if user provided arguments
        if len(args) < 2:
            await ctx.send("❌ **Usage:** `mit r34 tag1 tag2 ... n`\n**Example:** `mit r34 cat 5` (gets 5 cat images)")
            return

        # Extract tags and number of results from user input
        *tags, num_results = args
        
        try:
            num_results = int(num_results)
            if num_results < 1 or num_results > 100:
                await ctx.send("❌ **Error:** Number of results must be between 1 and 100.")
                return
        except ValueError:
            await ctx.send("❌ **Error:** Please provide a valid number of results (1-100).")
            return

        # Construct the API URL
        tags_query = '+'.join(tags)
        api_url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&tags={tags_query}&limit={num_results}&json=1"

        # Send initial message
        loading_msg = await ctx.send(f"🔍 **Searching for:** `{' '.join(tags)}` | **Results:** {num_results}")

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

            # Update loading message with results
            posts = data['post']
            await loading_msg.edit(content=f"✅ **Found {len(posts)} results** for tags: `{' '.join(tags)}`")

            # Send the image URLs to the Discord channel
            for i, post in enumerate(posts, 1):
                image_url = post.get('file_url')
                if image_url:
                    # Create an embed for better presentation
                    embed = discord.Embed(
                        title=f"Result {i}/{len(posts)}",
                        description=f"Tags: `{' '.join(tags)}`",
                        color=0x00ff00
                    )
                    embed.set_image(url=image_url)
                    embed.set_footer(text=f"Source: Gelbooru | Post ID: {post.get('id', 'N/A')}")
                    
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
    """Setup function to add the cog to the bot"""
    await bot.add_cog(BotCommands(bot))
