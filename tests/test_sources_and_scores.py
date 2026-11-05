from types import SimpleNamespace

import pytest

from hermes_job_automation.collectors import all_collectors
from hermes_job_automation.collectors.saramin import parse_response
from hermes_job_automation.scoring import validate_evaluation


def test_other_platforms_are_manual_only_without_approved_api():
    settings = SimpleNamespace(
        saramin_api_approved=False,
        saramin_access_key="",
        saramin_location_codes="",
    )
    results = {collector.platform: collector.collect() for collector in all_collectors(settings)}

    assert results["사람인"].status == "approval_required"
    assert all(
        results[name].status == "manual_only"
        for name in ("잡코리아", "원티드", "점핏", "직행", "로켓펀치", "그룹바이")
    )


def test_saramin_response_parser_keeps_source_fields():
    parsed = parse_response(
        {
            "jobs": {
                "job": [
                    {
                        "id": "42",
                        "url": "https://example.invalid/jobs/42",
                        "company": {"detail": {"name": "검증회사"}},
                        "position": {
                            "title": "Java 백엔드 신입",
                            "location": "서울",
                            "job-type": "정규직",
                            "experience-level": "신입",
                            "required-education-level": "고졸 이상",
                            "expiration-date": "2026-11-30",
                            "job-description": "Spring Boot",
                        },
                    }
                ]
            }
        }
    )

    assert len(parsed) == 1
    assert parsed[0].platform_id == "42"
    assert parsed[0].company == "검증회사"
    assert parsed[0].education == "고졸 이상"


def test_evaluation_total_must_match_components():
    with pytest.raises(ValueError, match="Total score"):
        validate_evaluation(
            {
                "technical_fit": 30,
                "work_fit": 25,
                "project_fit": 20,
                "preferred_qualifications": 5,
                "total": 79,
                "eligibility": "eligible",
            }
        )
