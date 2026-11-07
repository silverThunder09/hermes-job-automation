import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

from .config import Settings
from .collectors import all_collectors
from .form_dry_run import run_local_form_dry_run
from .finalize import finalize_review
from .runner import get_health, run_pipeline
from .state_checks import run_state_smoke, state_health


APPROVAL_PHRASE = "I explicitly approve real application submission for this platform and posting scope."


def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _approve(settings: Settings, args) -> int:
    if not sys.stdin.isatty():
        raise RuntimeError("Approval creation requires an interactive terminal.")
    print("Platform: {}".format(args.platform))
    print("Posting ID: {}".format(args.posting_id))
    print("Domain: {}".format(args.domain))
    print("Maximum score: {}".format(args.max_score))
    print("Conditions: {}".format(args.conditions))
    typed = input("Type the following exact sentence to authorize this scope:\n{}\n> ".format(APPROVAL_PHRASE))
    if typed.strip() != APPROVAL_PHRASE:
        raise RuntimeError("Approval phrase did not match.")
    settings.submission_approval_file.parent.mkdir(parents=True, exist_ok=True)
    current = []
    if settings.submission_approval_file.exists():
        current = json.loads(settings.submission_approval_file.read_text(encoding="utf-8"))
    current = [
        item
        for item in current
        if not (
            item.get("platform") == args.platform
            and args.posting_id in item.get("posting_ids", [])
        )
    ]
    current.append(
        {
            "platform": args.platform,
            "posting_ids": [args.posting_id],
            "domains": [args.domain.lower()],
            "max_score": args.max_score,
            "valid_until": (datetime.now().astimezone() + timedelta(hours=args.valid_hours)).isoformat(),
            "approved_at": datetime.now().astimezone().isoformat(),
            "conditions": args.conditions,
            "enabled": True,
        }
    )
    settings.submission_approval_file.write_text(
        json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Approval scope saved locally. AUTO_SUBMIT remains disabled until explicitly enabled.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="job-assist")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("health")
    commands.add_parser("state-health", help="Read-only Supabase schema and private-bucket check.")
    smoke = commands.add_parser("state-smoke", help="Retain a unique public storage sample; never upload or submit.")
    smoke.add_argument("--explicit-write", action="store_true", help="Explicitly authorize retaining a new storage sample.")
    smoke.add_argument("--file", help="Optional public-only JSON posting (company/title/url, optional platform/platform_id).")
    commands.add_parser("sources")
    ocr = commands.add_parser("ocr-image", help="Extract a local image with review-required Windows OCR.")
    ocr.add_argument("--file", required=True)
    ocr.add_argument("--language", default="ko")
    ocr.add_argument("--output", help="New UTF-8 JSON output file; existing files are never overwritten.")
    run = commands.add_parser("run")
    run.add_argument("--manual-file", action="append", default=[])
    run.add_argument("--execute", action="store_true", help="Allow configured Google/Telegram writes.")
    run.add_argument("--collect-only", action="store_true", help="Prepare source-verified postings for Hermes review.")
    finalize = commands.add_parser("finalize")
    finalize.add_argument("--file", required=True)
    finalize.add_argument("--execute", action="store_true", help="Write configured Google Workspace/Telegram outputs.")
    dry = commands.add_parser("form-dry-run")
    dry.set_defaults(command="form-dry-run")
    approval = commands.add_parser("approve-posting")
    approval.add_argument("--platform", required=True)
    approval.add_argument("--posting-id", required=True)
    approval.add_argument("--domain", required=True)
    approval.add_argument("--max-score", type=int, default=100)
    approval.add_argument("--valid-hours", type=int, default=24)
    approval.add_argument("--conditions", required=True)
    args = parser.parse_args(argv)
    if args.command == "state-smoke" and not args.explicit_write:
        parser.error("state-smoke requires --explicit-write; the public sample will be retained, not deleted.")

    try:
        settings = Settings.load()
        if args.command == "ocr-image":
            from .ocr import extract_image_text

            destination = Path(args.output).expanduser().resolve() if args.output else None
            if destination and destination.exists():
                raise FileExistsError("OCR output already exists; choose a new output path.")
            result = extract_image_text(Path(args.file), language=args.language)
            if destination:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("x", encoding="utf-8") as stream:
                    json.dump(result, stream, ensure_ascii=False, indent=2)
                _print({
                    "status": "extracted_requires_review",
                    "output": str(destination),
                    "engine": result["engine"],
                    "requires_review": True,
                    "text_characters": len(result["text"]),
                })
            else:
                _print(result)
        elif args.command == "health":
            _print(get_health(settings))
        elif args.command == "state-health":
            result = state_health(settings)
            _print(result)
            return 0 if result["status"] == "ready" else 1
        elif args.command == "state-smoke":
            _print(run_state_smoke(settings, explicit_write=args.explicit_write,
                                   sample_file=Path(args.file).expanduser().resolve() if args.file else None))
        elif args.command == "sources":
            statuses = []
            for collector in all_collectors(settings):
                result = collector.collect()
                statuses.append(
                    {
                        "platform": collector.platform,
                        "result": result.status,
                        "message": result.message,
                    }
                )
            _print(statuses)
        elif args.command == "run":
            files = [Path(value).expanduser().resolve() for value in args.manual_file]
            _print(
                run_pipeline(
                    settings,
                    manual_files=files,
                    dry_run=not args.execute,
                    notify=args.execute,
                    collect_only=args.collect_only,
                )
            )
        elif args.command == "finalize":
            _print(
                finalize_review(
                    settings,
                    Path(args.file).expanduser().resolve(),
                    execute=args.execute,
                )
            )
        elif args.command == "form-dry-run":
            _print(run_local_form_dry_run())
        elif args.command == "approve-posting":
            return _approve(settings, args)
    except Exception as exc:
        print(json.dumps({"status": "error", "error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
