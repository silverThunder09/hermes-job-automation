import pytest

from hermes_job_automation.eligibility import check_eligibility


def test_eligible_entry_level_job(posting, now):
    result = check_eligibility(posting(), now)

    assert result.status == "eligible"


def test_hard_excludes_mandatory_degree(posting, now):
    result = check_eligibility(posting(education="대졸 이상"), now)

    assert result.status == "excluded"
    assert any("학력 필수" in reason for reason in result.reasons)


def test_hard_excludes_degree_requirement_in_description(posting, now):
    result = check_eligibility(
        posting(education="학력무관", requirements="Java 개발자, 학사 이상 필수"),
        now,
    )

    assert result.status == "excluded"


def test_hard_excludes_closed_posting(posting, now):
    result = check_eligibility(posting(deadline="마감"), now)

    assert result.status == "excluded"


def test_missing_deadline_or_education_requires_review(posting, now):
    result = check_eligibility(posting(deadline=None, education=None), now)

    assert result.status == "review"
    assert "접수 마감일" in result.missing_information
    assert "학력 조건의 최소 기준" in result.missing_information


def test_mandatory_paid_backend_experience_is_excluded(posting, now):
    result = check_eligibility(
        posting(experience="백엔드 경력 2년 이상 필수", title="Java 백엔드 개발자"),
        now,
    )

    assert result.status == "excluded"
    assert any("유급 백엔드 경력" in reason for reason in result.reasons)


@pytest.mark.parametrize("deadline", ["채용시마감", "채용시 마감", "채용 시 마감"])
def test_until_hired_expression_does_not_mean_closed(posting, now, deadline):
    result = check_eligibility(posting(deadline=deadline), now)

    assert result.status == "eligible"


@pytest.mark.parametrize("deadline", ["접수 마감일: 2026-11-30", "마감일자 2026년 11월 30일"])
def test_deadline_date_label_is_not_a_closed_status(posting, now, deadline):
    result = check_eligibility(posting(deadline=deadline), now)

    assert result.status == "eligible"


@pytest.mark.parametrize(
    "deadline",
    [
        "12/28",
        "~12/28(월) 채용시 마감",
        "2026-02-30 채용시 마감",
        "2026-11-01 ~ 2026-11-30 채용시 마감",
        "2026년 11월 1일 ~ 2026-11-30",
        "2026-11-300",
        "12026-11-30",
    ],
)
def test_ambiguous_or_malformed_deadline_requires_review(posting, now, deadline):
    result = check_eligibility(posting(deadline=deadline), now)

    assert result.status == "review"
    assert "접수 마감일" in result.missing_information
    assert "접수 마감 또는 종료 표시" not in result.reasons


@pytest.mark.parametrize("full_date", ["2026-11-01", "2026년 11월 10일"])
@pytest.mark.parametrize("partial_date", ["11/30", "11월 30일"])
@pytest.mark.parametrize("reverse", [False, True])
def test_mixed_full_and_yearless_dates_require_review(
    posting, now, full_date, partial_date, reverse
):
    start, end = (partial_date, full_date) if reverse else (full_date, partial_date)
    result = check_eligibility(posting(deadline=f"{start} ~ {end} 채용시 마감"), now)

    assert result.status == "review"
    assert "접수 마감일" in result.missing_information
    assert "접수 마감 또는 종료 표시" not in result.reasons


@pytest.mark.parametrize(
    "deadline",
    ["상시", "상시채용", "상시 모집", "채용시", "채용 시", "채용시까지"],
)
def test_clear_open_ended_deadlines_remain_eligible(posting, now, deadline):
    assert check_eligibility(posting(deadline=deadline), now).status == "eligible"


@pytest.mark.parametrize(
    "deadline",
    [
        "마감",
        "접수 종료",
        "CLOSED",
        "상시채용 (접수 종료)",
        "채용시 마감 (모집 마감)",
        "2026-11-30 (접수 종료)",
    ],
)
def test_explicit_closed_status_overrides_rolling_or_future_date(posting, now, deadline):
    result = check_eligibility(posting(deadline=deadline), now)

    assert result.status == "excluded"
    assert "접수 마감 또는 종료 표시" in result.reasons


@pytest.mark.parametrize(
    ("deadline", "status"),
    [
        ("2026-11-02", "excluded"),
        ("2026-11-03", "eligible"),
        ("2026-11-30", "eligible"),
        ("2026-11-02 채용시 마감", "excluded"),
        ("2026-11-30 채용시 마감", "eligible"),
        ("2026.11.30", "eligible"),
        ("2026/11/30", "eligible"),
        ("2026-11-30 (2026년 11월 30일)", "eligible"),
    ],
)
def test_unambiguous_date_bounds_are_respected(posting, now, deadline, status):
    assert check_eligibility(posting(deadline=deadline), now).status == status


@pytest.mark.parametrize("deadline", [None, "", "미정", "채용시 추후 안내", "2026-02-30"])
def test_unknown_deadline_does_not_silently_become_eligible(posting, now, deadline):
    result = check_eligibility(posting(deadline=deadline), now)

    assert result.status == "review"
    assert "접수 마감일" in result.missing_information


def test_rolling_deadline_preserves_degree_and_experience_exclusions(posting, now):
    result = check_eligibility(
        posting(deadline="~12/28(월) 채용시 마감", education="대졸이상", experience="경력5년↑"),
        now,
    )

    assert result.status == "excluded"
    assert any("학력 필수" in reason for reason in result.reasons)
    assert any("유급 백엔드 경력" in reason for reason in result.reasons)
    assert "접수 마감 또는 종료 표시" not in result.reasons
    assert "접수 마감일" in result.missing_information


@pytest.mark.parametrize(
    ("deadline", "status"),
    [
        ("2026-11-30 마감 예정", "eligible"),
        ("2026-11-30 접수 종료 예정", "eligible"),
        ("상시채용 (조기마감 가능)", "review"),
    ],
)
def test_possible_future_closure_is_not_completed_recruitment(posting, now, deadline, status):
    result = check_eligibility(posting(deadline=deadline), now)

    assert result.status == status
    assert "접수 마감 또는 종료 표시" not in result.reasons
