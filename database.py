"""SQLite catalog storage. Only metadata and authorized source links."""
import aiosqlite

DB_PATH = "magician.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS novels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                source_url TEXT,
                telegram_chat_id INTEGER,
                telegram_message_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(telegram_chat_id, telegram_message_id)
            )
        """)
        await db.commit()


async def search_novels(query: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT title, source_url FROM novels WHERE title LIKE ? ORDER BY title LIMIT 10",
            (f"%{query}%",),
        ) as cursor:
            return await cursor.fetchall()


async def recent_novels():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT title FROM novels ORDER BY id DESC LIMIT 10"
        ) as cursor:
            return [row[0] for row in await cursor.fetchall()]
