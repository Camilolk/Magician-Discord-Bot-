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
MAX_RESULTS = 100


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
        return records[:MAX_RESULTS]
    needle = normalize(query)
    matches = []
    for title, url in records:
        haystack = normalize(title)
        score = max(fuzz.WRatio(needle, haystack), fuzz.partial_ratio(needle, haystack))
        if needle in haystack or score >= 75:
            matches.append((score, title, url))
    matches.sort(key=lambda item: (-item[0], item[1].casefold()))
    return [(title, url) for _, title, url in matches[:MAX_RESULTS]]


class JumpModal(discord.ui.Modal, title="Ir a una página"):
    page_number = discord.ui.TextInput(
        label="Número de página", placeholder="Ejemplo: 7", max_length=5
    )

    def __init__(self, results_view):
        super().__init__()
        self.results_view = results_view

    async def on_submit(self, interaction):
        view = self.results_view
        try:
            target = int(str(self.page_number.value))
        except ValueError:
            await interaction.response.send_message("Escribe un número válido.", ephemeral=True)
            return
        if not 1 <= target <= view.total_pages:
            await interaction.response.send_message(
                f"Elige una página entre 1 y {view.total_pages}.", ephemeral=True
            )
            return
        view.page = target - 1
        view.refresh()
        await interaction.response.edit_message(embed=view.embed(), view=view)


class ResultsView(discord.ui.View):
    def __init__(self, owner_id, results, heading):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.results = results
        self.heading = heading
        self.page = 0
        self.message = None
        self.refresh()

    @property
    def total_pages(self):
        return max(1, (len(self.results) + PAGE_SIZE - 1) // PAGE_SIZE)

    def refresh(self):
        self.previous.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.total_pages - 1
        self.jump.disabled = self.total_pages == 1

    def embed(self):
        start = self.page * PAGE_SIZE
        end = min(start + PAGE_SIZE, len(self.results))
        embed = discord.Embed(
            title=self.heading,
            description="Explora el catálogo de novelas indexadas en Telegram.",
            color=discord.Color.from_rgb(150, 90, 225),
        )
        for i, (title, url) in enumerate(self.results[start:end], start + 1):
            safe = discord.utils.escape_markdown(title)
            # Avoid exposing private-channel URLs or untrusted schemes.
            detail = "📄 Documento PDF · Disponible en el catálogo"
            if url and re.fullmatch(r"https://t\\.me/[A-Za-z0-9_]+/\\d+", url):
                detail = f"🔗 [Ver publicación original]({url})"
            embed.add_field(
                name=f"📖 {i:02d} · {safe[:210]}",
                value=detail,
                inline=False,
            )
        embed.set_footer(
            text=f"Página {self.page + 1} de {self.total_pages}  •  "
                 f"{len(self.results)} resultados  •  Magician Library"
        )
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Esta búsqueda pertenece a otra persona. Usa m!buscar para crear la tuya.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Anterior", emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def previous(self, interaction, button):
        self.page = max(0, self.page - 1)
        self.refresh()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Ir a página", emoji="🔢", style=discord.ButtonStyle.secondary, row=0)
    async def jump(self, interaction, button):
        await interaction.response.send_modal(JumpModal(self))

    @discord.ui.button(label="Siguiente", emoji="▶️", style=discord.ButtonStyle.primary, row=0)
    async def next_page(self, interaction, button):
        self.page = min(self.total_pages - 1, self.page + 1)
        self.refresh()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


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
    view.message = await ctx.send(embed=view.embed(), view=view, allowed_mentions=discord.AllowedMentions.none())


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


@bot.command(name="estadisticas", aliases=["stats"])
async def estadisticas(ctx):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM novels") as cursor:
            count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(DISTINCT telegram_chat_id) FROM novels") as cursor:
            channels = (await cursor.fetchone())[0]
    embed = discord.Embed(
        title="📊 Estadísticas de Magician",
        description="Resumen del catálogo local de metadatos.",
        color=discord.Color.purple(),
    )
    embed.add_field(name="📚 Documentos indexados", value=str(count))
    embed.add_field(name="📡 Canales registrados", value=str(channels))
    embed.set_footer(text="Actualizado tras ejecutar telegram_indexer.py")
    await ctx.send(embed=embed)


@bot.command(name="ayuda")
async def ayuda(ctx):
    await ctx.send(
        "🪄 **Magician 2.0**\n"
        "`m!ping` — Estado\n"
        "`m!buscar título` — Búsqueda aproximada\n"
        "`m!recientes` — Últimas novelas\n"
        "`m!biblioteca` — Catálogo paginado\n"
        "`m!estadisticas` — Resumen del catálogo\\n"
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
