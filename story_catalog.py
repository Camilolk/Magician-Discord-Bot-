"""Load metadata-based works for the Discord catalog (read-only)."""
import json
import unicodedata
import re
from pathlib import Path

PREVIEW_PATH = Path("story_preview.json")


def normalized(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", " ", value).strip()



def extract_synopsis(text):
    """Only use text explicitly labeled Sinopsis/Resumen in source metadata."""
    if not text:
        return ""
    lines = text.splitlines()
    start = None
    result = []
    for i, line in enumerate(lines):
        match = re.match(r"^\\s*(?:📖|📜|📝|📚)?\\s*(?:sinopsis|resumen|descripción|descripcion)\\s*[:：-]?\\s*(.*)$", line, re.I)
        if match:
            start = i
            if match.group(1).strip():
                result.append(match.group(1).strip())
            break
    if start is None:
        return ""
    for line in lines[start + 1:]:
        stripped = line.strip()
        if not stripped:
            if result:
                break
            continue
        if re.match(r"^[^\\w\\r\\n]{0,16}\\s*(?:t[ií]tulo|autor|origen|estado|vol[uú]men|g[eé]nero|fansubs|otras obras|descarga|enlaces?)\\s*[:：]", stripped, re.I):
            break
        if stripped.startswith("#") and result:
            break
        result.append(stripped)
    return " ".join(result).strip()[:1800]


def load_story_groups(path=PREVIEW_PATH):
    """Each Telegram metadata post stays separate; no unverified merging."""
    path = Path(path)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = []
    for work in data.get("works", []):
        title = (work.get("title") or "").strip()
        if not title or work.get("title_source") == "missing_needs_review":
            continue
        documents = work.get("documents") or []
        if not documents:
            continue
        items = []
        for doc in documents:
            name = (doc.get("filename") or "").strip()
            if name:
                # No Telegram deep links are synthesized for private channels.
                items.append((None, name, None))
        if items:
            groups.append({
                "name": title,
                "items": items,
                "author": (work.get("author") or "").strip(),
                "genres": (work.get("genres") or "").strip(),
                "status": (work.get("estado") or "").strip(),
                "synopsis": extract_synopsis(work.get("description_full") or work.get("description_excerpt") or ""),
                "metadata_message_id": work.get("message_id"),
                "provisional": True,
            })
    return sorted(groups, key=lambda g: (normalized(g["name"]), g["metadata_message_id"] or 0))
