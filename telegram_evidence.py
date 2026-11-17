"""Inspect Telegram evidence for suspected PDF reassignment, without downloads or writes.

Usage:
 python telegram_evidence.py --metadata-id 24580
 python telegram_evidence.py --all
"""
import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

from telegram_story_analyzer import CHANNEL_ID, fields_from_text, is_pdf


def read_json(filename):
    return json.loads(Path(filename).read_text(encoding="utf-8"))


async def inspect(groups, preview):
    load_dotenv()
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        raise RuntimeError("Missing TELEGRAM_API_ID or TELEGRAM_API_HASH in .env")
    works = {w["message_id"]: w for w in preview["works"]}
    ids = set()
    for group in groups:
        ids.add(group["current_metadata_message_id"])
        ids.update(group["message_ids"])
        ids.update(c["metadata_message_id"] for c in group["candidate_works"])
    async with TelegramClient(os.getenv("TELEGRAM_SESSION_PATH", "magician_telegram"), int(api_id), api_hash) as client:
        chat = await client.get_entity(CHANNEL_ID)
        found = await client.get_messages(chat, ids=sorted(ids))
    messages = {m.id: m for m in found if m is not None}
    reports = []
    for group in groups:
        origin_id = group["current_metadata_message_id"]
        origin = messages.get(origin_id)
        documents = []
        for mid in group["message_ids"]:
            msg = messages.get(mid)
            file = getattr(msg, "file", None) if msg else None
            documents.append({
                "message_id": mid,
                "found": msg is not None,
                "is_pdf": is_pdf(msg) if msg else False,
                "filename": (getattr(file, "name", None) or "") if file else None,
                "caption_excerpt": (msg.message or "")[:240] if msg else None,
                "distance_from_current_metadata": mid - origin_id,
            })
        candidates = []
        for candidate in group["candidate_works"]:
            cid = candidate["metadata_message_id"]
            msg = messages.get(cid)
            fields = fields_from_text(msg.message or "") if msg else {}
            candidates.append({
                "metadata_message_id": cid,
                "found": msg is not None,
                "telegram_title": fields.get("title"),
                "preview_title": works.get(cid, {}).get("title"),
                "suggested_title": candidate["title"],
                "filename_similarity_score": candidate.get("score"),
                "distance_from_first_pdf": cid - group["message_ids"][0],
            })
        reports.append({
            "current_work": group["current_work"],
            "current_metadata_message_id": origin_id,
            "current_telegram_title": fields_from_text(origin.message or "").get("title") if origin else None,
            "current_metadata_found": origin is not None,
            "documents": documents,
            "candidates": candidates,
            "decision": "needs_human_verification",
        })
    return reports


def main():
    parser = argparse.ArgumentParser(description="Read-only Telegram evidence report")
    parser.add_argument("--metadata-id", type=int)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--groups", default="story_grouped_review.json")
    parser.add_argument("--preview", default="story_preview.json")
    parser.add_argument("--output", default="telegram_evidence.json")
    args = parser.parse_args()
    if args.all == (args.metadata_id is not None):
        parser.error("Choose exactly one of --all or --metadata-id")
    groups = [g for g in read_json(args.groups)["groups"] if g["category"] == "possible_reassignment"]
    if args.metadata_id is not None:
        groups = [g for g in groups if g["current_metadata_message_id"] == args.metadata_id]
    if not groups:
        parser.error("No matching reassignment group")
    evidence = asyncio.run(inspect(groups, read_json(args.preview)))
    Path(args.output).write_text(json.dumps({"reports": evidence, "warning": "Evidence only; no automatic reassignment or PDF download."}, ensure_ascii=False, indent=2), encoding="utf-8")
    for report in evidence:
        print(f"Current: {report['current_work']} (message {report['current_metadata_message_id']})")
        for doc in report["documents"]:
            print(f"  PDF {doc['message_id']}: {doc['filename']} | found={doc['found']} | pdf={doc['is_pdf']}")
        for candidate in report["candidates"]:
            print(f"  Candidate {candidate['metadata_message_id']}: {candidate['telegram_title']} | found={candidate['found']}")
    print("Saved:", args.output)
    print("No database, catalog associations, or PDF files were modified.")


if __name__ == "__main__":
    main()
