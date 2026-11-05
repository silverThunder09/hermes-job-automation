import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, Iterable, List, Optional

from .base import CollectionResult, Collector
from ..models import Posting


SEARCH_URL = "https://oapi.saramin.co.kr/job-search"
KEYWORDS = ("Java", "Spring", "Spring Boot", "백엔드", "AI")


def _plain(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("name", "text", "value", "content", "title"):
            if key in value:
                return _plain(value[key])
        return ""
    if isinstance(value, list):
        return " ".join(filter(None, (_plain(item) for item in value)))
    if value is None:
        return ""
    return html.unescape(re.sub(r"<[^>]+>", " ", str(value))).strip()


def _as_list(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _deadline(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        timestamp = value.get("timestamp") or value.get("time")
        if timestamp:
            try:
                return datetime.fromtimestamp(
                    int(timestamp), timezone.utc
                ).astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()
            except (TypeError, ValueError, OSError):
                pass
    text = _plain(value)
    return text or None


def parse_response(payload: Dict[str, Any]) -> List[Posting]:
    root = payload.get("jobs", payload)
    if isinstance(root, dict):
        raw_jobs = root.get("job", root.get("jobs", []))
    else:
        raw_jobs = root
    postings = []
    for item in _as_list(raw_jobs):
        position = item.get("position", {}) or {}
        company = item.get("company", {}) or {}
        company_detail = company.get("detail", {}) if isinstance(company, dict) else {}
        location = position.get("location", {}) if isinstance(position, dict) else {}
        job_type = position.get("job-type", {}) if isinstance(position, dict) else {}
        experience = position.get("experience-level", {}) if isinstance(position, dict) else {}
        education = position.get("required-education-level", {}) if isinstance(position, dict) else {}
        expiration = position.get("expiration-date", {}) if isinstance(position, dict) else {}
        identifier = item.get("id") or item.get("rec_idx")
        url = item.get("url") or item.get("original-url")
        title = _plain(position.get("title") or item.get("title"))
        company_name = _plain(company_detail.get("name") or company.get("name"))
        if not url or not title or not company_name:
            continue
        description = position.get("job-description") or position.get("description") or ""
        postings.append(
            Posting(
                platform="사람인",
                platform_id=str(identifier) if identifier else None,
                title=title,
                company=company_name,
                url=str(url),
                deadline=_deadline(expiration),
                location=_plain(location),
                experience=_plain(experience),
                education=_plain(education),
                employment_type=_plain(job_type),
                skills=[],
                requirements=_plain(description),
                source_kind="saramin_approved_api",
            )
        )
    return postings


class SaraminCollector(Collector):
    platform = "사람인"

    def __init__(self, settings, opener=urllib.request.urlopen):
        self.settings = settings
        self.opener = opener

    def collect(self) -> CollectionResult:
        if not self.settings.saramin_api_approved:
            return CollectionResult(
                platform=self.platform,
                status="approval_required",
                message="공식 API 이용 승인을 확인한 뒤 SARAMIN_API_APPROVED=true로 설정해야 합니다.",
            )
        if not self.settings.saramin_access_key:
            return CollectionResult(
                platform=self.platform,
                status="credential_missing",
                message="공식 발급 access-key가 필요합니다.",
            )
        postings = []
        errors = []
        for keyword in KEYWORDS:
            params = {
                "access-key": self.settings.saramin_access_key,
                "keywords": keyword,
                "count": "110",
                "sort": "pd",
                "fields": "posting-date,expiration-date",
            }
            if self.settings.saramin_location_codes:
                params["loc_cd"] = self.settings.saramin_location_codes
            request = urllib.request.Request(
                SEARCH_URL + "?" + urllib.parse.urlencode(params),
                headers={"Accept": "application/json", "User-Agent": "HermesJobAssist/0.1"},
            )
            try:
                with self.opener(request, timeout=20) as response:
                    body = response.read()
                postings.extend(parse_response(json.loads(body.decode("utf-8"))))
            except (urllib.error.URLError, TimeoutError, ValueError, UnicodeDecodeError) as exc:
                errors.append("{}: {}".format(keyword, type(exc).__name__))
        if errors and not postings:
            return CollectionResult(
                platform=self.platform,
                status="error",
                message="공식 API 요청을 완료하지 못했습니다.",
                error="; ".join(errors),
            )
        return CollectionResult(
            platform=self.platform,
            status="partial" if errors else "success",
            postings=postings,
            message="공식 승인 API에서 {}건을 읽었습니다.".format(len(postings)),
            error="; ".join(errors) if errors else None,
        )
