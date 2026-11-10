import re
from datetime import date, datetime
from typing import Iterable, Optional, Tuple
from zoneinfo import ZoneInfo

from .models import Eligibility, Posting


ALLOWED_REGIONS = ("서울", "경기", "인천")
ALLOWED_EMPLOYMENT = ("정규직", "인턴")
DEGREE_REQUIREMENTS = (
    "대졸↑",
    "대졸 이상",
    "4년제 졸업",
    "대학교 졸업 이상",
    "학사 이상",
    "전문학사 이상",
    "초대졸↑",
    "대학(2,3년)↑",
    "대학교(2,3년)↑",
)
JUNIOR_WORDS = ("신입", "경력무관", "경력 무관", "경력무관(신입")
DATE_PATTERNS = (
    re.compile(r"(?<!\d)(20\d{2})[-./](\d{1,2})[-./](\d{1,2})(?!\d)"),
    re.compile(r"(?<!\d)(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일"),
)


def _text(posting: Posting) -> str:
    return " ".join(
        value or ""
        for value in (
            posting.title,
            posting.experience,
            posting.education,
            posting.employment_type,
            posting.location,
            posting.requirements,
        )
    ).lower()


def _is_open_ended_deadline(value: Optional[str]) -> bool:
    """Accept clear open-ended values; extra text or dates require separate review."""
    compact = re.sub(r"\s+", "", value or "").lower()
    return re.fullmatch(r"상시(?:채용|모집)?|채용시(?:마감|까지)?", compact) is not None


def _deadline_date(value: Optional[str]) -> Tuple[Optional[date], bool]:
    if not value:
        return None, False
    lowered = value.strip().lower()
    # These words describe a deadline, not completed recruitment. Parse the raw date below.
    status_text = re.sub(r"채용\s*시\s*마감", "", lowered)
    status_text = re.sub(r"(?:마감|종료)\s*일(?:자)?", "", status_text)
    status_text = re.sub(r"(?:조기\s*)?(?:마감|종료)\s*(?:예정|임박|가능)", "", status_text)
    if any(token in status_text for token in ("마감", "closed", "종료")):
        return None, True
    if _is_open_ended_deadline(value):
        return None, False
    dates = set()
    remaining = value
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(value):
            # A complete match must not be a slice of a longer numeric date token.
            if re.search(r"\d[-./]$", value[:match.start()]) or re.match(
                r"[-./]\d", value[match.end():]
            ):
                return None, False
            year, month, day = (int(part) for part in match.groups())
            try:
                dates.add(date(year, month, day))
            except ValueError:
                return None, False
        remaining = pattern.sub(" ", remaining)
    # Only standalone clock metadata may claim numbers outside complete dates.
    # Do not let a clock matcher consume components of a malformed date token.
    remaining = re.sub(
        r"(?<![\d./])(?<!\d-)(?:"
        r"\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[+-]\d{2}:\d{2})?"
        r"|\d{1,2}시(?:\s*\d{1,2}분)?(?:\s*\d{1,2}초)?"
        r")(?!\d|[-./]\d)",
        " ",
        remaining,
    )
    # Every number must belong to a complete date or recognized clock; otherwise
    # the field is unresolved, regardless of which side of a separator remains.
    if re.search(r"\d", remaining):
        return None, False
    if len(dates) == 1:
        return next(iter(dates)), False
    return None, False


def check_eligibility(
    posting: Posting,
    now: Optional[datetime] = None,
) -> Eligibility:
    reasons = []
    missing = []
    details = _text(posting)
    current = now or datetime.now(ZoneInfo("Asia/Seoul"))

    deadline, marked_closed = _deadline_date(posting.deadline)
    if marked_closed or (deadline and deadline < current.date()):
        reasons.append("접수 마감 또는 종료 표시")
    elif not posting.deadline or (
        deadline is None
        and not _is_open_ended_deadline(posting.deadline)
    ):
        missing.append("접수 마감일")

    if not posting.location:
        missing.append("근무 지역")
    elif not any(region in posting.location for region in ALLOWED_REGIONS):
        reasons.append("서울·경기·인천 외 근무지")

    if not posting.employment_type:
        missing.append("고용 형태")
    elif not any(kind in posting.employment_type for kind in ALLOWED_EMPLOYMENT):
        reasons.append("정규직 또는 인턴 채용으로 확인되지 않음")

    education_text = " ".join((posting.education or "", posting.requirements or "")).replace(" ", "")
    if any(marker.replace(" ", "") in education_text for marker in DEGREE_REQUIREMENTS):
        reasons.append("고졸 학력으로 충족할 수 없는 학력 필수 조건")
    elif not posting.education and not posting.requirements:
        missing.append("학력 조건")
    elif "학력무관" not in education_text and "고졸" not in education_text:
        missing.append("학력 조건의 최소 기준")

    experience_text = " ".join(
        (posting.experience or "", posting.requirements or "", posting.title or "")
    )
    required_years = re.search(
        r"(?:백엔드|개발|서버|backend).{0,30}(?:경력)?\s*(\d+)\s*년\s*(?:이상|↑|필수)",
        experience_text,
        re.IGNORECASE,
    )
    generic_years = re.search(
        r"경력\s*(\d+)\s*년\s*(?:이상|↑|필수)",
        experience_text,
        re.IGNORECASE,
    )
    years = [int(match.group(1)) for match in (required_years, generic_years) if match]
    if years and min(years) >= 1:
        reasons.append("유급 백엔드 경력 1년 이상 필수 조건")
    elif any(word in experience_text for word in JUNIOR_WORDS):
        pass
    elif not posting.experience:
        missing.append("필요 경력")
    else:
        missing.append("경력 최소 요건 확인")

    if reasons:
        return Eligibility(status="excluded", reasons=reasons, missing_information=missing)
    if missing:
        return Eligibility(status="review", missing_information=missing)
    return Eligibility(status="eligible", reasons=["명시된 필수 조건이 프로필 제약과 충돌하지 않음"])
