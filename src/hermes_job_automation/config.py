import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env", override=False)
    except ImportError:
        return


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    candidate = Path(raw) if raw else default
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    log_dir: Path
    timezone: str
    google_sheet_id: str
    google_sheet_tab: str
    google_drive_parent_id: str
    google_credentials: str
    google_oauth_client_secrets: str
    google_oauth_token_file: Path
    google_resume_doc_id: str
    saramin_api_approved: bool
    saramin_access_key: str
    saramin_location_codes: str
    openai_api_key: str
    openai_model: str
    minimum_score: int
    telegram_bot_token: str
    telegram_chat_id: str
    auto_submit: bool
    form_autofill_enabled: bool
    submission_approval_file: Path

    @classmethod
    def load(cls) -> "Settings":
        _load_dotenv()
        data_dir = _path("JOB_ASSIST_DATA_DIR", PROJECT_ROOT / "data")
        log_dir = _path("JOB_ASSIST_LOG_DIR", PROJECT_ROOT / "logs")
        return cls(
            project_root=PROJECT_ROOT,
            data_dir=data_dir,
            log_dir=log_dir,
            timezone=os.getenv("TZ", "Asia/Seoul"),
            google_sheet_id=os.getenv("GOOGLE_SHEET_ID", "").strip(),
            google_sheet_tab=os.getenv("GOOGLE_SHEET_TAB", "전체공고").strip(),
            google_drive_parent_id=os.getenv("GOOGLE_DRIVE_PARENT_ID", "").strip(),
            google_credentials=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip(),
            google_oauth_client_secrets=os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS", "").strip(),
            google_oauth_token_file=_path(
                "GOOGLE_OAUTH_TOKEN_FILE", data_dir / "google-token.json"
            ),
            google_resume_doc_id=os.getenv("GOOGLE_RESUME_DOC_ID", "").strip(),
            saramin_api_approved=_bool("SARAMIN_API_APPROVED"),
            saramin_access_key=os.getenv("SARAMIN_ACCESS_KEY", "").strip(),
            saramin_location_codes=os.getenv("SARAMIN_LOCATION_CODES", "").strip(),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_model=os.getenv("OPENAI_MODEL", "").strip(),
            minimum_score=int(os.getenv("MINIMUM_SCORE", "70")),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            auto_submit=_bool("AUTO_SUBMIT", False),
            form_autofill_enabled=_bool("FORM_AUTOFILL_ENABLED", False),
            submission_approval_file=_path(
                "SUBMISSION_APPROVAL_FILE", data_dir / "platform-submit-approvals.json"
            ),
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def public_status(self) -> dict:
        return {
            "timezone": self.timezone,
            "google_sheet_configured": bool(self.google_sheet_id),
            "google_credentials_configured": bool(
                self.google_credentials or self.google_oauth_client_secrets
            ),
            "resume_doc_configured": bool(self.google_resume_doc_id),
            "saramin_api_approved": self.saramin_api_approved,
            "saramin_key_configured": bool(self.saramin_access_key),
            "gpt_configured": bool(self.openai_api_key and self.openai_model),
            "telegram_configured": bool(self.telegram_bot_token and self.telegram_chat_id),
            "auto_submit": self.auto_submit,
            "form_autofill_enabled": self.form_autofill_enabled,
        }
