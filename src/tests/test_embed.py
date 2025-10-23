from discord.ext import commands
from src.utils.embed import create_embed, EmbedColors

class ExampleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def info(self, ctx):
        embed = create_embed(
            title="Информация",
            description="Это пример эмбеда с синим цветом.",
            color=EmbedColors.INFO,
            author=ctx.author
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def error(self, ctx):
        embed = create_embed(
            title="Ошибка",
            description="Произошла ошибка!",
            color=EmbedColors.ERROR,
            author=ctx.author
        )
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(ExampleCog(bot))