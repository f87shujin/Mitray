import discord
from discord.ext import commands
import random
import asyncio
import json
import os
from pathlib import Path

ydl_opts = {
    'format': '251/250/249/bestaudio/best',  # Prefer opus formats
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
    }
}

class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Store active roulette games by user ID
        self.roulette_games = {}
        # Store points for each user
        self.user_points = {}
        # Load existing points from JSON file
        self.points_file = Path(__file__).parent / "points.json"
        self._load_points()
    
    def _load_points(self):
        """Load points from the JSON file"""
        try:
            if os.path.exists(self.points_file):
                with open(self.points_file, 'r') as f:
                    data = json.load(f)
                    # Convert string keys (from JSON) to integers (user IDs)
                    self.user_points = {int(k): v for k, v in data.items()}
        except Exception as e:
            print(f"Error loading points: {e}")
            self.user_points = {}
    
    def _save_points(self):
        """Save points to the JSON file"""
        try:
            with open(self.points_file, 'w') as f:
                # Convert int keys to strings for JSON
                data = {str(k): v for k, v in self.user_points.items()}
                json.dump(data, f)
        except Exception as e:
            print(f"Error saving points: {e}")

    @commands.command(name="show")
    async def show(self, ctx: commands.Context, this: str, guy: str, the: str, meeting: str):
        """Show someone the meeting gif"""
        # Check if the command is exactly "show this guy the meeting"
        if this.lower() == "this" and guy.lower() == "guy" and the.lower() == "the" and meeting.lower() == "meeting":
            gif_url = "https://cdn.discordapp.com/attachments/1320524420384555160/1385117333634416650/Meeting.gif?ex=68a5520a&is=68a4008a&hm=597d014fc29f567a1e39bd67567dcb91bc00c9e0b505fd841003802ca4c5a6fd&"
            await ctx.send(gif_url)
        else:
            await ctx.send("❌ The command should be exactly: `mit show this guy the meeting`")
    
    @commands.command(name="rr", aliases=["rs", "roulette"])
    async def russian_roulette(self, ctx: commands.Context, pulls: int = 1):
        """Play Russian Roulette with a revolver.
        Usage: mit rr [number of pulls]
        
        Each pull has a 1 in 6 chance of firing the bullet.
        Specify how many consecutive trigger pulls to attempt (default: 1).
        Rewards: 1 pull = 5 pts, 2 = 12 pts, 3 = 20 pts, 4 = 35 pts, 5 = 50 pts
        Penalty for losing: -15 points
        """
        user_id = ctx.author.id
        
        # Validate pulls parameter
        if pulls < 1:
            await ctx.send("❌ You need to pull the trigger at least once!")
            return
        
        # Special case for 6+ pulls
        show_krabs = pulls >= 6
        if show_krabs:
            # For 6+ pulls, show the Mr. Krabs image but let them play
            embed = discord.Embed(color=0xFF5733)
            embed.set_image(url="https://media.tenor.com/R1Uq6yzOjq8AAAAe/how-do-we-tell-him-mr-krabs.png")
            await ctx.send(embed=embed)
            # Cap at 6 for gameplay
            pulls = 6
        
        # Reset any previous game for this user
        if user_id in self.roulette_games:
            del self.roulette_games[user_id]
        
        # Create a new game: randomly place the bullet in one of 6 chambers
        bullet_position = random.randint(0, 5)  # 0-5 (6 chambers)
        
        embed = discord.Embed(
            title="🔫 Russian Roulette",
            description=f"{ctx.author.mention} loads a single bullet into the revolver, spins the cylinder...",
            color=0xFF5733
        )
        embed.set_footer(text=f"Attempting {pulls} consecutive trigger pulls")
        
        message = await ctx.send(embed=embed)
        await asyncio.sleep(2)  # Dramatic pause
        
        # Start pulling the trigger
        current_position = 0
        survived = True
        
        for pull_number in range(1, pulls+1):
            # Animation for pulling trigger
            embed.description = f"{ctx.author.mention} puts the gun to their head...\n\n*click*..."
            await message.edit(embed=embed)
            await asyncio.sleep(1.5)
            
            # Check if bullet fired
            if current_position == bullet_position:
                # BANG! User lost
                embed.title = "💥 BANG!"
                embed.description = f"{ctx.author.mention} has been shot on pull #{pull_number}!"
                embed.color = 0xFF0000  # Red
                await message.edit(embed=embed)
                survived = False
                break
            
            # Survived this pull
            embed.description = f"{ctx.author.mention} pulls the trigger... *click*\n\nThe chamber was empty! ({pull_number}/{pulls})"
            await message.edit(embed=embed)
            current_position = (current_position + 1) % 6
            await asyncio.sleep(1)
        
        # Final result
        if survived:
            embed.title = "😎 Survived!"
            embed.description = f"{ctx.author.mention} survived all {pulls} pulls!\nThe bullet was in chamber #{bullet_position + 1}."
            embed.color = 0x00FF00  # Green
            await message.edit(embed=embed)
            
            # Calculate winnings based on custom reward tiers
            rewards = {1: 5, 2: 12, 3: 20, 4: 35, 5: 50, 6: -15}  # 6 pulls is actually a penalty
            winnings = rewards[pulls]
            
            # Add points to user's total
            if user_id not in self.user_points:
                self.user_points[user_id] = 0
            self.user_points[user_id] += winnings
            
            embed.add_field(name="Reward", value=f"+{winnings} points for your bravery!")
            embed.add_field(name="Total Points", value=f"{self.user_points[user_id]} points", inline=False)
            
            # Save updated points
            self._save_points()
        else:
            # User lost - check if they have points to lose
            if user_id in self.user_points and self.user_points[user_id] > 0:
                # Lose 15 points when shot, but not below zero
                points_lost = min(15, self.user_points[user_id])
                self.user_points[user_id] -= points_lost
                embed.add_field(name="Game Over", value=f"You lost {points_lost} points!")
                embed.add_field(name="Total Points", value=f"{self.user_points[user_id]} points", inline=False)
                
                # Save updated points
                self._save_points()
            else:
                # No points to lose
                if user_id not in self.user_points:
                    self.user_points[user_id] = 0
                embed.add_field(name="Game Over", value="Better luck next time!")
                embed.add_field(name="Total Points", value=f"{self.user_points[user_id]} points", inline=False)
            
        await message.edit(embed=embed)
        
    @commands.command(name="points")
    async def check_points(self, ctx: commands.Context, member: discord.Member = None):
        """Check how many points you or another user has.
        Usage: mit points [user mention]
        """
        # If no member specified, show the author's points
        target = member or ctx.author
        user_id = target.id
        
        # Get points (default to 0 if user not found)
        points = self.user_points.get(user_id, 0)
        
        embed = discord.Embed(
            title="🏆 Points Balance",
            description=f"{target.mention} has **{points} points**!",
            color=0xFFD700  # Gold
        )
        
        await ctx.send(embed=embed)
        
    @commands.command(name="leaderboard", aliases=["lb"])
    async def leaderboard(self, ctx: commands.Context):
        """Show the top 10 users with the most points.
        Usage: mit leaderboard
        """
        if not self.user_points:
            await ctx.send("No one has earned any points yet!")
            return
            
        # Sort users by points (highest first)
        sorted_users = sorted(self.user_points.items(), key=lambda x: x[1], reverse=True)
        
        # Take top 10
        top_users = sorted_users[:10]
        
        embed = discord.Embed(
            title="🏆 Points Leaderboard",
            description="Top Russian Roulette players:",
            color=0xFFD700  # Gold
        )
        
        # Add each user to the leaderboard
        for i, (user_id, points) in enumerate(top_users, 1):
            try:
                user = await self.bot.fetch_user(user_id)
                username = user.name
            except:
                username = f"User {user_id}"
                
            # Format with medals for top 3
            if i == 1:
                rank = "🥇"
            elif i == 2:
                rank = "🥈"
            elif i == 3:
                rank = "🥉"
            else:
                rank = f"{i}."
                
            embed.add_field(
                name=f"{rank} {username}",
                value=f"{points} points",
                inline=False
            )
            
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
