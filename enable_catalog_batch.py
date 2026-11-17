"""Preview and enable rights-cleared Telegram PDFs from the local metadata index.

Examples:
 python enable_catalog_batch.py --search "A Hint of Spring"
 python enable_catalog_batch.py --search "A Hint of Spring" --confirm-rights
 python enable_catalog_batch.py --search "Cultivation" --limit 100 --confirm-rights

Only authorize PDFs for which you have the necessary redistribution rights.
No files are downloaded.
"""
import argparse
import json
import sqlite3
from pathlib import Path

from authorized_delivery import MANIFEST
from database import DB_PATH


def main():
    parser = argparse.ArgumentParser(description="Habilitar PDF autorizados por título")
    parser.add_argument("--search", required=True, help="Parte del nombre del PDF")
    parser.add_argument("--channel", type=int, default=-1001485195933)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--confirm-rights", action="store_true")
    args = parser.parse_args()
    if not args.search.strip() or len(args.search.strip()) < 3:
        parser.error("--search debe tener al menos tres caracteres")
    if not 1 <= args.limit <= 500:
        parser.error("--limit debe estar entre 1 y 500")

    needle = "%" + args.search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute(
            """SELECT telegram_message_id, title FROM novels
               WHERE telegram_chat_id = ? AND title LIKE ? ESCAPE '\\'
               ORDER BY telegram_message_id DESC LIMIT ?""",
            (args.channel, needle, args.limit + 1),
        ).fetchall()
    truncated = len(rows) > args.limit
    rows = rows[:args.limit]
    valid = []
    for message_id, title in rows:
        filename = title + ".pdf"
        if (not isinstance(message_id, int) or not isinstance(title, str)
                or Path(filename).name != filename or not filename.lower().endswith(".pdf")):
            print(f"OMITIDO: {message_id} | {title}")
            continue
        valid.append((message_id, filename))
        print(f"{message_id}: {filename}")
    print(f"Coincidencias válidas: {len(valid)}" + (" (hay más resultados; ajusta --search)" if truncated else ""))
    if not args.confirm_rights:
        print("Vista previa: no se modificó el manifiesto. Para habilitar, añade --confirm-rights.")
        return
    if truncated:
        parser.error("La búsqueda excede el límite. Usa un término más específico para evitar habilitaciones parciales.")
    if not valid:
        parser.error("No se encontraron documentos válidos.")
    if MANIFEST.is_file():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            parser.error(f"No se pudo leer el manifiesto: {exc}")
    else:
        manifest = {"documents": {}}
    if not isinstance(manifest, dict) or not isinstance(manifest.get("documents"), dict):
        parser.error("El manifiesto no tiene un objeto 'documents' válido")
    entries = manifest["documents"]
    for message_id, filename in valid:
        key = f"telegram_{abs(args.channel)}_{message_id}"
        proposed = {
            "source": "telegram",
            "filename": filename,
            "telegram_chat_id": args.channel,
            "telegram_message_id": message_id,
            "redistribution_authorized": True,
        }
        if key in entries and entries[key] != proposed:
            parser.error(f"Conflicto con documento existente: {key}")
    for message_id, filename in valid:
        key = f"telegram_{abs(args.channel)}_{message_id}"
        entries[key] = {
            "source": "telegram",
            "filename": filename,
            "telegram_chat_id": args.channel,
            "telegram_message_id": message_id,
            "redistribution_authorized": True,
        }
    temporary = MANIFEST.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(MANIFEST)
    print(f"Habilitados: {len(valid)} documentos. No se descargó ningún PDF.")


if __name__ == "__main__":
    main()
