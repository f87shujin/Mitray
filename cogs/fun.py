import discord
from discord.ext import commands

class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="show")
    async def show(self, ctx: commands.Context, this: str, guy: str, the: str, meeting: str):
        """Show someone the meeting gif"""
        # Check if the command is exactly "show this guy the meeting"
        if this.lower() == "this" and guy.lower() == "guy" and the.lower() == "the" and meeting.lower() == "meeting":
            gif_url = "https://cdn.discordapp.com/attachments/1320524420384555160/1385117333634416650/Meeting.gif?ex=68a5520a&is=68a4008a&hm=597d014fc29f567a1e39bd67567dcb91bc00c9e0b505fd841003802ca4c5a6fd&"
            await ctx.send(gif_url)
        else:
            await ctx.send("❌ The command should be exactly: `mit show this guy the meeting`")

async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
