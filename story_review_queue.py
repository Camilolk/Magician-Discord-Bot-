"""Generate a human-review queue from story_audit.json.

Read-only: never modifies the Telegram index, source audit, or PDFs.
Usage: python story_review_queue.py
"""
import argparse
import json
from collections import Counter
from pathlib import Path


def build_queue(audit):
    proposals = []
    for work in audit.get("works", []):
        for doc in work.get("documents", []):
            if doc.get("status") != "review":
                continue
            candidates = doc.get("possible_other_works") or []
            reasons = doc.get("reasons") or []
            if "invalid_work_title" in reasons:
                category = "invalid_title"
            elif candidates:
                category = "possible_reassignment"
            elif "filename_title_mismatch" in reasons:
                category = "title_mismatch_or_alias"
            elif "overlapping_chapter_range" in reasons:
                category = "chapter_overlap"
            else:
                category = "other"
            proposals.append({
                "message_id": doc.get("message_id"),
                "filename": doc.get("filename"),
                "current_work": work.get("title"),
                "current_metadata_message_id": work.get("metadata_message_id"),
                "category": category,
                "reasons": reasons,
                "candidates": candidates,
                "decision": "pending",
                "approved_target_metadata_message_id": None,
                "reviewer_note": "",
            })
    priority = {"invalid_title": 0, "possible_reassignment": 1,
                "chapter_overlap": 2, "title_mismatch_or_alias": 3, "other": 4}
    proposals.sort(key=lambda p: (priority.get(p["category"], 9),
                                  p["message_id"] if p["message_id"] is not None else -1))
    return proposals


def main():
    parser = argparse.ArgumentParser(description="Cola de revisión manual de novelas")
    parser.add_argument("--input", default="story_audit.json")
    parser.add_argument("--output", default="story_review_queue.json")
    args = parser.parse_args()
    audit = json.loads(Path(args.input).read_text(encoding="utf-8"))
    proposals = build_queue(audit)
    result = {
        "summary": {
            "pending": len(proposals),
            "by_category": dict(Counter(p["category"] for p in proposals)),
        },
        "instructions": (
            "This is a review worksheet, not an automatic correction. "
            "Do not apply reassignment solely from a filename score. "
            "Use the Telegram source context to choose among duplicate works."
        ),
        "proposals": proposals,
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    print("Cola guardada en:", args.output)
    print("Pendientes:", len(proposals))
    for category, count in result["summary"]["by_category"].items():
        print(f" - {category}: {count}")
    print("Primeras propuestas:")
    for p in proposals[:8]:
        best = p["candidates"][0]["title"] if p["candidates"] else "(sin candidato)"
        print(f" - {p['message_id']}: {p['filename']} -> {best} [{p['category']}]")
    print("Solo se generó un informe. No se modificó la base de datos.")


if __name__ == "__main__":
    main()
