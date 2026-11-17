"""Enable a specifically authorized batch of indexed Telegram PDFs.

Does not download files. Only use for PDFs whose rights holder permits
redistribution. Example:
 python enable_telegram_batch.py --channel -1001485195933 --start 26153 --end 26160 --confirm-rights
"""
import argparse
import json
import sqlite3
from pathlib import Path

from authorized_delivery import MANIFEST, MAX_BYTES
from database import DB_PATH


def main():
    parser = argparse.ArgumentParser(description="Habilitar lote autorizado de PDF indexados")
    parser.add_argument("--channel", type=int, required=True)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--confirm-rights", action="store_true",
                        help="Confirmo que tengo permiso para redistribuir estos PDF")
    args = parser.parse_args()
    if not args.confirm_rights:
        parser.error("Se requiere --confirm-rights para habilitar la redistribución")
    if args.start <= 0 or args.end < args.start or args.end - args.start >= 100:
        parser.error("El lote debe contener entre 1 y 100 IDs consecutivos positivos")
    ids = list(range(args.start, args.end + 1))
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute(
            """SELECT telegram_message_id, title FROM novels
               WHERE telegram_chat_id = ? AND telegram_message_id BETWEEN ? AND ?""",
            (args.channel, args.start, args.end),
        ).fetchall()
    indexed = dict(rows)
    if len(indexed) != len(ids):
        missing = sorted(set(ids) - set(indexed))
        parser.error(f"Faltan IDs en el índice local: {missing}")
    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            parser.error(f"Manifiesto inválido: {exc}")
    else:
        manifest = {"documents": {}}
    if not isinstance(manifest, dict) or not isinstance(manifest.get("documents"), dict):
        parser.error("El manifiesto debe contener un objeto 'documents'")
    entries = manifest["documents"]
    for message_id in ids:
        filename = indexed[message_id] + ".pdf"
        if Path(filename).name != filename or not filename.lower().endswith(".pdf"):
            parser.error(f"Nombre inválido para mensaje {message_id}")
        key = f"telegram_{abs(args.channel)}_{message_id}"
        existing = entries.get(key)
        if existing and (existing.get("filename") != filename or
                         existing.get("telegram_message_id") != message_id or
                         existing.get("telegram_chat_id") != args.channel):
            parser.error(f"Conflicto con entrada existente: {key}")
        entries[key] = {
            "source": "telegram",
            "filename": filename,
            "telegram_chat_id": args.channel,
            "telegram_message_id": message_id,
            "redistribution_authorized": True,
        }
    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(MANIFEST)
    print(f"Listo: {len(ids)} PDF habilitados en {MANIFEST.name}.")
    print("No se descargó ningún PDF. Reinicia el bot para probar el menú.")
    print(f"El límite de entrega actual es {MAX_BYTES / (1024*1024):g} MiB por archivo.")


if __name__ == "__main__":
    main()
