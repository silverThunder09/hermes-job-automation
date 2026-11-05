import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .config import Settings
from .documents import create_application_documents
from .eligibility import check_eligibility
from .models import Evaluation, Posting
from .notifications import send_telegram
from .scoring import validate_evaluation
from .state import StateStore
from .workspace import GoogleWorkspace


def finalize_review(settings: Settings, review_file: Path, execute: bool = False) -> Dict[str, Any]:
    payload = json.loads(review_file.read_text(encoding="utf-8"))
    entries = payload.get("evaluations", [])
    if not isinstance(entries, list):
        raise ValueError("evaluations must be a JSON array.")
    store = StateStore(settings.data_dir / "state.sqlite3")
    profile_path = settings.project_root / "profile.json"
    if not profile_path.exists():
        profile_path = settings.project_root / "profile.example.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    ready = []
    held = []
    generated = []
    for entry in entries:
        key = str(entry.get("posting_key", ""))
        raw_posting = store.get_posting(key)
        if not raw_posting:
            held.append({"posting_key": key, "reason": "posting_not_in_local_database"})
            continue
        posting = Posting.from_dict(raw_posting)
        eligibility = check_eligibility(posting)
        supplied = dict(entry.get("evaluation") or {})
        evaluation = validate_evaluation(supplied, model="Hermes-configured-model")
        if eligibility.status != "eligible":
            evaluation.eligibility = eligibility.status
            evaluation.gaps.extend(eligibility.missing_information)
            evaluation.gaps.extend(eligibility.reasons)
            store.save_evaluation(posting, evaluation.to_dict())
            held.append(
                {
                    "posting_key": key,
                    "reason": "fresh_hard_filter_" + eligibility.status,
                    "details": eligibility.to_dict(),
                }
            )
            continue
        store.save_evaluation(posting, evaluation.to_dict())
        ready.append((posting, evaluation))
        draft = entry.get("documents") or {}
        resume_text = str(draft.get("resume", ""))
        cover_letter_text = str(draft.get("cover_letter", ""))
        if evaluation.eligibility == "eligible" and evaluation.total >= settings.minimum_score:
            if resume_text and cover_letter_text:
                from .writing import validate_draft_numbers

                validate_draft_numbers(profile, posting, draft)
                paths = create_application_documents(
                    settings.project_root / "generated",
                    posting,
                    resume_text,
                    cover_letter_text,
                )
                generated.extend((posting.company, path) for path in paths)
            else:
                held.append({"posting_key": key, "reason": "application_documents_missing"})

    sheet_result = {"status": "not_written"}
    drive_links = []
    drive_result = {"status": "not_written"}
    if execute:
        if settings.google_sheet_id and ready:
            sheet_result = {
                "status": "written",
                **GoogleWorkspace(settings).append_postings(
                    ready, datetime.now().astimezone().date().isoformat()
                ),
            }
        elif not settings.google_sheet_id:
            sheet_result = {"status": "skipped", "reason": "GOOGLE_SHEET_ID_MISSING"}
        else:
            sheet_result = {"status": "no_rows"}
        if generated and settings.google_drive_parent_id:
            workspace = GoogleWorkspace(settings)
            for company, path in generated:
                drive_links.append(workspace.upload_document(company, path))
            drive_result = {"status": "uploaded", "count": len(drive_links)}
        elif generated:
            drive_result = {
                "status": "skipped",
                "reason": "GOOGLE_DRIVE_PARENT_ID_MISSING",
            }
        else:
            drive_result = {"status": "no_documents"}
    result = {
        "status": "completed",
        "evaluated": len(ready),
        "documents_generated": len(generated),
        "held": held,
        "sheet": sheet_result,
        "drive": drive_result,
        "drive_links": drive_links,
        "execute": execute,
    }
    if execute:
        result["telegram"] = send_telegram(
            settings,
            "채용공고 검토 완료\n점수 평가 {}건 · 지원 문서 {}개 · 확인 보류 {}건 · 시트 {}".format(
                len(ready), len(generated), len(held), sheet_result["status"]
            ),
        )
    return result
