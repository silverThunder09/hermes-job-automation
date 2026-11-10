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


@pytest.mark.parametrize("full_date", ["2026-11-01", "2026-11-30"])
@pytest.mark.parametrize(
    "malformed_date",
    [
        "2026-11-300",
        "2026-111-30",
        "12026-11-300",
        "2026/11/300",
        "2026.11.300",
        "2026-11",
        "2026-11-",
        "2026-",
        "11/",
        "2026-02-30",
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_mixed_valid_and_malformed_numeric_dates_require_review(
    posting, now, full_date, malformed_date, reverse
):
    start, end = (malformed_date, full_date) if reverse else (full_date, malformed_date)
    result = check_eligibility(posting(deadline=f"{start} ~ {end} 채용시 마감"), now)

    assert result.status == "review"
    assert "접수 마감일" in result.missing_information
    assert "접수 마감 또는 종료 표시" not in result.reasons


@pytest.mark.parametrize(
    "full_date",
    ["2026-11-01", "2026-11-30", "2026년 11월 1일", "2026년 11월 30일"],
)
@pytest.mark.parametrize(
    "unresolved_date",
    [
        "2026년 11월 300일",
        "11월 300일",
        "2026년 110월 30일",
        "12026년 11월 30일",
        "2026년 11월 31일",
        "2026년 11월",
        "2026년",
        "11월",
        "30일",
        "2026년 11월 30",
        "2026년 11",
        "2026년 110월",
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_mixed_valid_and_unresolved_korean_dates_require_review(
    posting, now, full_date, unresolved_date, reverse
):
    start, end = (unresolved_date, full_date) if reverse else (full_date, unresolved_date)
    deadline = f"{start} ~ {end} 채용시 마감"
    job = posting(deadline=deadline)

    result = check_eligibility(job, now)

    assert result.status == "review"
    assert result.missing_information == ["접수 마감일"]
    assert result.reasons == []
    assert job.deadline == deadline


@pytest.mark.parametrize(
    "full_date",
    [
        "2026-11-01", "2026-11-30",
        "2026/11/01", "2026/11/30",
        "2026.11.01", "2026.11.30",
        "2026년 11월 1일", "2026년 11월 30일",
    ],
)
@pytest.mark.parametrize(
    "unresolved_date",
    [
        "11/01", "11.01", "11-01", "11월 1일",
        "2026-11-300", "2026/11/300", "2026.11.300", "2026년 11월 300일",
        "2026-110-30", "2026/110/30", "2026.110.30", "2026년 110월 30일",
        "12026-11-30", "12026/11/30", "12026.11.30", "12026년 11월 30일",
        "2026-11", "2026/11", "2026.11", "2026년 11월",
        "2026-", "2026/", "2026.", "2026년",
        "11-", "11/", "11.", "11월",
        "2026-02-30", "2026/02/30", "2026.02.30", "2026년 2월 30일",
    ],
)
@pytest.mark.parametrize("label", ["마감일:", "마감일: "])
@pytest.mark.parametrize("reverse", [False, True])
def test_date_label_colon_does_not_hide_unresolved_dates(
    posting, now, full_date, unresolved_date, label, reverse
):
    labeled_date = label + unresolved_date
    start, end = (labeled_date, full_date) if reverse else (full_date, labeled_date)
    deadline = f"{start} ~ {end} 채용시 마감"
    job = posting(deadline=deadline)

    result = check_eligibility(job, now)

    assert result.status == "review"
    assert result.missing_information == ["접수 마감일"]
    assert result.reasons == []
    assert job.deadline == deadline


@pytest.mark.parametrize(
    "full_date",
    ["2026-11-01", "2026-11-30", "2026/11/30", "2026.11.30", "2026년 11월 30일"],
)
@pytest.mark.parametrize("suffix", ["/1", "-1", ".1", "/1:11", "/2026-11-30", "1"])
def test_date_prefix_cannot_hide_extra_numeric_components(posting, now, full_date, suffix):
    deadline = full_date + suffix
    result = check_eligibility(posting(deadline=deadline), now)

    assert result.status == "review"
    assert result.missing_information == ["접수 마감일"]
    assert result.reasons == []


@pytest.mark.parametrize("prefix", ["1/", "1-", "1.", "11:00/"])
@pytest.mark.parametrize("full_date", ["2026-11-30", "2026년 11월 30일"])
def test_date_suffix_cannot_hide_extra_numeric_components(posting, now, prefix, full_date):
    result = check_eligibility(posting(deadline=prefix + full_date), now)

    assert result.status == "review"
    assert result.missing_information == ["접수 마감일"]


@pytest.mark.parametrize("partial_date", ["1/11:00", "1.11:00", "1-11:00", "1:11/30"])
@pytest.mark.parametrize("reverse", [False, True])
def test_clock_mask_cannot_consume_part_of_an_unresolved_date(posting, now, partial_date, reverse):
    parts = ["2026-11-30", partial_date]
    if reverse:
        parts.reverse()
    result = check_eligibility(posting(deadline=" ~ ".join(parts)), now)

    assert result.status == "review"
    assert result.missing_information == ["접수 마감일"]


@pytest.mark.parametrize(
    ("full_date", "status"),
    [("2026-11-01", "excluded"), ("2026-11-30", "eligible")],
)
@pytest.mark.parametrize(
    "time_suffix",
    [
        " 18:00",
        "T18:00:00",
        " 23:59:59.999",
        "T23:59:59.123456+09:00",
        " 18시 00분",
        " 18:00 채용시 마감",
    ],
)
def test_single_date_with_time_preserves_date_status(
    posting, now, full_date, status, time_suffix
):
    result = check_eligibility(posting(deadline=full_date + time_suffix), now)

    assert result.status == status
    assert "접수 마감일" not in result.missing_information


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
