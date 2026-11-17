"""Personal library and metadata-based recommendations for Magician."""
import random
import re
import unicodedata
import aiosqlite
from database import DB_PATH
from story_catalog import load_story_groups


def norm(text):
    text = unicodedata.normalize("NFKD", str(text or "").casefold())
    return " ".join("".join(c if c.isalnum() else " " for c in text if not unicodedata.combining(c)).split())


def identity(group):
    return str(group.get("metadata_message_id") or "") + ":" + norm(group["name"])


def genres(group):
    return {norm(x) for x in re.split(r"[,;/|•]+", group.get("genres") or "") if norm(x)}


async def initialize():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS reader_library (
            user_id INTEGER NOT NULL, work_id TEXT NOT NULL,
            work_title TEXT NOT NULL, favorite INTEGER NOT NULL DEFAULT 0,
            viewed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, work_id))""")
        await db.commit()


async def save(user_id, group, favorite=None):
    key = identity(group)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""INSERT INTO reader_library(user_id,work_id,work_title,favorite)
            VALUES(?,?,?,?) ON CONFLICT(user_id,work_id) DO UPDATE SET
            work_title=excluded.work_title,
            viewed_at=CURRENT_TIMESTAMP,
            favorite=COALESCE(?,reader_library.favorite)""",
            (user_id, key, group["name"], int(bool(favorite)) if favorite is not None else 0,
             int(bool(favorite)) if favorite is not None else None))
        await db.commit()


async def entries(user_id, favorites=False):
    async with aiosqlite.connect(DB_PATH) as db:
        sql = ("SELECT work_id,work_title,favorite FROM reader_library WHERE user_id=?"
               + (" AND favorite=1" if favorites else "") + " ORDER BY viewed_at DESC LIMIT 30")
        async with db.execute(sql, (user_id,)) as cur:
            return await cur.fetchall()


def search(groups, query):
    tokens = norm(query).split()
    if not tokens:
        return groups
    def score(g):
        title, author, genre = (norm(g.get(k)) for k in ("name","author","genres"))
        fields = (title, author, genre)
        if all(any(t in field for field in fields) for t in tokens):
            return (3 if all(t in title for t in tokens) else 2 if all(t in author for t in tokens) else 1,
                    len(g["items"]))
        return None
    ranked = [(score(g),g) for g in groups]
    return [g for rating,g in sorted((x for x in ranked if x[0] is not None),
                                     key=lambda x:x[0],reverse=True)]


async def recommend(user_id, query="", limit=5):
    groups = load_story_groups()
    if not groups:
        return [], "No hay fichas de novelas. Genera story_preview.json."
    history = await entries(user_id)
    favorite_ids = {key for key,_,fav in history if fav}
    seen_ids = {key for key,_,_ in history}
    favorite_genres = set()
    for g in groups:
        if identity(g) in favorite_ids:
            favorite_genres.update(genres(g))
    query_tokens = norm(query).split()
    candidates = []
    for group in groups:
        key = identity(group)
        if key in favorite_ids:
            continue
        title = norm(group["name"])
        author = norm(group.get("author"))
        tags = norm(group.get("genres"))
        if query_tokens and not all(any(t in field for field in (title,author,tags)) for t in query_tokens):
            continue
        overlap = len(genres(group) & favorite_genres)
        score = overlap * 10 + min(len(group["items"]), 8) * .1
        if key in seen_ids:
            score -= 3
        candidates.append((score, random.random(), group))
    candidates.sort(key=lambda item:(item[0],item[1]),reverse=True)
    note = ("Basado en tus géneros favoritos y obras pendientes."
            if favorite_genres and not query else
            "Coincidencias con tu búsqueda y variedad del catálogo."
            if query else "Sugerencias variadas del catálogo; guarda favoritos para personalizarlas.")
    return [g for _,_,g in candidates[:limit]], note
