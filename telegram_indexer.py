"""Index Telegram PDF metadata without downloading or redistributing files.

Run: python telegram_indexer.py --limit 100
Use --limit 0 to scan the full channel history (may take time).
Only index channels and documents you are authorized to access and catalog.
"""
import argparse
import asyncio
import os
from pathlib import Path

import aiosqlite
from dotenv import load_dotenv
from telethon import TelegramClient

from database import DB_PATH, init_db

CHANNEL_ID = -1001485195933


def message_link(chat, message_id):
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"
    # Private channel messages may not be accessible to other Discord users.
    return None


async def index_pdfs(limit: int, incremental: bool = False):
    load_dotenv()
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        raise RuntimeError("Configura TELEGRAM_API_ID y TELEGRAM_API_HASH en .env")

    await init_db()
    session = os.getenv("TELEGRAM_SESSION_PATH", "magician_telegram")
    count = 0
    scanned = 0
    newest_known = 0
    if incremental:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT COALESCE(MAX(telegram_message_id), 0) FROM novels WHERE telegram_chat_id = ?",
                (CHANNEL_ID,),
            ) as cursor:
                newest_known = (await cursor.fetchone())[0]
        print(f"Buscando mensajes posteriores a {newest_known}...")
    async with TelegramClient(session, int(api_id), api_hash) as client:
        chat = await client.get_entity(CHANNEL_ID)
        print(f"Canal: {getattr(chat, 'title', CHANNEL_ID)}")
        async with aiosqlite.connect(DB_PATH) as db:
            async for msg in client.iter_messages(chat, limit=limit or None, min_id=newest_known):
                scanned += 1
                if not msg.file:
                    continue
                name = msg.file.name or ""
                mime = msg.file.mime_type or ""
                if mime != "application/pdf" and not name.lower().endswith(".pdf"):
                    continue
                title = Path(name).stem.strip() if name else ""
                if not title:
                    title = (msg.message or "").strip().splitlines()[0][:180] if msg.message else ""
                title = title or f"Documento PDF {msg.id}"
                await db.execute(
                    """INSERT INTO novels
                       (title, source_url, telegram_chat_id, telegram_message_id)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(telegram_chat_id, telegram_message_id)
                       DO UPDATE SET title=excluded.title, source_url=excluded.source_url""",
                    (title, message_link(chat, msg.id), CHANNEL_ID, msg.id),
                )
                count += 1
                if count <= 10:
                    print(f"PDF: {title}")
            await db.commit()
    print(f"Mensajes revisados: {scanned}; PDF encontrados: {count}")
    print("Solo se guardaron metadatos. No se descargaron archivos.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Indexa metadatos de PDF de Telegram")
    parser.add_argument("--limit", type=int, default=100, help="Mensajes a revisar; 0 = todos")
    parser.add_argument("--incremental", action="store_true", help="Revisar solo mensajes nuevos")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit debe ser >= 0")
    asyncio.run(index_pdfs(args.limit, args.incremental))
