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
