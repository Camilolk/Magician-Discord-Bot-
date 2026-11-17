"""Magician Discord library: fuzzy search and interactive pagination."""
import asyncio
import logging
import os
import re
import unicodedata

import aiosqlite
import discord
from discord.ext import commands
from dotenv import load_dotenv
from rapidfuzz import fuzz

from database import DB_PATH, init_db

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("magician")
PREFIX = "m!"
PAGE_SIZE = 5


def normalize(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", " ", value).strip()


async def find_titles(query="", limit=5000):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT title, source_url FROM novels ORDER BY id DESC LIMIT ?", (limit,)
        ) as cursor:
            records = await cursor.fetchall()
    if not query.strip():
        return records[:100]
    needle = normalize(query)
    matches = []
    for title, url in records:
        haystack = normalize(title)
        score = max(fuzz.WRatio(needle, haystack), fuzz.partial_ratio(needle, haystack))
        if needle in haystack or score >= 75:
            matches.append((score, title, url))
    matches.sort(key=lambda item: (-item[0], item[1].casefold()))
    return [(title, url) for _, title, url in matches[:100]]


class ResultsView(discord.ui.View):
    def __init__(self, owner_id, results, heading):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.results = results
        self.heading = heading
        self.page = 0
        self.refresh()

    def refresh(self):
        self.previous.disabled = self.page == 0
        self.next_page.disabled = (self.page + 1) * PAGE_SIZE >= len(self.results)

    def embed(self):
        total_pages = (len(self.results) + PAGE_SIZE - 1) // PAGE_SIZE
        embed = discord.Embed(title=self.heading, color=discord.Color.purple())
        start = self.page * PAGE_SIZE
        lines = []
        for i, (title, url) in enumerate(self.results[start:start + PAGE_SIZE], start + 1):
            safe = discord.utils.escape_markdown(title)
            lines.append(f"**{i}.** {safe}")
            # Only show publicly accessible source links when recorded.
            if url and url.startswith("https://t.me/"):
                lines.append(f"   [Publicación original]({url})")
        embed.description = "\n".join(lines) or "Sin resultados."
        embed.set_footer(text=f"Página {self.page + 1}/{total_pages} • {len(self.results)} resultados")
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Estos botones pertenecen a otra búsqueda. Usa m!buscar para crear la tuya.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Anterior", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        self.page = max(0, self.page - 1)
        self.refresh()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Siguiente", emoji="▶️", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction, button):
        self.page = min((len(self.results) - 1) // PAGE_SIZE, self.page + 1)
        self.refresh()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def on_timeout(self):
        self.previous.disabled = True
        self.next_page.disabled = True


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
    logger.info("Magician conectado como %s", bot.user)


@bot.command(name="ping")
async def ping(ctx):
    await ctx.send(f"🪄 ¡Magician está activo! Latencia: {round(bot.latency * 1000)} ms")


async def send_results(ctx, query, heading):
    results = await find_titles(query)
    if not results:
        await ctx.send("📚 No encontré coincidencias. Prueba con parte del título.")
        return
    view = ResultsView(ctx.author.id, results, heading)
    await ctx.send(embed=view.embed(), view=view, allowed_mentions=discord.AllowedMentions.none())


@bot.command(name="buscar")
async def buscar(ctx, *, titulo=""):
    if not titulo.strip():
        await ctx.send("Uso: `m!buscar nombre de la novela`")
        return
    await send_results(ctx, titulo, f"🔎 Resultados para: {titulo[:150]}")


@bot.command(name="recientes")
async def recientes(ctx):
    await send_results(ctx, "", "📚 Novelas recientes")


@bot.command(name="biblioteca")
async def biblioteca(ctx):
    await send_results(ctx, "", "🪄 Biblioteca Magician")


@bot.command(name="ayuda")
async def ayuda(ctx):
    await ctx.send(
        "🪄 **Magician 2.0**\n"
        "`m!ping` — Estado\n"
        "`m!buscar título` — Búsqueda aproximada\n"
        "`m!recientes` — Últimas novelas\n"
        "`m!biblioteca` — Catálogo paginado\n"
        "`m!ayuda` — Comandos"
    )


async def main():
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta DISCORD_TOKEN en .env")
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
