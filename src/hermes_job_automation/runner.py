import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from zoneinfo import ZoneInfo

from .collectors import all_collectors
from .config import Settings
from .documents import create_application_documents
from .eligibility import check_eligibility
from .locking import ProcessLock
from .manual_import import load_manual_postings
from .models import Evaluation, Posting
from .notifications import send_telegram
from .scoring import OpenAIScorer
from .state import create_state_store, posting_key
from .workspace import GoogleWorkspace
from .writing import OpenAIWriter


def _now(settings: Settings) -> datetime:
    return datetime.now(ZoneInfo(settings.timezone))


def _load_profile(settings: Settings) -> Dict[str, Any]:
    profile_path = settings.project_root / "profile.json"
    if not profile_path.exists():
        profile_path = settings.project_root / "profile.example.json"
    return json.loads(profile_path.read_text(encoding="utf-8"))


def _setup_logging(settings: Settings) -> None:
    settings.ensure_directories()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(settings.log_dir / "job-assistant.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def _manual_result(files: Sequence[Path]) -> tuple:
    postings = []
    results = []
    for path in files:
        try:
            rows = load_manual_postings(path)
            postings.extend(rows)
            results.append(
                {
                    "platform": "manual-import",
                    "status": "success",
                    "count": len(rows),
                    "file": path.name,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "platform": "manual-import",
                    "status": "error",
                    "file": path.name,
                    "error": type(exc).__name__,
                }
            )
    return postings, results


def run_pipeline(
    settings: Settings,
    manual_files: Optional[Sequence[Path]] = None,
    dry_run: bool = True,
    notify: bool = True,
    collect_only: bool = False,
) -> Dict[str, Any]:
    _setup_logging(settings)
    log = logging.getLogger("job_assistant")
    lock_path = settings.data_dir / "run.lock"
    with ProcessLock(lock_path):
        store = create_state_store(settings)
        run_id = str(uuid.uuid4())
        started = _now(settings)
        store.create_run(run_id, started.isoformat())
        log.info("Run started: %s; dry_run=%s", run_id, dry_run)

        collected: List[Posting] = []
        source_results = []
        for collector in all_collectors(settings):
            try:
                result = collector.collect()
                collected.extend(result.postings)
                source_results.append(
                    {
                        "platform": result.platform,
                        "status": result.status,
                        "count": len(result.postings),
                        "message": result.message,
                        "error": result.error,
                    }
                )
            except Exception as exc:
                source_results.append(
                    {
                        "platform": getattr(collector, "platform", "unknown"),
                        "status": "error",
                        "count": 0,
                        "error": type(exc).__name__,
                    }
                )
                log.exception("Source failed: %s", getattr(collector, "platform", "unknown"))

        manual_postings, manual_results = _manual_result(manual_files or [])
        collected.extend(manual_postings)
        source_results.extend(manual_results)

        new_postings = []
        eligibility_by_key = {}
        for posting in collected:
            eligibility = check_eligibility(posting, now=started)
            eligibility_by_key[posting_key(posting)] = eligibility
            if store.save_posting(posting, eligibility.to_dict()):
                new_postings.append(posting)

        profile = _load_profile(settings)
        # Contact details are not needed for fit scoring and must not leave the
        # local workspace in Hermes review JSON, run reports, or model prompts.
        scoring_profile = {
            key: value
            for key, value in profile.items()
            if key.lower() not in {"contact", "email", "phone", "name"}
        }
        evaluated = []
        unscored = []
        scored_entries = []
        review_queue = [
            {
                "posting_key": posting_key(posting),
                "posting": posting.to_dict(),
                "eligibility": eligibility_by_key[posting_key(posting)].to_dict(),
                "reason": "HERMES_REVIEW_REQUIRED",
            }
            for posting in new_postings
            if eligibility_by_key[posting_key(posting)].status in {"eligible", "review"}
        ]
        if collect_only:
            unscored = [
                {"posting_key": entry["posting_key"], "reason": entry["reason"]}
                for entry in review_queue
            ]
        elif settings.openai_api_key and settings.openai_model:
            scorer = OpenAIScorer(settings)
            writer = OpenAIWriter(settings)
            for posting in new_postings:
                eligibility = eligibility_by_key[posting_key(posting)]
                if eligibility.status != "eligible":
                    continue
                try:
                    evaluation = scorer.evaluate(posting, scoring_profile)
                    store.save_evaluation(posting, evaluation.to_dict())
                    evaluated.append((posting, evaluation))
                    scored_entries.append(
                        {"posting": posting.to_dict(), "evaluation": evaluation.to_dict()}
                    )
                    if evaluation.eligibility != "eligible" or evaluation.total < settings.minimum_score:
                        continue
                    draft = writer.draft(posting, scoring_profile)
                    docs = create_application_documents(
                        settings.project_root / "generated",
                        posting,
                        draft["resume"],
                        draft["cover_letter"],
                    )
                    uploaded = []
                    if not dry_run and settings.google_drive_parent_id:
                        workspace = GoogleWorkspace(settings)
                        uploaded = [
                            workspace.upload_document(posting.company, path) for path in docs
                        ]
                    scored_entries[-1]["documents"] = [str(path) for path in docs]
                    scored_entries[-1]["drive_links"] = uploaded
                except Exception as exc:
                    log.exception("Evaluation or document generation failed for %s", posting.url)
                    unscored.append(
                        {"posting": posting.to_dict(), "reason": type(exc).__name__}
                    )
        else:
            unscored = [
                {
                    "posting_key": posting_key(posting),
                    "reason": "GPT_CONFIGURATION_MISSING",
                }
                for posting in new_postings
                if eligibility_by_key[posting_key(posting)].status == "eligible"
            ]

        sheet_result = {"status": "dry_run" if dry_run else "skipped"}
        if not dry_run and settings.google_sheet_id and evaluated:
            try:
                sheet_result = {
                    "status": "written",
                    **GoogleWorkspace(settings).append_postings(
                        evaluated, started.date().isoformat()
                    ),
                }
            except Exception as exc:
                sheet_result = {"status": "error", "reason": type(exc).__name__}
                log.exception("Google Sheets update failed")
        elif not dry_run and not settings.google_sheet_id:
            sheet_result = {"status": "skipped", "reason": "GOOGLE_SHEET_ID_MISSING"}

        eligible_count = sum(
            1 for value in eligibility_by_key.values() if value.status == "eligible"
        )
        excluded_count = sum(
            1 for value in eligibility_by_key.values() if value.status == "excluded"
        )
        review_count = sum(
            1 for value in eligibility_by_key.values() if value.status == "review"
        )
        report = {
            "run_id": run_id,
            "started_at": started.isoformat(),
            "finished_at": _now(settings).isoformat(),
            "dry_run": dry_run,
            "sources": source_results,
            "collected": len(collected),
            "new": len(new_postings),
            "eligible": eligible_count,
            "excluded": excluded_count,
            "review": review_count,
            "evaluated": len(evaluated),
            "unscored": unscored,
            "sheet": sheet_result,
        }
        report_dir = settings.data_dir / "runs"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "{}.json".format(started.strftime("%Y-%m-%d-%H%M%S"))
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if collect_only:
            review_path = settings.data_dir / "to-review.json"
            review_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "started_at": started.isoformat(),
                        "profile": scoring_profile,
                        "postings": review_queue,
                        "excluded_count": excluded_count,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        store.finish_run(
            run_id,
            report["finished_at"],
            "completed_with_gaps" if unscored else "completed",
            report,
        )
        if notify and not dry_run:
            message = (
                "채용공고 작업 완료\n"
                "수집 {} · 신규 {} · 조건 통과 {} · 제외 {} · 확인 필요 {}\n"
                "평가 {} · 미평가 {} · 시트 {}".format(
                    report["collected"],
                    report["new"],
                    report["eligible"],
                    report["excluded"],
                    report["review"],
                    report["evaluated"],
                    len(unscored),
                    sheet_result["status"],
                )
            )
            report["telegram"] = send_telegram(settings, message)
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        log.info("Run finished: %s", report["finished_at"])
        return report


def get_health(settings: Settings) -> Dict[str, Any]:
    import importlib.util
    import os
    import shutil

    from .state_checks import state_health

    state_status = state_health(settings)
    hermes = shutil.which("hermes")
    if not hermes:
        candidates = []
        configured_home = os.getenv("HERMES_HOME", "").strip()
        if configured_home:
            candidates.extend(
                [Path(configured_home) / "bin" / "hermes.exe", Path(configured_home) / "bin" / "hermes"]
            )
        candidates.extend(
            [
                Path(r"D:\HermesRuntime\home\bin\hermes.exe"),
                settings.project_root / "work" / "runtime" / "hermes" / "home" / "bin" / "hermes.exe",
            ]
        )
        hermes = next((str(candidate) for candidate in candidates if candidate.is_file()), None)
    return {
        "status": "ready_with_configuration_gaps",
        "python": __import__("sys").version.split()[0],
        "hermes": hermes or "not_found",
        "playwright": bool(importlib.util.find_spec("playwright")),
        "configuration": settings.public_status(),
        "state": state_status,
        "next_run_schedule": None,
        "schedule_status": "not_verified",
    }
