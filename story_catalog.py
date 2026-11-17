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
    """Extract labeled synopses or introductory prose preceding Telegram metadata."""
    if not text:
        return ""
    lines = text.splitlines()
    metadata_heading = re.compile(
        r"^[^\\w\\r\\n]{0,16}\\s*(?:t[ií]tulo|nombre|obra|autor(?:es)?|author|origen|estado|"
        r"cap[ií]tulos?|vol[uú]men(?:es)?|g[eé]nero(?:s)?|fansubs|ilustraciones|"
        r"otras obras del autor|descarga|enlaces?)\\s*[:：]",
        re.I,
    )
    label = re.compile(
        r"^\\s*(?:📖|📜|📝|📚)?\\s*(?:sinopsis|resumen|descripci[oó]n)\\s*[:：-]\\s*(.*)$",
        re.I,
    )
    # Explicitly labeled text takes priority, wherever it occurs.
    for index, line in enumerate(lines):
        match = label.match(line)
        if not match:
            continue
        parts = [match.group(1).strip()] if match.group(1).strip() else []
        for following in lines[index + 1:]:
            value = following.strip()
            if metadata_heading.match(value) or label.match(value) or (value.startswith("#") and parts):
                break
            if not value:
                if parts:
                    break
                continue
            parts.append(value)
        if parts:
            return " ".join(parts)[:1800]

    # Many posts start with unlabelled synopsis paragraphs before 🔰⊳Titulo.
    first_heading = next((i for i, line in enumerate(lines) if metadata_heading.match(line.strip())), None)
    if first_heading is None or first_heading == 0:
        return ""
    introduction = []
    for line in lines[:first_heading]:
        value = line.strip()
        if not value:
            if introduction:
                introduction.append("")
            continue
        if value.startswith("#") or value.startswith(("http://", "https://", "@")):
            return ""
        introduction.append(value)
    prose = "\\n".join(introduction).strip()
    # Avoid treating short announcements, tags or a standalone heading as a synopsis.
    if len(prose) < 65 or len(prose.split()) < 12:
        return ""
    return prose[:1800]


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
