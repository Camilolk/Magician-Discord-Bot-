"""Group pending story reviews by work, without changing any source data.

Usage: python story_grouped_review.py
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


def classify_group(items):
    categories = {item["category"] for item in items}
    if "possible_reassignment" in categories:
        return "possible_reassignment"
    if "chapter_overlap" in categories:
        return "chapter_overlap"
    return "title_mismatch_or_alias"


def filename_pattern(name):
    stem = re.sub(r"(?i)\.pdf$", "", name).strip()
    stem = re.sub(r"(?i)\b(?:vol(?:umen|ume)?|tomo)\.?\s*\d+(?:\.\d+)?\b.*$", "", stem)
    stem = re.sub(r"(?i)[\[(]?\s*\d{1,5}\s*[-–_]\s*\d{1,5}\s*[\])]?$", "", stem)
    stem = re.sub(r"(?i)\s*\d{1,3}\s*[-–]\s*[^/]+$", "", stem)
    return stem.strip(" -_.[]()")


def build_report(queue):
    groups = defaultdict(list)
    for item in queue.get("proposals", []):
        key = (item.get("current_metadata_message_id"), item.get("current_work"))
        groups[key].append(item)
    results = []
    for (metadata_id, title), items in groups.items():
        category = classify_group(items)
        patterns = Counter(filename_pattern(item.get("filename") or "") for item in items)
        suggestions = []
        for item in items:
            for candidate in item.get("candidates", []):
                identity = (candidate.get("metadata_message_id"), candidate.get("title"))
                if identity not in [(s["metadata_message_id"], s["title"]) for s in suggestions]:
                    suggestions.append({
                        "metadata_message_id": identity[0],
                        "title": identity[1],
                        "score": candidate.get("score"),
                    })
        suggestions.sort(key=lambda x: (-(x["score"] or 0), str(x["title"])))
        results.append({
            "current_work": title,
            "current_metadata_message_id": metadata_id,
            "category": category,
            "document_count": len(items),
            "reason_counts": dict(Counter(reason for item in items for reason in item.get("reasons", []))),
            "filename_patterns": [{"pattern": pattern, "count": count} for pattern, count in patterns.most_common()],
            "candidate_works": suggestions,
            "message_ids": [item.get("message_id") for item in items],
            "decision": "pending",
            "reviewer_note": "",
            "warning": "Patterns are filename-derived suggestions, not verified aliases.",
        })
    priority = {"possible_reassignment": 0, "chapter_overlap": 1, "title_mismatch_or_alias": 2}
    results.sort(key=lambda g: (priority.get(g["category"], 9), -g["document_count"], str(g["current_work"])))
    return {
        "summary": {
            "groups": len(results),
            "documents": sum(g["document_count"] for g in results),
            "groups_by_category": dict(Counter(g["category"] for g in results)),
        },
        "groups": results,
        "warning": "Read-only report; no alias, association, or database changes.",
    }


def main():
    parser = argparse.ArgumentParser(description="Agrupa revisiones por publicación de novela")
    parser.add_argument("--input", default="story_review_queue.json")
    parser.add_argument("--output", default="story_grouped_review.json")
    args = parser.parse_args()
    queue = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report = build_report(queue)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Informe agrupado:", args.output)
    print("Grupos:", report["summary"]["groups"])
    print("Documentos:", report["summary"]["documents"])
    for category, count in report["summary"]["groups_by_category"].items():
        print(f" - {category}: {count} grupos")
    print("No se modificaron los PDF ni la base de datos.")


if __name__ == "__main__":
    main()
