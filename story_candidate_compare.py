"""Compare suspicious Telegram PDFs with candidate publication contents (read-only).

Usage:
 python story_candidate_compare.py --all
 python story_candidate_compare.py --metadata-id 24580
"""
import argparse
import json
import re
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def volume(filename):
    match = re.search(r"(?i)\b(?:vol(?:umen|ume)?|tomo)\s*[-_. ]*0*(\d{1,3})\b", filename)
    return int(match.group(1)) if match else None


def chapter_range(doc):
    existing = doc.get("chapter_range")
    if existing and len(existing) == 2:
        return existing
    stem = Path(doc["filename"]).stem
    matches = re.findall(r"(?<!\d)(\d{1,5})\s*[-–_]\s*(\d{1,5})(?!\d)", stem)
    if not matches:
        return None
    a, b = map(int, matches[-1])
    return [a, b] if a <= b else None


def compare(doc, target_docs):
    vol = volume(doc["filename"])
    chapters = chapter_range(doc)
    overlaps = []
    same_volumes = []
    identical_names = []
    for other in target_docs:
        if other["message_id"] == doc["message_id"]:
            continue
        if doc["filename"].casefold() == other["filename"].casefold():
            identical_names.append(other["message_id"])
        other_vol = volume(other["filename"])
        if vol is not None and other_vol == vol:
            same_volumes.append(other["message_id"])
        other_range = chapter_range(other)
        if chapters and other_range and max(chapters[0], other_range[0]) <= min(chapters[1], other_range[1]):
            overlaps.append(other["message_id"])
    return {
        "filename": doc["filename"],
        "message_id": doc["message_id"],
        "volume": vol,
        "chapter_range": chapters,
        "identical_filename_message_ids": identical_names,
        "same_volume_message_ids": same_volumes,
        "overlapping_chapter_message_ids": overlaps,
        "note": "Filename heuristics only; overlaps may be legitimate editions or updates.",
    }


def main():
    p = argparse.ArgumentParser(description="Compare candidate volumes and chapter ranges")
    p.add_argument("--all", action="store_true")
    p.add_argument("--metadata-id", type=int)
    p.add_argument("--preview", default="story_preview.json")
    p.add_argument("--groups", default="story_grouped_review.json")
    p.add_argument("--output", default="story_candidate_comparison.json")
    args = p.parse_args()
    if args.all == (args.metadata_id is not None):
        p.error("Choose exactly one of --all or --metadata-id")
    preview = load(args.preview)
    groups = load(args.groups)["groups"]
    by_id = {w["message_id"]: w for w in preview["works"]}
    by_pdf = {d["message_id"]: d for w in preview["works"] for d in w["documents"]}
    reports = []
    for group in groups:
        if group["category"] != "possible_reassignment":
            continue
        mid = group["current_metadata_message_id"]
        if args.metadata_id is not None and mid != args.metadata_id:
            continue
        for doc_id in group["message_ids"]:
            doc = by_pdf.get(doc_id)
            if doc is None:
                reports.append({"current_metadata_message_id": mid, "pdf_message_id": doc_id, "error": "PDF not found in preview"})
                continue
            candidates = []
            for candidate in group["candidate_works"]:
                target_id = candidate["metadata_message_id"]
                target = by_id.get(target_id)
                if target is None:
                    candidates.append({"metadata_message_id": target_id, "error": "Candidate not in preview"})
                    continue
                result = compare(doc, target["documents"])
                candidates.append({
                    "metadata_message_id": target_id,
                    "title": target["title"],
                    "existing_pdf_count": len(target["documents"]),
                    "existing_pdf_examples": [d["filename"] for d in target["documents"][:8]],
                    **result,
                })
            reports.append({
                "current_metadata_message_id": mid,
                "current_work": group["current_work"],
                "pdf_message_id": doc_id,
                "pdf_filename": doc["filename"],
                "candidates": candidates,
                "decision": "human_review_required",
            })
    if not reports:
        p.error("No matching reassignment group")
    Path(args.output).write_text(json.dumps({
        "reports": reports,
        "warning": "Read-only filename comparison; never automatically move PDFs or approve decisions.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    for report in reports:
        print(f"PDF {report['pdf_message_id']}: {report.get('pdf_filename', 'not found')}")
        for c in report.get("candidates", []):
            if "error" in c:
                print(f"  Candidate {c['metadata_message_id']}: {c['error']}")
            else:
                print(f"  Candidate {c['metadata_message_id']} ({c['title']}): {c['existing_pdf_count']} PDFs; same volumes={len(c['same_volume_message_ids'])}, chapter overlaps={len(c['overlapping_chapter_message_ids'])}, identical filenames={len(c['identical_filename_message_ids'])}")
    print("Saved:", args.output)
    print("No catalog or database changes.")


if __name__ == "__main__":
    main()
