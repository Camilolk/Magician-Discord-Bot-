"""Fetch explicitly approved Telegram PDF documents into a temporary directory.

The caller owns the temporary directory and must clean it after upload.
"""
import asyncio
import os
from pathlib import Path

from telethon import TelegramClient
from dotenv import load_dotenv

from authorized_delivery import DeliveryError, MAX_BYTES

_client = None
_client_lock = asyncio.Lock()


async def _get_client(api_id, api_hash, session):
    """Reuse a connected Telegram session across sequential PDF requests."""
    global _client
    if _client is not None and _client.is_connected():
        return _client
    if _client is not None:
        await _client.disconnect()
    _client = TelegramClient(session, api_id, api_hash)
    await _client.connect()
    if not await _client.is_user_authorized():
        await _client.disconnect()
        _client = None
        raise DeliveryError("La sesión de Telegram no está autorizada. Ejecuta primero el indexador.")
    return _client


async def download_approved_telegram_pdf(entry, directory):
    chat_id = entry.get("telegram_chat_id")
    message_id = entry.get("telegram_message_id")
    filename = entry.get("filename")
    if not isinstance(chat_id, int) or not isinstance(message_id, int) or message_id <= 0:
        raise DeliveryError("Faltan los identificadores del documento de Telegram.")
    if not isinstance(filename, str) or Path(filename).name != filename or not filename.lower().endswith(".pdf"):
        raise DeliveryError("El nombre del PDF no es válido.")
    load_dotenv()
    try:
        api_id = int(os.environ["TELEGRAM_API_ID"])
        api_hash = os.environ["TELEGRAM_API_HASH"]
    except (KeyError, ValueError) as exc:
        raise DeliveryError("Configura TELEGRAM_API_ID y TELEGRAM_API_HASH en .env.") from exc

    session = os.getenv("TELEGRAM_SESSION_PATH", "magician_telegram")
    async with _client_lock:
        client = await _get_client(api_id, api_hash, session)
    try:
        message = await client.get_messages(chat_id, ids=message_id)
    except Exception as exc:
        raise DeliveryError("No pude consultar ese mensaje de Telegram con la sesión actual.") from exc
    if not message or not message.document:
        raise DeliveryError("El mensaje no contiene un documento descargable.")
    document = message.document
    mime = getattr(document, "mime_type", "")
    actual_name = next((attr.file_name for attr in document.attributes
                        if hasattr(attr, "file_name")), None)
    if mime != "application/pdf" or actual_name != filename:
        raise DeliveryError("El documento de Telegram no coincide con el PDF autorizado.")
    if not 0 < document.size <= MAX_BYTES:
        raise DeliveryError("El PDF supera el límite de 8 MB o está vacío.")
    destination = Path(directory) / filename
    try:
        result = await asyncio.wait_for(
            client.download_file(document, file=str(destination), part_size_kb=512), timeout=120
        )
    except (Exception, asyncio.TimeoutError) as exc:
        raise DeliveryError("No se pudo descargar el PDF desde Telegram.") from exc
    if not result or not destination.is_file() or not 0 < destination.stat().st_size <= MAX_BYTES:
        raise DeliveryError("La descarga del PDF no se completó correctamente.")
    return destination
