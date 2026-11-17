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
from story_catalog import load_story_groups, document_sort_key

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("magician")
PREFIX = "m!"
PAGE_SIZE = 5
MAX_RESULTS = 500


def clean_title(value):
    value = re.sub(r"(?i)\.pdf$", "", value.strip())
    value = value.replace("_", " ")
    return re.sub(r"\s+", " ", value).strip(" -") or "Documento sin título"


def normalize(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", " ", value).strip()



def title_parts(title):
    value = clean_title(title)
    match = re.match(r"^0*(\d{1,3})\s*(?:[-.·]\s*|\s+)(.+)$", value)
    if match:
        return match.group(2).strip(), int(match.group(1))
    match = re.search(r"\s+(?:vol(?:umen|ume)?\.?|tomo)\s*0*(\d{1,3})$", value, re.I)
    if match:
        return value[:match.start()].strip(" -"), int(match.group(1))
    match = re.search(r"\s+[-–]\s*0*(\d{1,3})$", value)
    if match:
        return value[:match.start()].strip(), int(match.group(1))
    return value, None


def rank_title(query, title):
    needle = normalize(query)
    base, _ = title_parts(title)
    name = normalize(base)
    if needle == name:
        return 1000
    if name.startswith(needle):
        return 900
    if needle in name:
        return 800
    words = needle.split()
    if words and all(word in name.split() for word in words):
        return 700
    score = fuzz.ratio(needle, name)
    return score if score >= 85 else -1


async def find_titles(query="", limit=None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT title, source_url FROM novels ORDER BY id DESC") as cursor:
            records = await cursor.fetchall()
    if not query.strip():
        return records[:limit] if limit is not None else records
    matches = []
    for index, (title, url) in enumerate(records):
        score = rank_title(query, title)
        if score >= 0:
            matches.append((score, index, title, url))
    matches.sort(key=lambda item: (-item[0], item[1]))
    cap = MAX_RESULTS if limit is None else limit
    return [(title, url) for _, _, title, url in matches[:cap]]


async def find_novel_volumes(query):
    records = await find_titles("")
    needle = normalize(query)
    families = {}
    for title, url in records:
        base, volume = title_parts(title)
        key = normalize(base)
        if key and volume is not None and (needle == key or key.startswith(needle) or needle in key):
            families.setdefault(key, []).append((volume, title, url))
    if not families:
        return []
    family = max(families, key=lambda key: (key == needle, key.startswith(needle), fuzz.ratio(needle, key)))
    matches = sorted(families[family], key=lambda row: (row[0], normalize(row[1])))
    return [(title, url) for _, title, url in matches]


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
            safe = discord.utils.escape_markdown(clean_title(title))
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



def catalog_groups(records):
    """Group document metadata by normalized work name, retaining every file."""
    groups = {}
    for title, url in records:
        base, volume = title_parts(title)
        key = normalize(base)
        if not key:
            continue
        group = groups.setdefault(key, {"name": base, "items": []})
        group["items"].append((volume, title, url))
    return sorted(groups.values(), key=lambda group: normalize(group["name"]))


class CatalogSelect(discord.ui.Select):
    def __init__(self, catalog_view):
        self.catalog_view = catalog_view
        start = catalog_view.page * 10
        choices = catalog_view.groups[start:start + 10]
        options = [
            discord.SelectOption(
                label=group["name"][:100],
                value=str(start + i),
                description=f'{len(group["items"])} documento(s)'[:100],
                emoji="📖",
            )
            for i, group in enumerate(choices)
        ]
        super().__init__(placeholder="📚 Selecciona una novela", options=options, row=0)

    async def callback(self, interaction):
        group = self.catalog_view.groups[int(self.values[0])]
        view = NovelDetailView(interaction.user.id, group)
        await interaction.response.send_message(
            embed=view.embed(), view=view, ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.message = await interaction.original_response()


class NovelDetailView(discord.ui.View):
    def __init__(self, owner_id, group):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.group = group
        self.message = None

    def embed(self):
        group = self.group
        embed = discord.Embed(
            title=f'📖 {group["name"][:240]}',
            description="Ficha extraída de una publicación de Telegram. Asociación de PDF provisional.",
            color=discord.Color.from_rgb(150, 90, 225),
        )
        for label, key in (("✍️ Autor", "author"), ("🏷️ Géneros", "genres"), ("📌 Estado", "status")):
            value = group.get(key)
            if value:
                embed.add_field(name=label, value=discord.utils.escape_markdown(str(value)[:900]), inline=False)
        synopsis = group.get("synopsis")
        if synopsis:
            embed.add_field(
                name="📜 Sinopsis",
                value=discord.utils.escape_mentions(discord.utils.escape_markdown(synopsis[:1000])),
                inline=False,
            )
        else:
            embed.add_field(name="📜 Sinopsis", value="No disponible en la ficha analizada.", inline=False)
        embed.add_field(name="📄 PDF asociados", value=str(len(group["items"])), inline=True)
        embed.set_footer(text=f'Publicación de metadatos: {group.get("metadata_message_id") or "sin ID"} · Magician')
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Abre tu propio catálogo con m!catalogo.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Ver documentos", emoji="📄", style=discord.ButtonStyle.primary)
    async def documents(self, interaction, button):
        items = sorted(self.group["items"], key=lambda item: document_sort_key(item[1]))
        results = [(title, url) for _, title, url in items]
        view = ResultsView(interaction.user.id, results, f'📄 {self.group["name"][:140]} · Orden de lectura provisional')
        await interaction.response.send_message(
            embed=view.embed(), view=view, ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.message = await interaction.original_response()


class CatalogSearchModal(discord.ui.Modal, title="Buscar en el catálogo"):
    query = discord.ui.TextInput(label="Título de la novela", placeholder="Ejemplo: Majo no Tabitabi", max_length=100)

    def __init__(self, catalog_view):
        super().__init__()
        self.catalog_view = catalog_view

    async def on_submit(self, interaction):
        view = self.catalog_view
        needle = normalize(str(self.query.value))
        matches = [group for group in view.all_groups if needle in normalize(group["name"])]
        if not matches:
            await interaction.response.send_message("🔎 No encontré novelas con ese título en las fichas analizadas.", ephemeral=True)
            return
        view.groups = matches
        view.page = 0
        view.refresh()
        await interaction.response.edit_message(embed=view.embed(), view=view)


class CatalogView(discord.ui.View):
    def __init__(self, owner_id, groups):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.all_groups = groups
        self.groups = groups
        self.page = 0
        self.message = None
        self.refresh()

    @property
    def total_pages(self):
        return max(1, (len(self.groups) + 9) // 10)

    def refresh(self):
        self.previous.disabled = self.page == 0
        self.next_page.disabled = self.page == self.total_pages - 1
        self.clear_items()
        if self.groups:
            self.add_item(CatalogSelect(self))
        self.add_item(self.previous)
        self.add_item(self.next_page)
        self.add_item(self.search)
        self.add_item(self.reset_search)
        self.reset_search.disabled = self.groups is self.all_groups

    def embed(self):
        start = self.page * 10
        groups = self.groups[start:start + 10]
        lines = [
            f'**{start + i + 1:02d}.** {discord.utils.escape_markdown(group["name"][:150])} '
            f'· **{len(group["items"])}** PDF'
            for i, group in enumerate(groups)
        ]
        embed = discord.Embed(
            title="📚 Magician 3.2 · Catálogo de obras",
            description="Obras identificadas por publicaciones de Telegram. Las asociaciones de PDF son provisionales.\n\n" + "\n".join(lines),
            color=discord.Color.from_rgb(150, 90, 225),
        )
        embed.set_footer(text=f'Página {self.page + 1}/{self.total_pages} · {len(self.groups)} obras · Magician Library')
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Abre tu propio catálogo con m!catalogo.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Buscar", emoji="🔎", style=discord.ButtonStyle.success, row=2)
    async def search(self, interaction, button):
        await interaction.response.send_modal(CatalogSearchModal(self))

    @discord.ui.button(label="Mostrar todas", emoji="📚", style=discord.ButtonStyle.secondary, row=2)
    async def reset_search(self, interaction, button):
        self.groups = self.all_groups
        self.page = 0
        self.refresh()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Anterior", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def previous(self, interaction, button):
        self.page = max(0, self.page - 1)
        self.refresh()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Siguiente", emoji="▶️", style=discord.ButtonStyle.primary, row=1)
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


@bot.command(name="catalogo")
async def catalogo(ctx):
    try:
        groups = load_story_groups()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("No se pudo cargar story_preview.json: %s", exc)
        groups = []
    if not groups:
        await ctx.send("📚 No hay fichas de novelas disponibles. Genera story_preview.json con telegram_story_analyzer.py. Mientras tanto puedes usar m!buscar.")
        return
    view = CatalogView(ctx.author.id, groups)
    view.message = await ctx.send(embed=view.embed(), view=view, allowed_mentions=discord.AllowedMentions.none())


@bot.command(name="novela")
async def novela(ctx, *, titulo=""):
    if not titulo.strip():
        await ctx.send("Uso: m!novela nombre de la obra")
        return
    results = await find_novel_volumes(titulo)
    if not results:
        await ctx.send("📚 No encontré volúmenes agrupables. Prueba m!buscar.")
        return
    view = ResultsView(ctx.author.id, results, f"📖 Volúmenes: {titulo[:120]}")
    view.message = await ctx.send(embed=view.embed(), view=view, allowed_mentions=discord.AllowedMentions.none())


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
        "🪄 **Magician 3.0**\n"
        "`m!ping` — Estado\n"
        "`m!buscar título` — Búsqueda aproximada\n"
        "`m!recientes` — Últimas novelas\n"
        "`m!biblioteca` — Catálogo paginado\n"
        "`m!catalogo` — Obras agrupadas con menú\n"
        "`m!novela título` — Volúmenes de una obra\n"
        "`m!estadisticas` — Resumen del catálogo\n"
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
