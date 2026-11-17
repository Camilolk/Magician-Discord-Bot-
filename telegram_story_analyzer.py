"""Preview Telegram novel-post groupings without downloading files or changing the database.

Usage: python telegram_story_analyzer.py --limit 500
       python telegram_story_analyzer.py --limit 0 --output story_preview.json
Only catalog content you are authorized to access.
"""
import argparse
import asyncio
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

CHANNEL_ID = -1001485195933
FIELD_RE = re.compile(
    r"(?im)^[^\w\r\n]{0,16}[^\S\r\n]*(t[ií]tulo|nombre|obra|autor(?:es)?|author|origen|estado|"
    r"ilustraciones|ilustrador|vol[uú]men(?:es)?|g[eé]nero(?:s)?|fansubs)[^\S\r\n]*[:：][^\S\r\n]*([^\r\n]*)$"
)

def fields_from_text(body):
    result = {}
    for match in FIELD_RE.finditer(body):
        key = match.group(1).casefold()
        value = match.group(2).strip()
        if key in ("título", "titulo", "nombre", "obra"):
            key = "title"
        elif key in ("autor", "autores", "author"):
            key = "author"
        elif key.startswith("g"):
            key = "genres"
        elif key.startswith("vol"):
            key = "volumes"
        if value:
            result[key] = value
    return result

RELATED_WORKS_RE = re.compile(
    r"(?im)^\s*otras obras del autor\s*[:：]\s*(.*)$"
)


def related_works_from_text(body):
    """Keep author references separate from the current work's title."""
    match = RELATED_WORKS_RE.search(body)
    if not match:
        return []
    lines = [match.group(1).strip()]
    # Continuation lines may wrap naturally, but stop at blank lines,
    # hashtags, metadata fields, or another heading.
    tail = body[match.end():].splitlines()
    for line in tail:
        line = line.strip()
        if not line or line.startswith("#") or FIELD_RE.match(line):
            break
        if re.match(r"(?i)^(?:otras obras|sinopsis|resumen|descarga|enlaces?)\s*:", line):
            break
        lines.append(line)
        if len(lines) >= 5:
            break
    joined = " ".join(lines).strip()
    # Preserve a single free-text reference; splitting on commas can
    # accidentally split a legitimate novel title.
    return [joined] if joined else []


RANGE_RE = re.compile(r"^\s*(\d{1,5})\s*[-–_]\s*(\d{1,5})\s*$")
GENERIC_RE = re.compile(r"^(?:\d{1,5}|vol(?:umen|ume)?\.?\s*\d+|tomo\s*\d+)$", re.I)


def is_pdf(msg):
    file = getattr(msg, "file", None)
    if not file:
        return False
    name = file.name or ""
    return (file.mime_type or "").lower() == "application/pdf" or name.lower().endswith(".pdf")


def metadata(msg):
    body = msg.message or ""
    fields = fields_from_text(body)
    if not fields.get("title"):
        # Preserve a metadata post with an explicitly empty title; do not
        # accidentally attach its PDFs to the preceding work.
        if not re.search(r"(?im)^[^\w\r\n]{0,16}[^\S\r\n]*(?:t[ií]tulo|nombre|obra)[^\S\r\n]*[:：]", body):
            return None
        fields["title"] = ""
    return {
        **fields,
        "message_id": msg.id,
        "description_excerpt": body[:500],
        "related_works": related_works_from_text(body),
        "documents": [],
        "confidence": "contextual",
    }


def pdf_info(msg):
    filename = (msg.file.name or "").strip() or f"document_{msg.id}.pdf"
    stem = Path(filename).stem
    match = RANGE_RE.fullmatch(stem)
    chapter_range = [int(match.group(1)), int(match.group(2))] if match else None
    return {
        "message_id": msg.id,
        "filename": filename,
        "chapter_range": chapter_range,
        "generic_name": bool(match or GENERIC_RE.fullmatch(stem)),
    }


async def analyze(limit, inspect=False):
    load_dotenv()
    api_id, api_hash = os.getenv("TELEGRAM_API_ID"), os.getenv("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        raise RuntimeError("Faltan TELEGRAM_API_ID y TELEGRAM_API_HASH en .env")
    session = os.getenv("TELEGRAM_SESSION_PATH", "magician_telegram")
    async with TelegramClient(session, int(api_id), api_hash) as client:
        chat = await client.get_entity(CHANNEL_ID)
        # Telegram yields newest first; reverse to reconstruct publication order.
        messages = [msg async for msg in client.iter_messages(chat, limit=limit or None)]
    messages.reverse()
    if inspect:
        print("Muestras de publicaciones sin archivos (máximo 8):")
        shown = 0
        for msg in messages:
            if not is_pdf(msg) and (msg.message or "").strip():
                snippet = (msg.message or "").strip().replace("\n", " ")[:220]
                print(f"  Mensaje {msg.id}: {snippet}")
                shown += 1
                if shown >= 8:
                    break
    works, unassigned = [], []
    active = None
    # A conservative window prevents an unrelated PDF being attached much later.
    last_context_index = None
    for index, msg in enumerate(messages):
        info = metadata(msg) if not is_pdf(msg) else None
        if info:
            works.append(info)
            active = info
            last_context_index = index
            continue
        if not is_pdf(msg):
            # Text without a recognized title is ambiguous: do not reset a
            # known context, but keep a short maximum association window.
            continue
        doc = pdf_info(msg)
        if active and last_context_index is not None and index - last_context_index <= 60:
            active["documents"].append(doc)
            last_context_index = index
        else:
            unassigned.append(doc)
    # Recover only a missing title from consistently named, non-generic PDFs.
    # Ambiguous or generic filenames remain blank for manual review.
    for work in works:
        if work["title"] or not work["documents"]:
            continue
        candidates = []
        for doc in work["documents"]:
            if doc["generic_name"]:
                continue
            stem = Path(doc["filename"]).stem
            stem = re.sub(r"(?i)[^\w\r\n]*(?:\d{1,5}\s*[-–_]\s*\d{1,5}|vol(?:umen|ume)?\.?\s*\d+)\s*$", "", stem).strip(" -_.")
            if stem:
                candidates.append(stem)
        if candidates and len({re.sub(r"\W+", "", c).casefold() for c in candidates}) == 1:
            work["title"] = candidates[0]
            work["title_source"] = "pdf_filename_inferred"
        else:
            work["title_source"] = "missing_needs_review"
    return {
        "scanned_messages": len(messages),
        "detected_works": len(works),
        "assigned_pdfs": sum(len(work["documents"]) for work in works),
        "unassigned_pdfs": len(unassigned),
        "works": works,
        "unassigned": unassigned,
        "warning": "Heuristic preview only; associations require review. No files downloaded or database modified.",
    }


def main():
    parser = argparse.ArgumentParser(description="Vista previa de agrupaciones de novelas de Telegram")
    parser.add_argument("--limit", type=int, default=500, help="Mensajes a revisar; 0 = todo")
    parser.add_argument("--output", default="story_preview.json", help="Archivo JSON local")
    parser.add_argument("--inspect", action="store_true", help="Mostrar ejemplos de mensajes para diagnosticar formatos")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit debe ser >= 0")
    report = asyncio.run(analyze(args.limit, args.inspect))
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for key in ("scanned_messages", "detected_works", "assigned_pdfs", "unassigned_pdfs"):
        print(f"{key}: {report[key]}")
    print("Vista previa guardada en:", args.output)
    for work in report["works"][:10]:
        print(f" - {work['title']} | {len(work['documents'])} PDF")
    print("No se descargaron PDF ni se modificó la base de datos.")


if __name__ == "__main__":
    main()
