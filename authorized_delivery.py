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


def authorized_keys_for_filenames(filenames):
    """Return only explicit allowlist keys matching the given document names."""
    if not MANIFEST.is_file():
        return []
    try:
        entries = json.loads(MANIFEST.read_text(encoding="utf-8")).get("documents", {})
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(entries, dict):
        return []
    allowed = set(filenames)
    return [(key, entry["filename"]) for key, entry in entries.items()
            if isinstance(key, str) and isinstance(entry, dict)
            and entry.get("redistribution_authorized") is True
            and isinstance(entry.get("filename"), str)
            and entry["filename"] in allowed]
