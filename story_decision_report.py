"""Read-only HTML and JSON review dashboard for Magician."""
import argparse
import html
import json
from collections import Counter
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def evidence_map(path):
    if not path.exists():
        return {}
    data = load(path)
    return {int(r["current_metadata_message_id"]): r for r in data.get("reports", [])}

def build(groups, decisions, candidates, telegram):
    rows = []
    for g in groups:
        mid = int(g["current_metadata_message_id"])
        saved = decisions.get(str(mid), {})
        cat = g["category"]
        candidate_report = candidates.get(mid, {})
        telegram_report = telegram.get(mid, {})
        candidate_items = candidate_report.get("candidates", [])
        telegram_items = telegram_report.get("candidates", [])
        comparisons = Counter(
            d.get("comparison", "unknown")
            for c in telegram_items for d in c.get("documents", [])
        )
        has_errors = any("error" in c for c in candidate_items)
        status = ("insufficient_evidence" if cat == "possible_reassignment" and
                  (not candidate_report or not telegram_report or has_errors or
                   comparisons.get("message_missing", 0) or comparisons.get("document_missing", 0))
                  else "needs_review")
        if cat == "possible_reassignment" and candidate_report and telegram_report and not has_errors and not (
            comparisons.get("message_missing", 0) or comparisons.get("document_missing", 0)
        ):
            status = "ready_for_manual_review"
        rows.append({
            "metadata_id": mid, "title": g["current_work"], "category": cat,
            "document_count": g["document_count"], "message_ids": g.get("message_ids", []),
            "candidate_works": g.get("candidate_works", []),
            "filename_patterns": g.get("filename_patterns", []),
            "reason_counts": g.get("reason_counts", {}),
            "evidence_status": status,
            "manual_decision": saved.get("decision", "pending"),
            "manual_note": saved.get("note", ""),
            "manual_target_id": saved.get("target_metadata_message_id"),
            "filename_comparison": candidate_report,
            "telegram_comparison": telegram_report,
            "telegram_comparison_counts": dict(comparisons),
        })
    return {"summary": {"groups": len(rows), "documents": sum(r["document_count"] for r in rows),
                        "by_evidence_status": dict(Counter(r["evidence_status"] for r in rows)),
                        "by_manual_decision": dict(Counter(r["manual_decision"] for r in rows))},
            "groups": rows,
            "warning": "Read-only; filename and Telegram metadata are not proof of content identity. No changes applied."}

def render(data):
    esc = lambda value: html.escape(str(value), quote=True)
    sections = []
    for r in data["groups"]:
        candidates = ", ".join(f'{esc(c.get("title"))} (ID {esc(c.get("metadata_message_id"))})'
                               for c in r["candidate_works"]) or "Ninguno"
        patterns = ", ".join(f'{esc(p.get("pattern"))} ({esc(p.get("count"))})'
                             for p in r["filename_patterns"]) or "Ninguno"
        counts = ", ".join(f"{esc(k)}: {esc(v)}" for k, v in r["telegram_comparison_counts"].items()) or "Sin comparación"
        sections.append(
            f'<article data-search="{esc((r["title"]+" "+r["category"]).lower())}" data-status="{esc(r["evidence_status"])}">'
            f'<h2>{esc(r["title"])}</h2><p><strong>ID:</strong> {r["metadata_id"]} · '
            f'<strong>PDFs:</strong> {r["document_count"]} · <strong>Categoría:</strong> {esc(r["category"])}</p>'
            f'<p><strong>Evidencia:</strong> {esc(r["evidence_status"])} · '
            f'<strong>Decisión manual:</strong> {esc(r["manual_decision"])}</p>'
            f'<details><summary>Ver evidencia</summary><p><b>Candidatos:</b> {candidates}</p>'
            f'<p><b>Patrones:</b> {patterns}</p><p><b>Telegram:</b> {counts}</p>'
            f'<p><b>Nota:</b> {esc(r["manual_note"])}</p></details></article>')
    summary = data["summary"]
    return """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Magician · Revisión de novelas</title>
<style>
body{font:16px system-ui;background:#101526;color:#e9eaf5;margin:0 auto;padding:28px;max-width:1050px}
h1{color:#c6b8ff}article{background:#1d2540;border:1px solid #374363;border-radius:14px;padding:18px;margin:14px 0}
h2{margin:0 0 8px;font-size:20px}p{line-height:1.5}input,select{background:#222c47;color:white;border:1px solid #526084;border-radius:8px;padding:12px;margin:5px}
summary{cursor:pointer;color:#b6c7ff}small{color:#aebbd2}
</style></head><body><h1>🪄 Magician · Revisión de novelas</h1>
<p>Informe de solo lectura. Ninguna reasignación se aprueba automáticamente.</p>
<p><b>Grupos:</b> """ + str(summary["groups"]) + """ · <b>PDFs:</b> """ + str(summary["documents"]) + """</p>
<input id="search" placeholder="Buscar novela..." aria-label="Buscar novela">
<select id="status" aria-label="Filtrar evidencia"><option value="">Todas las evidencias</option>
<option>needs_review</option><option>insufficient_evidence</option>
<option>ready_for_manual_review</option></select>
<main>""" + "\n".join(sections) + """</main>
<small>Los identificadores de Telegram no son hashes. Verifica las fuentes antes de decidir.</small>
<script>
const search=document.getElementById('search'),status=document.getElementById('status');
function filter(){for(const card of document.querySelectorAll('article'))
card.hidden=!(card.dataset.search.includes(search.value.toLowerCase()) &&
(!status.value||card.dataset.status===status.value));}
search.addEventListener('input',filter);status.addEventListener('change',filter);
</script></body></html>"""

def main():
    p = argparse.ArgumentParser(description="Generate read-only Magician review reports")
    p.add_argument("--groups", default="story_grouped_review.json")
    p.add_argument("--decisions", default="story_review_decisions.json")
    p.add_argument("--candidates", default="story_candidate_comparison.json")
    p.add_argument("--telegram", default="telegram_document_comparison.json")
    p.add_argument("--json-output", default="story_decision_report.json")
    p.add_argument("--html-output", default="story_decision_report.html")
    args = p.parse_args()
    groups = load(args.groups)["groups"]
    mids = [g["current_metadata_message_id"] for g in groups]
    if len(mids) != len(set(mids)):
        p.error("Duplicate metadata IDs in grouped report")
    decisions = load(args.decisions).get("decisions", {}) if Path(args.decisions).exists() else {}
    report = build(groups, decisions, evidence_map(Path(args.candidates)), evidence_map(Path(args.telegram)))
    Path(args.json_output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.html_output).write_text(render(report), encoding="utf-8")
    print(f"Saved {args.json_output} and {args.html_output}")
    print(f"Groups: {report['summary']['groups']}; PDFs: {report['summary']['documents']}")
    print("Database, PDFs, and manual decisions unchanged.")

if __name__ == "__main__":
    main()
