"""Compare Telegram document identities and metadata without downloading files.

Usage:
 python telegram_document_compare.py --all
 python telegram_document_compare.py --metadata-id 24580

Reads story_candidate_comparison.json and queries only the referenced messages.
Document IDs are Telegram identifiers, not cryptographic file hashes.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeFilename

from telegram_story_analyzer import CHANNEL_ID


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def document_info(msg):
    if msg is None:
        return {"found": False}
    doc = getattr(msg, "document", None)
    filename = None
    if doc:
        for attr in doc.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                filename = attr.file_name
                break
    return {
        "found": True,
        "message_id": msg.id,
        "date_utc": msg.date.isoformat() if msg.date else None,
        "filename": filename or getattr(getattr(msg, "file", None), "name", None),
        "document_id": str(doc.id) if doc else None,
        "size_bytes": doc.size if doc else None,
        "mime_type": doc.mime_type if doc else None,
        "is_pdf": bool(doc and (doc.mime_type or "").lower() == "application/pdf") or bool(filename and filename.lower().endswith(".pdf")),
    }


async def collect(ids):
    load_dotenv()
    api_id, api_hash = os.getenv("TELEGRAM_API_ID"), os.getenv("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        raise RuntimeError("Missing TELEGRAM_API_ID or TELEGRAM_API_HASH in .env")
    async with TelegramClient(os.getenv("TELEGRAM_SESSION_PATH", "magician_telegram"), int(api_id), api_hash) as client:
        chat = await client.get_entity(CHANNEL_ID)
        messages = await client.get_messages(chat, ids=sorted(ids))
    return {msg.id: document_info(msg) for msg in messages if msg is not None}


def compare(source, target):
    if not source.get("found") or not target.get("found"):
        return "message_missing"
    if not source.get("document_id") or not target.get("document_id"):
        return "document_missing"
    if source["document_id"] == target["document_id"]:
        return "same_telegram_document_id"
    if source["size_bytes"] == target["size_bytes"] and source["filename"] == target["filename"]:
        return "different_document_ids_same_name_and_size"
    if source["filename"] == target["filename"]:
        return "same_name_different_document_ids"
    return "different_document_ids"


def main():
    p = argparse.ArgumentParser(description="Read-only Telegram document identity comparison")
    p.add_argument("--all", action="store_true")
    p.add_argument("--metadata-id", type=int)
    p.add_argument("--comparison", default="story_candidate_comparison.json")
    p.add_argument("--preview", default="story_preview.json")
    p.add_argument("--output", default="telegram_document_comparison.json")
    args = p.parse_args()
    if args.all == (args.metadata_id is not None):
        p.error("Choose exactly one of --all or --metadata-id")
    reports = read_json(args.comparison)["reports"]
    if args.metadata_id is not None:
        reports = [r for r in reports if r["current_metadata_message_id"] == args.metadata_id]
    if not reports:
        p.error("No matching reports. Run story_candidate_compare.py --all first.")
    preview = read_json(args.preview)
    works = {w["message_id"]: w for w in preview["works"]}
    ids = set()
    for report in reports:
        ids.add(report["pdf_message_id"])
        ids.add(report["current_metadata_message_id"])
        for candidate in report.get("candidates", []):
            cid = candidate["metadata_message_id"]
            ids.add(cid)
            ids.update(d["message_id"] for d in works.get(cid, {}).get("documents", []))
    evidence = asyncio.run(collect(ids))
    output = []
    for report in reports:
        source = evidence.get(report["pdf_message_id"], {"found": False})
        candidates = []
        for candidate in report.get("candidates", []):
            cid = candidate["metadata_message_id"]
            target_docs = []
            for doc in works.get(cid, {}).get("documents", []):
                other = evidence.get(doc["message_id"], {"found": False})
                target_docs.append({
                    "document": other,
                    "comparison": compare(source, other),
                })
            candidates.append({
                "metadata_message_id": cid,
                "title": candidate.get("title"),
                "metadata_message": evidence.get(cid, {"found": False}),
                "documents": target_docs,
            })
        output.append({
            "current_work": report.get("current_work"),
            "current_metadata_message_id": report["current_metadata_message_id"],
            "current_metadata_message": evidence.get(report["current_metadata_message_id"], {"found": False}),
            "suspect_document": source,
            "candidates": candidates,
            "decision": "human_review_required",
        })
    Path(args.output).write_text(json.dumps({
        "reports": output,
        "warning": "Document IDs are not hashes; equal IDs indicate a shared Telegram document, differing IDs do not prove different content. No changes applied.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    for report in output:
        source = report["suspect_document"]
        print(f"Suspect {source.get('message_id', '?')}: {source.get('filename')} | doc_id={source.get('document_id')} | size={source.get('size_bytes')}")
        for candidate in report["candidates"]:
            from collections import Counter
            counts = Counter(d["comparison"] for d in candidate["documents"])
            print(f"  Candidate {candidate['metadata_message_id']} ({candidate['title']}): {dict(counts)}")
            for entry in candidate["documents"]:
                if entry["comparison"] in ("same_telegram_document_id", "different_document_ids_same_name_and_size", "same_name_different_document_ids"):
                    other = entry["document"]
                    print(f"    Match message {other.get('message_id')}: {entry['comparison']} | size={other.get('size_bytes')}")
    print("Saved:", args.output)
    print("No files downloaded, no associations or database changed.")


if __name__ == "__main__":
    main()
