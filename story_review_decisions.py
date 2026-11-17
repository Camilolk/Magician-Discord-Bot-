"""Review decisions for grouped novel alerts; never modify catalog data.

Examples:
 python story_review_decisions.py list
 python story_review_decisions.py decide --metadata-id 25326 --decision investigate --note "Check Telegram context"
 python story_review_decisions.py decide --metadata-id 25326 --decision approve --target-id 25048 --note "Verified against source"
 python story_review_decisions.py summary
"""
import argparse
import json
from collections import Counter
from pathlib import Path

VALID_DECISIONS = ("pending", "investigate", "approve", "reject")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_groups(path):
    report = read_json(path)
    groups = report.get("groups", [])
    ids = [g["current_metadata_message_id"] for g in groups]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate metadata IDs; refusing ambiguous decisions")
    return groups


def main():
    parser = argparse.ArgumentParser(description="Manual review log (read-only catalog)")
    parser.add_argument("--groups", default="story_grouped_review.json")
    parser.add_argument("--decisions", default="story_review_decisions.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("summary")
    decide = sub.add_parser("decide")
    decide.add_argument("--metadata-id", type=int, required=True)
    decide.add_argument("--decision", choices=VALID_DECISIONS, required=True)
    decide.add_argument("--target-id", type=int)
    decide.add_argument("--note", default="")
    args = parser.parse_args()
    groups = load_groups(args.groups)
    by_id = {g["current_metadata_message_id"]: g for g in groups}
    path = Path(args.decisions)
    saved = read_json(path) if path.exists() else {"decisions": {}}
    decisions = saved.get("decisions", {})
    if not isinstance(decisions, dict):
        raise ValueError("Invalid decisions file")
    if args.command == "decide":
        group = by_id.get(args.metadata_id)
        if not group:
            parser.error("metadata-id not found in grouped report")
        if args.decision == "approve" and group["category"] == "possible_reassignment":
            valid_targets = {c["metadata_message_id"] for c in group["candidate_works"]}
            if args.target_id not in valid_targets:
                parser.error("For reassignment approval, --target-id must match a listed candidate")
            if not args.note.strip():
                parser.error("Approval requires --note explaining source verification")
        elif args.target_id is not None:
            parser.error("--target-id is only valid for reassignment approvals")
        decisions[str(args.metadata_id)] = {
            "decision": args.decision,
            "current_work": group["current_work"],
            "category": group["category"],
            "target_metadata_message_id": args.target_id,
            "note": args.note.strip(),
            "message_ids": group["message_ids"],
        }
        path.write_text(json.dumps({"decisions": decisions}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Decision recorded locally; catalog and PDFs unchanged.")
    elif args.command == "list":
        for group in groups:
            mid = group["current_metadata_message_id"]
            state = decisions.get(str(mid), {}).get("decision", "pending")
            print(f"{mid} | {state:11} | {group['document_count']:2} PDFs | {group['category']} | {group['current_work']}")
    else:
        counts = Counter(decisions.get(str(g["current_metadata_message_id"]), {}).get("decision", "pending") for g in groups)
        print("Review groups:", len(groups))
        for state in VALID_DECISIONS:
            print(f"{state}: {counts[state]}")
        print("No decisions are applied automatically.")


if __name__ == "__main__":
    main()
