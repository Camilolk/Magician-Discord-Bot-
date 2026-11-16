"""Magician: Discord novel catalog bot."""
import asyncio
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from database import init_db, search_novels, recent_novels

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("magician")


class Magician(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned, intents=discord.Intents.default())

    async def setup_hook(self):
        await init_db()
        guild_id = os.getenv("DISCORD_GUILD_ID", "").strip()
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Synced commands to test guild %s", guild_id)
        else:
            await self.tree.sync()
            logger.info("Synced global commands (may take time to appear)")


bot = Magician()


@bot.event
async def on_ready():
    logger.info("Magician connected as %s", bot.user)


@bot.tree.command(name="ping", description="Comprueba que Magician está activo")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🪄 ¡Magician está activo! Latencia: {round(bot.latency * 1000)} ms")


@bot.tree.command(name="buscar", description="Busca una novela en el catálogo")
@app_commands.describe(titulo="Título o parte del título de la novela")
async def buscar(interaction: discord.Interaction, titulo: str):
    await interaction.response.defer()
    novels = await search_novels(titulo)
    if not novels:
        await interaction.followup.send("📚 No encontré coincidencias. El catálogo todavía puede estar vacío.")
        return
    lines = []
    for novel in novels:
        name, source_url = novel
        lines.append(f"• **{discord.utils.escape_markdown(name)}**" + (f" — {source_url}" if source_url else ""))
    await interaction.followup.send("\n".join(lines), allowed_mentions=discord.AllowedMentions.none())


@bot.tree.command(name="recientes", description="Muestra las últimas novelas registradas")
async def recientes(interaction: discord.Interaction):
    novels = await recent_novels()
    if not novels:
        await interaction.response.send_message("📚 Aún no hay novelas registradas.")
        return
    lines = [f"• **{discord.utils.escape_markdown(title)}**" for title in novels]
    await interaction.response.send_message("\n".join(lines), allowed_mentions=discord.AllowedMentions.none())


async def main():
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta DISCORD_TOKEN. Configúralo como secreto o en .env (nunca en GitHub).")
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
