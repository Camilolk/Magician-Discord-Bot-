"""Verify Telegram PDF message metadata without downloading documents.

Usage:
    python verify_telegram_pdfs.py 26153 26154 26155 26156 26157 26158 26159 26160
The script reads the existing Telegram session and local SQLite index.
"""
import argparse
import asyncio
import os
import sqlite3

from dotenv import load_dotenv
from telethon import TelegramClient
from database import DB_PATH

DEFAULT_CHANNEL = -1001485195933


async def verify(ids, channel_id):
    load_dotenv()
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        raise SystemExit("Faltan TELEGRAM_API_ID o TELEGRAM_API_HASH en .env")
    with sqlite3.connect(DB_PATH) as db:
        placeholders = ",".join("?" for _ in ids)
        rows = db.execute(
            f"""SELECT telegram_message_id, title FROM novels
                WHERE telegram_chat_id = ? AND telegram_message_id IN ({placeholders})""",
            [channel_id, *ids],
        ).fetchall()
    indexed = dict(rows)
    session = os.getenv("TELEGRAM_SESSION_PATH", "magician_telegram")
    async with TelegramClient(session, int(api_id), api_hash) as client:
        entity = await client.get_entity(channel_id)
        messages = await client.get_messages(entity, ids=ids)
        if not isinstance(messages, list):
            messages = [messages]
        by_id = {message.id: message for message in messages if message}
        print(f"Canal: {getattr(entity, 'title', channel_id)}")
        print("Solo se consultan metadatos. No se descargan archivos.\n")
        for message_id in ids:
            msg = by_id.get(message_id)
            if not msg:
                print(f"{message_id}: NO ENCONTRADO / SIN ACCESO")
                continue
            if not msg.file:
                print(f"{message_id}: SIN ARCHIVO")
                continue
            filename = msg.file.name or "(sin nombre)"
            mime = msg.file.mime_type or "(sin MIME)"
            size = msg.file.size or 0
            index_title = indexed.get(message_id)
            expected = index_title + ".pdf" if index_title else None
            matches = bool(expected and filename.casefold() == expected.casefold())
            status = "COINCIDE" if matches else "REVISAR NOMBRE"
            if not filename.lower().endswith(".pdf") or mime != "application/pdf":
                status = "NO ES PDF"
            print(f"{message_id}: {status} | {filename} | {size / (1024 * 1024):.2f} MiB")
            if index_title and not matches:
                print(f"    Índice: {index_title}")
            if not index_title:
                print("    No figura en el índice local")


def main():
    parser = argparse.ArgumentParser(description="Verifica metadatos de PDF en Telegram sin descargarlos")
    parser.add_argument("message_ids", type=int, nargs="+")
    parser.add_argument("--channel", type=int, default=DEFAULT_CHANNEL)
    args = parser.parse_args()
    if any(message_id <= 0 for message_id in args.message_ids):
        parser.error("Los identificadores deben ser positivos")
    asyncio.run(verify(args.message_ids, args.channel))


if __name__ == "__main__":
    main()
