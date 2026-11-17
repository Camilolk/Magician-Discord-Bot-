"""Build an evidence-based, read-only review report from local JSON files."""
import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(comparison, telegram, decisions):
    a = {r["pdf_message_id"]: r for r in comparison["reports"]}
    b = {r["suspect_document"].get("message_id"): r for r in telegram["reports"]}
    if set(a) != set(b):
        raise ValueError("Reports cover different PDF IDs. Rerun both comparison commands with --all.")
    result = []
    for pdf_id, record in a.items():
        evidence = b[pdf_id]
        mid = record["current_metadata_message_id"]
        if evidence["current_metadata_message_id"] != mid:
            raise ValueError(f"Metadata mismatch for PDF {pdf_id}")
        source = evidence["suspect_document"]
        candidates = []
        for candidate in record["candidates"]:
            cid = candidate["metadata_message_id"]
            match = next((c for c in evidence["candidates"] if c["metadata_message_id"] == cid), None)
            if match is None:
                raise ValueError(f"Missing candidate {cid} for PDF {pdf_id}")
            comparisons = {}
            for entry in match["documents"]:
                label = entry["comparison"]
                comparisons[label] = comparisons.get(label, 0) + 1
            same_name = [entry["document"] for entry in match["documents"]
                         if entry["comparison"] in ("same_name_different_document_ids", "different_document_ids_same_name_and_size", "same_telegram_document_id")]
            candidates.append({
                "metadata_message_id": cid,
                "title": candidate.get("title"),
                "same_name_or_identity": same_name,
                "comparison_counts": comparisons,
                "same_volume_message_ids": candidate.get("same_volume_message_ids", []),
                "overlapping_chapter_message_ids": candidate.get("overlapping_chapter_message_ids", []),
            })
        has_same_name = any(c["same_name_or_identity"] for c in candidates)
        has_same_doc = any(c["comparison_counts"].get("same_telegram_document_id", 0) for c in candidates)
        if not source.get("found") or not source.get("document_id"):
            classification = "insufficient_telegram_evidence"
        elif has_same_doc:
            classification = "same_telegram_document_found"
        elif has_same_name:
            classification = "possible_alternative_version"
        else:
            classification = "possible_misassociation_needs_review"
        previous = decisions.get(str(mid), {})
        result.append({
            "pdf_message_id": pdf_id,
            "filename": record.get("pdf_filename"),
            "current_work": record["current_work"],
            "current_metadata_message_id": mid,
            "suspect_document": source,
            "classification": classification,
            "candidates": candidates,
            "existing_review_decision": previous.get("decision", "pending"),
            "existing_review_note": previous.get("note", ""),
            "recommendation": "Investigate manually; no reassignment or deletion authorized.",
        })
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--comparison", default="story_candidate_comparison.json")
    p.add_argument("--telegram", default="telegram_document_comparison.json")
    p.add_argument("--decisions", default="story_review_decisions.json")
    p.add_argument("--output", default="story_assisted_review.json")
    args = p.parse_args()
    decision_path = Path(args.decisions)
    decisions = load(decision_path).get("decisions", {}) if decision_path.exists() else {}
    reports = build(load(args.comparison), load(args.telegram), decisions)
    Path(args.output).write_text(json.dumps({
        "reports": reports,
        "warning": "Classification is advisory only. No content hashes or PDF content inspected. No decisions applied.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in reports:
        print(f"{r['pdf_message_id']} | {r['classification']} | {r['filename']}")
        print(f"  Current: {r['current_work']} | Review: {r['existing_review_decision']}")
        for c in r["candidates"]:
            print(f"  Candidate {c['metadata_message_id']}: {c['title']} | name/identity matches: {len(c['same_name_or_identity'])}")
    print("Saved:", args.output)
    print("Read-only: catalog, database, PDFs, and decisions unchanged.")


if __name__ == "__main__":
    main()
