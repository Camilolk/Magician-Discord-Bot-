"""Deliver locally approved PDF files through Discord.

Only files explicitly listed in authorized_pdfs.json can be sent.
No Telegram downloads or automatic redistribution are performed.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PDF_ROOT = ROOT / "authorized_pdfs"
MANIFEST = ROOT / "authorized_pdfs.json"
MAX_BYTES = 8 * 1024 * 1024


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
        raise DeliveryError("El PDF está vacío o supera el límite configurado de 8 MB.")
    return path


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
    return choices


def get_authorized_entry(key):
    """Return a validated explicit permission entry for local or Telegram delivery."""
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
