"""Magician: Discord novel catalog bot."""
import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from database import init_db, search_novels, recent_novels

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("magician")

PREFIX = "m!"


class Magician(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned_or(PREFIX), intents=intents)

    async def setup_hook(self):
        await init_db()


bot = Magician()


@bot.event
async def on_ready():
    logger.info("Magician connected as %s", bot.user)


@bot.command(name="ping")
async def ping(ctx: commands.Context):
    """Comprueba que Magician está activo."""
    await ctx.send(f"🪄 ¡Magician está activo! Latencia: {round(bot.latency * 1000)} ms")


@bot.command(name="buscar")
async def buscar(ctx: commands.Context, *, titulo: str = ""):
    """Busca novelas por título."""
    if not titulo.strip():
        await ctx.send("Uso: `m!buscar nombre de la novela`")
        return
    novels = await search_novels(titulo)
    if not novels:
        await ctx.send("📚 No encontré coincidencias. El catálogo todavía puede estar vacío.")
        return
    lines = []
    for name, source_url in novels:
        line = f"• **{discord.utils.escape_markdown(name)}**"
        if source_url:
            line += f" — {source_url}"
        lines.append(line)
    await ctx.send("\n".join(lines)[:1900], allowed_mentions=discord.AllowedMentions.none())


@bot.command(name="recientes")
async def recientes(ctx: commands.Context):
    """Muestra las últimas novelas registradas."""
    novels = await recent_novels()
    if not novels:
        await ctx.send("📚 Aún no hay novelas registradas.")
        return
    await ctx.send("\n".join(f"• **{discord.utils.escape_markdown(title)}**" for title in novels)[:1900])


@bot.command(name="biblioteca")
async def biblioteca(ctx: commands.Context):
    """Muestra el catálogo reciente."""
    await recientes(ctx)


@bot.command(name="ayuda")
async def ayuda(ctx: commands.Context):
    await ctx.send("🪄 **Magician**\n`m!ping` — Estado\n`m!buscar título` — Buscar novela\n`m!recientes` — Últimas novelas\n`m!biblioteca` — Biblioteca\n`m!ayuda` — Esta ayuda")


async def main():
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta DISCORD_TOKEN. Configúralo como secreto o en .env.")
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
