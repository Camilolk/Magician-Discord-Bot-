"""Compare Telethon PDF transfer methods without changing Magician's delivery.

Usage: python benchmark_telegram_pdf.py 26153
Only tests documents in the explicitly authorized channel/index.
Downloads into a temporary directory and removes both test files.
Do not run concurrently with the Discord bot using the same session.
"""
import argparse
import asyncio
import os
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

from authorized_delivery import DeliveryError, _channel_entry, MAX_BYTES


async def run(chat_id, message_id):
    entry = _channel_entry(chat_id, message_id)
    load_dotenv()
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session = os.getenv("TELEGRAM_SESSION_PATH", "magician_telegram")
    async with TelegramClient(session, api_id, api_hash) as client:
        entity = await client.get_entity(chat_id)
        message = await client.get_messages(entity, ids=message_id)
        if not message or not message.document:
            raise DeliveryError("No se encontró el PDF en Telegram")
        document = message.document
        actual_name = message.file.name
        if actual_name != entry["filename"] or document.mime_type != "application/pdf":
            raise DeliveryError("El documento no coincide con el índice autorizado")
        if not 0 < document.size <= MAX_BYTES:
            raise DeliveryError("El PDF supera el límite actual de entrega")
        with tempfile.TemporaryDirectory(prefix="magician_benchmark_") as temp:
            first = Path(temp) / "default.pdf"
            second = Path(temp) / "large_chunks.pdf"
            start = time.perf_counter()
            await client.download_media(message, file=str(first))
            default_seconds = time.perf_counter() - start
            if first.stat().st_size != document.size:
                raise DeliveryError("La primera descarga quedó incompleta")
            start = time.perf_counter()
            await client.download_file(document, file=str(second), part_size_kb=512)
            optimized_seconds = time.perf_counter() - start
            if second.stat().st_size != document.size:
                raise DeliveryError("La segunda descarga quedó incompleta")
            print(f"PDF: {actual_name} ({document.size / 1048576:.2f} MiB)")
            print(f"Descarga habitual: {default_seconds:.1f} s")
            print(f"Bloques de 512 KiB: {optimized_seconds:.1f} s")
            print("Archivos temporales eliminados al terminar.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("message_id", type=int)
    parser.add_argument("--channel", type=int, default=-1001485195933)
    args = parser.parse_args()
    if args.message_id <= 0:
        parser.error("El ID debe ser positivo")
    asyncio.run(run(args.channel, args.message_id))


if __name__ == "__main__":
    main()
