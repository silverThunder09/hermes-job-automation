import json
from pathlib import Path
from typing import List

from .models import Posting


def load_manual_postings(path: Path) -> List[Posting]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("postings", [])
    postings = []
    for row in rows:
        item = dict(row)
        item.setdefault("source_kind", "user_reviewed_manual")
        posting = Posting.from_dict(item)
        if not posting.platform or not posting.url or not posting.title or not posting.company:
            raise ValueError("Each manual posting needs platform, company, title, and url.")
        if posting.source_kind != "user_reviewed_manual":
            raise ValueError("Manual import requires source_kind=user_reviewed_manual.")
        postings.append(posting)
    return postings
