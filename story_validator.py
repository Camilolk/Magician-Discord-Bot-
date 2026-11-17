"""Audit story_preview.json without Telegram access or database writes.

Usage: python story_validator.py --input story_preview.json
"""
import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

RANGE = re.compile(r"(?<!\d)(\d{1,5})\s*[-–_]\s*(\d{1,5})(?!\d)")
VOLUME = re.compile(r"\b(?:vol(?:umen|ume)?|tomo)\.?\s*#?\s*(\d{1,3})\b", re.I)
LABEL = re.compile(r"(?i)^(?:🔰|📗|📘|📚|📖)?\s*[⊳>:]*\s*(?:origen|estado|autor|g[eé]nero|fansubs)\s*:")
STOP = {"the", "a", "an", "of", "and", "in", "to", "is", "as", "de", "del", "la", "el", "los", "las", "en", "y", "un", "una", "novela", "light", "ln", "wn", "pdf", "vol", "volumen", "tomo"}

def normalize(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()

def tokens(value):
    return {word for word in normalize(value).split() if len(word) > 2 and word not in STOP}

def filename_parts(filename):
    stem = re.sub(r"\.pdf$", "", filename, flags=re.I)
    volume = VOLUME.search(stem)
    ranges = list(RANGE.finditer(stem))
    chapter = None
    if ranges:
        match = ranges[-1]
        start, end = int(match.group(1)), int(match.group(2))
        if start <= end and end - start <= 10000:
            chapter = [start, end]
            stem = stem[:match.start()] + " " + stem[match.end():]
    if volume:
        stem = VOLUME.sub(" ", stem)
    stem = re.sub(r"\b(?:MTL|LN|WN|PDF|completo|complete|novela ligera)\b", " ", stem, flags=re.I)
    stem = re.sub(r"[\[\]()_.,-]+", " ", stem).strip()
    return chapter, int(volume.group(1)) if volume else None, stem

def audit(data):
    reports = []
    all_ids = []
    for work in data["works"]:
        title = (work.get("title") or "").strip()
        title_invalid = not title or bool(LABEL.match(title))
        records = []
        intervals = []
        for doc in work.get("documents", []):
            filename = doc.get("filename", "")
            chapter, volume, stem = filename_parts(filename)
            expected, actual = tokens(title), tokens(stem)
            overlap = len(expected & actual) / len(expected) if expected else 0
            generic = not actual or (chapter is not None and not tokens(stem))
            reasons = []
            if title_invalid:
                reasons.append("invalid_work_title")
            if not generic and overlap < 0.35:
                reasons.append("filename_title_mismatch")
            if chapter and chapter[0] > chapter[1]:
                reasons.append("invalid_range")
            if chapter:
                for prior, prior_id in intervals:
                    if max(chapter[0], prior[0]) <= min(chapter[1], prior[1]):
                        reasons.append("overlapping_chapter_range")
                        break
                intervals.append((chapter, doc.get("message_id")))
            status = "review" if reasons else ("contextual" if generic else "likely")
            records.append({
                "message_id": doc.get("message_id"),
                "filename": filename,
                "chapter_range": chapter,
                "volume": volume,
                "status": status,
                "reasons": reasons,
                "title_token_overlap": round(overlap, 2) if not generic else None,
            })
            all_ids.append(doc.get("message_id"))
        reports.append({
            "title": title, "metadata_message_id": work.get("message_id"),
            "documents": records, "review_count": sum(d["status"] == "review" for d in records)
        })
    duplicates = defaultdict(list)
    for work in reports:
        if normalize(work["title"]):
            duplicates[normalize(work["title"])].append(work["metadata_message_id"])
    counts = Counter(doc["status"] for work in reports for doc in work["documents"])
    return {
        "summary": {
            "works": len(reports),
            "documents": len(all_ids),
            "likely": counts["likely"],
            "contextual": counts["contextual"],
            "needs_review": counts["review"],
            "duplicate_message_ids": len(all_ids) - len(set(all_ids)),
            "repeated_titles": sum(len(v) > 1 for v in duplicates.values()),
            "unassigned": len(data.get("unassigned", [])),
        },
        "repeated_titles": {k: v for k, v in duplicates.items() if len(v) > 1},
        "works": reports,
        "unassigned": data.get("unassigned", []),
        "note": "Heuristic validation only. Likely is not verified; contextual files need source context. No database changes.",
    }

def main():
    parser = argparse.ArgumentParser(description="Audita asociaciones de novelas y PDF")
    parser.add_argument("--input", default="story_preview.json")
    parser.add_argument("--output", default="story_audit.json")
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report = audit(data)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Auditoría guardada en:", args.output)
    for key, value in report["summary"].items():
        print(f"{key}: {value}")
    print("Ejemplos que requieren revisión:")
    shown = 0
    for work in report["works"]:
        for doc in work["documents"]:
            if doc["status"] == "review":
                print(f" - {work['title']} -> {doc['filename']} ({', '.join(doc['reasons'])})")
                shown += 1
                if shown >= 12:
                    return

if __name__ == "__main__":
    main()
