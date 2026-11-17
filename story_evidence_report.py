"""Build a conservative, read-only review report from local evidence.

Run:
 python story_evidence_report.py --all
 python story_evidence_report.py --metadata-id 24580
"""
import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Consolidate reassignment evidence without modifying the catalog")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--metadata-id", type=int)
    parser.add_argument("--comparison", default="story_candidate_comparison.json")
    parser.add_argument("--documents", default="telegram_document_comparison.json")
    parser.add_argument("--decisions", default="story_review_decisions.json")
    parser.add_argument("--output", default="story_evidence_report.json")
    args = parser.parse_args()
    if args.all == (args.metadata_id is not None):
        parser.error("Choose exactly one of --all or --metadata-id")

    filename_reports = load(args.comparison)["reports"]
    telegram_reports = load(args.documents)["reports"]
    by_key = {}
    for report in telegram_reports:
        doc_id = report.get("suspect_document", {}).get("message_id")
        key = (report.get("current_metadata_message_id"), doc_id)
        if key in by_key:
            parser.error("Duplicate Telegram evidence record: " + str(key))
        by_key[key] = report

    decisions_path = Path(args.decisions)
    decisions = load(decisions_path).get("decisions", {}) if decisions_path.exists() else {}
    output = []
    seen = set()
    for report in filename_reports:
        mid, doc_id = report["current_metadata_message_id"], report["pdf_message_id"]
        if args.metadata_id is not None and mid != args.metadata_id:
            continue
        key = (mid, doc_id)
        if key in seen:
            parser.error("Duplicate candidate report: " + str(key))
        seen.add(key)
        evidence = by_key.get(key)
        if evidence is None:
            parser.error("Missing Telegram evidence for " + str(key) + "; rerun telegram_document_compare.py --all")
        source = evidence["suspect_document"]
        if not source.get("found") or not source.get("document_id"):
            parser.error("Missing original Telegram PDF metadata for " + str(key))
        if source.get("filename", "").casefold() != report["pdf_filename"].casefold():
            parser.error("Stale or mismatched PDF filename for " + str(key))
        candidates_by_id = {c["metadata_message_id"]: c for c in evidence["candidates"]}
        candidate_summaries = []
        for candidate in report.get("candidates", []):
            cid = candidate["metadata_message_id"]
            other = candidates_by_id.get(cid)
            if other is None:
                parser.error("Missing candidate evidence for " + str((key, cid)))
            matches = []
            for entry in other["documents"]:
                comparison = entry["comparison"]
                if comparison != "different_document_ids":
                    matches.append({
                        "message_id": entry["document"].get("message_id"),
                        "filename": entry["document"].get("filename"),
                        "size_bytes": entry["document"].get("size_bytes"),
                        "comparison": comparison,
                    })
            candidate_summaries.append({
                "metadata_message_id": cid,
                "title": candidate.get("title"),
                "existing_pdf_count": len(other["documents"]),
                "same_filename_count": len(candidate.get("identical_filename_message_ids", [])),
                "volume_overlap_count": len(candidate.get("same_volume_message_ids", [])),
                "chapter_overlap_count": len(candidate.get("overlapping_chapter_message_ids", [])),
                "matching_documents": matches,
            })
        has_same_name = any(c["same_filename_count"] for c in candidate_summaries)
        has_same_doc = any(any(m["comparison"] == "same_telegram_document_id" for m in c["matching_documents"]) for c in candidate_summaries)
        if has_same_doc:
            classification = "possible_reused_telegram_document"
        elif has_same_name:
            classification = "possible_alternate_version"
        else:
            classification = "possible_misassociation_without_exact_filename_match"
        output.append({
            "current_metadata_message_id": mid,
            "current_work": report.get("current_work"),
            "pdf_message_id": doc_id,
            "pdf_filename": report["pdf_filename"],
            "source_document_id": source["document_id"],
            "source_size_bytes": source.get("size_bytes"),
            "source_date_utc": source.get("date_utc"),
            "classification": classification,
            "candidate_works": candidate_summaries,
            "review_decision": decisions.get(str(mid), {}).get("decision", "pending"),
            "recommended_action": "investigate_manually",
            "reason": "Filename, size and Telegram IDs alone cannot establish correct ownership or identical PDF contents.",
        })
    if not output:
        parser.error("No matching evidence found")
    Path(args.output).write_text(json.dumps({
        "reports": output,
        "warning": "Review aid only; classifications are hypotheses, not approval. No PDF or catalog changes.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in output:
        print(f"PDF {item['pdf_message_id']} | {item['classification']} | decision={item['review_decision']}")
        for candidate in item["candidate_works"]:
            print(f"  Candidate {candidate['metadata_message_id']}: {candidate['title']} | filename matches={candidate['same_filename_count']} | chapter overlaps={candidate['chapter_overlap_count']}")
    print("Saved:", args.output)
    print("No catalog, database or PDF changes.")


if __name__ == "__main__":
    main()
