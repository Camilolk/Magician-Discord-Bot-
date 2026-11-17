"""Deliver locally approved PDF files through Discord.

Only files explicitly listed in authorized_pdfs.json can be sent.
No Telegram downloads or automatic redistribution are performed.
"""
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PDF_ROOT = ROOT / "authorized_pdfs"
MANIFEST = ROOT / "authorized_pdfs.json"
MAX_BYTES = max(1, int(os.getenv("MAGICIAN_MAX_PDF_MIB", "20"))) * 1024 * 1024
CHANNEL_GRANTS = ROOT / "authorized_channels.json"


class DeliveryError(Exception):
    pass


def get_authorized_pdf(key):
    if not MANIFEST.is_file():
        raise DeliveryError("Todavía no hay documentos autorizados configurados.")
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise DeliveryError("El manifiesto de documentos no es válido.") from exc
    entries = manifest.get("documents", {})
    if not isinstance(entries, dict) or not isinstance(key, str):
        raise DeliveryError("El manifiesto de documentos no es válido.")
    entry = entries.get(key)
    if not isinstance(entry, dict) or entry.get("redistribution_authorized") is not True:
        raise DeliveryError("Este documento no está habilitado para entrega.")
    name = entry.get("filename")
    if not isinstance(name, str) or Path(name).name != name or not name.lower().endswith(".pdf"):
        raise DeliveryError("Nombre de archivo no permitido.")
    root = PDF_ROOT.resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise DeliveryError("No encontré el PDF autorizado en el servidor.")
    size = path.stat().st_size
    if size == 0 or size > MAX_BYTES:
        raise DeliveryError(f"El PDF está vacío o supera el límite configurado de {MAX_BYTES // (1024 * 1024)} MiB.")
    return path


def _channel_entry(chat_id, message_id):
    from database import DB_PATH
    try:
        grants = json.loads(CHANNEL_GRANTS.read_text(encoding="utf-8")).get("channels", {})
        if grants.get(str(chat_id), {}).get("redistribution_authorized") is not True:
            raise DeliveryError("El canal no está habilitado.")
        with sqlite3.connect(DB_PATH) as db:
            row = db.execute("SELECT title FROM novels WHERE telegram_chat_id=? AND telegram_message_id=?", (chat_id, message_id)).fetchone()
    except (OSError, ValueError, AttributeError, sqlite3.Error) as exc:
        raise DeliveryError("No pude validar el documento en el canal autorizado.") from exc
    if not row:
        raise DeliveryError("Documento no indexado.")
    filename = row[0] + ".pdf"
    if Path(filename).name != filename or not filename.lower().endswith(".pdf"):
        raise DeliveryError("Nombre de archivo no válido.")
    return {"source": "telegram", "filename": filename, "telegram_chat_id": chat_id, "telegram_message_id": message_id, "redistribution_authorized": True}


def _channel_key(message_id, filename):
    from database import DB_PATH
    if not CHANNEL_GRANTS.is_file() or not isinstance(message_id, int):
        return None
    try:
        grants = json.loads(CHANNEL_GRANTS.read_text(encoding="utf-8")).get("channels", {})
        with sqlite3.connect(DB_PATH) as db:
            rows = db.execute("SELECT telegram_chat_id FROM novels WHERE telegram_message_id=? AND title=?", (message_id, Path(filename).stem)).fetchall()
        for (chat_id,) in rows:
            if grants.get(str(chat_id), {}).get("redistribution_authorized") is True:
                return f"channel:{chat_id}:{message_id}"
    except (OSError, ValueError, AttributeError, sqlite3.Error):
        pass
    return None


def authorized_keys_for_documents(documents):
    """Match approved entries to catalog PDFs by Telegram message ID when provided.

    Filename-only matching is reserved for explicitly local files.
    Telegram-backed entries require an exact message ID to avoid collisions.
    """
    if not MANIFEST.is_file():
        return []
    try:
        entries = json.loads(MANIFEST.read_text(encoding="utf-8")).get("documents", {})
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(entries, dict):
        return []
    choices = []
    seen = set()
    for message_id, filename in documents:
        for key, entry in entries.items():
            if not isinstance(key, str) or not isinstance(entry, dict):
                continue
            if entry.get("redistribution_authorized") is not True or entry.get("filename") != filename:
                continue
            if entry.get("source") == "telegram":
                if not isinstance(message_id, int) or entry.get("telegram_message_id") != message_id:
                    continue
            elif entry.get("source", "local") != "local":
                continue
            if key not in seen:
                choices.append((key, filename))
                seen.add(key)
    for message_id, filename in documents:
        key = _channel_key(message_id, filename)
        if key and key not in seen:
            choices.append((key, filename))
            seen.add(key)
    return choices


def get_authorized_entry(key):
    """Return a validated explicit permission entry for local or Telegram delivery."""
    if isinstance(key, str) and key.startswith("channel:"):
        try:
            _, chat_id, message_id = key.split(":")
            return _channel_entry(int(chat_id), int(message_id))
        except ValueError as exc:
            raise DeliveryError("Identificador de documento inválido.") from exc
    if not MANIFEST.is_file():
        raise DeliveryError("Todavía no hay documentos autorizados configurados.")
    try:
        entries = json.loads(MANIFEST.read_text(encoding="utf-8")).get("documents", {})
    except (OSError, ValueError, AttributeError) as exc:
        raise DeliveryError("El manifiesto de documentos no es válido.") from exc
    entry = entries.get(key) if isinstance(entries, dict) and isinstance(key, str) else None
    if not isinstance(entry, dict) or entry.get("redistribution_authorized") is not True:
        raise DeliveryError("Este documento no está habilitado para entrega.")
    name = entry.get("filename")
    if not isinstance(name, str) or Path(name).name != name or not name.lower().endswith(".pdf"):
        raise DeliveryError("Nombre de archivo no permitido.")
    return entry
