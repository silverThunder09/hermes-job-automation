"""Synthetic data and scripted local HTTP only; never a live DB/persistence test."""
import importlib
import json
from datetime import datetime, timezone

import pytest


NOW = datetime(2026, 11, 15, 3, 0, tzinfo=timezone.utc)
STAMP = NOW.isoformat()


def api():
    return importlib.import_module("hermes_job_automation.cloud_collection")


def batch_data(**overrides):
    row = dict(platform="점핏", platform_id="123", title="Java 백엔드 신입 개발자",
               company="합성 계약회사", url="https://jumpit.saramin.co.kr/position/123",
               deadline="상시채용", location="서울", experience="신입", education="학력무관",
               employment_type="정규직", skills=["Java"], requirements="Java 백엔드 개발",
               collected_at=STAMP, source_kind="agent_researched_public")
    row.update(overrides)
    return dict(schema_version=1, source="jumpit_public_browser", collected_at=STAMP, postings=[row])


def input_file(tmp_path, data=None):
    path = tmp_path / "batch.json"
    path.write_text(json.dumps(data if data is not None else batch_data(), ensure_ascii=False), encoding="utf-8")
    return path


def test_load_valid_public_batch_preserves_posting_fields(tmp_path):
    source = batch_data()
    loaded = api().load_cloud_batch(input_file(tmp_path, source), now=NOW)
    assert [row.to_dict() for row in loaded] == source["postings"]
    assert loaded[0].source_kind == "agent_researched_public"


@pytest.mark.parametrize("change", [
    {"platform": "사람인"}, {"platform_id": " 123"}, {"platform_id": "123 "},
    {"platform_id": "１２３"}, {"platform_id": 123}, {"platform_id": "123x"},
    {"platform_id": "1" * 41}, {"platform_id": "123,456"},
    {"url": "https://jumpit.saramin.co.kr/position/124"},
    *[{"url": "https://jumpit.saramin.co.kr/position/123" + suffix}
      for suffix in ("?x=1", "#x", "/", "?", "#")],
    {"url": "https://jumpit.saramin.co.kr:443/position/123"},
    {"url": "https://u@jumpit.saramin.co.kr/position/123"},
    {"url": "http://jumpit.saramin.co.kr/position/123"},
    {"source_kind": "user_reviewed_manual"}, {"title": " "}, {"company": ""},
    {"title": "x" * 501}, {"company": "x" * 301}, {"requirements": "x" * 32001},
    {"requirements": {}}, {"requirements": "\ud800"}, {"requirements": "a\x00b"},
    {"skills": "Java"}, {"skills": [3]}, {"skills": ["x"] * 51},
    {"skills": ["x" * 101]}, {"skills": [""]}, {"education": None},
    {"education": "확인 필요"}, {"education": "대학교 졸업 이상"},
    {"requirements": "Java 백엔드 학사 이상 필수"}, {"deadline": None},
    {"deadline": "마감"}, {"deadline": "2026-11-14"}, {"location": "부산"},
    {"location": "서울 또는 부산"}, {"employment_type": "계약직"},
    {"employment_type": "정규직 또는 계약직"}, {"experience": "확인 필요"},
    {"experience": "백엔드 경력 3년 이상"}, {"collected_at": "2026-11-15T03:00:00"},
    {"collected_at": "2026-11-15T12:00:00+09:00"},
    {"collected_at": "2026-11-15T03:00:01+00:00"},
    {"evaluation": {}}, {"credentials": "synthetic-private-marker"}, {"commands": ["echo no"]},
    {"title": "JavaScript 프론트엔드 신입", "requirements": "JavaScript", "skills": ["JavaScript"]},
    {"title": "Spring 제조 생산 신입", "requirements": "스프링 제조", "skills": ["Spring"]},
    {"title": "백엔드 신입", "requirements": "JavaScript", "skills": ["JavaScript"]},
])
def test_load_rejects_untrusted_or_unqualified_rows(tmp_path, change):
    # ASCII escaping permits intentionally malformed Unicode to reach the parser.
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(batch_data(**change)), encoding="utf-8")
    with pytest.raises(ValueError, match="^Invalid cloud collection batch\\.$"):
        api().load_cloud_batch(path, now=NOW)


@pytest.mark.parametrize("raw", [
    '{"schema_version":1,"schema_version":1}',
    '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '[]', 'null',
    '{"postings":[{"title":"a","title":"b"}]}',
    '{', '\ufeff{}', ' ' * (256 * 1024 + 1),
], ids=["duplicate", "nan", "infinity", "negative_infinity", "list", "null",
        "nested_duplicate", "syntax", "bom", "oversize"])
def test_load_rejects_non_strict_or_oversized_json(tmp_path, raw):
    path = tmp_path / "raw.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match="^Invalid cloud collection batch\\.$"):
        api().load_cloud_batch(path, now=NOW)


@pytest.mark.parametrize("mutation", ["version", "source", "extra", "empty", "eleven", "duplicate",
                                     "old", "future", "naive", "nonutc", "bool_version", "missing_field"])
def test_load_validates_whole_envelope_before_returning(tmp_path, mutation):
    data = batch_data()
    if mutation == "version":
        data["schema_version"] = 2
    elif mutation == "bool_version":
        data["schema_version"] = True
    elif mutation == "source":
        data["source"] = "user_reviewed_manual"
    elif mutation == "extra":
        data["secret"] = "synthetic-private-marker"
    elif mutation == "empty":
        data["postings"] = []
    elif mutation == "eleven":
        data["postings"] *= 11
    elif mutation == "duplicate":
        data["postings"] *= 2
    elif mutation == "missing_field":
        del data["postings"][0]["education"]
    else:
        data["collected_at"] = {"old": "2026-11-14T02:59:59+00:00",
                                "future": "2026-11-15T03:00:01+00:00",
                                "naive": "2026-11-15T03:00:00",
                                "nonutc": "2026-11-15T12:00:00+09:00"}[mutation]
        data["postings"][0]["collected_at"] = data["collected_at"]
    with pytest.raises(ValueError, match="^Invalid cloud collection batch\\.$"):
        api().load_cloud_batch(input_file(tmp_path, data), now=NOW)


@pytest.mark.parametrize("changes", [
    {"platform_id": "00123", "url": "https://jumpit.saramin.co.kr/position/00123"},
    {"title": "Spring 백엔드 신입", "skills": ["Spring"], "requirements": "Spring 백엔드 개발"},
    {"experience": "유급 백엔드 경력 0년", "title": "Java 백엔드 개발자"},
])
def test_load_preserves_decimal_id_and_accepts_separate_backend_keywords(tmp_path, changes):
    source = batch_data(**changes)
    assert api().load_cloud_batch(input_file(tmp_path, source), now=NOW)[0].to_dict() == source["postings"][0]


REVIEW = {"status": "review", "reasons": ["agent-researched", "user-review-pending"], "missing_information": []}


def stored_row(payload=None, key="점핏:123", **changes):
    payload = payload or batch_data()["postings"][0]
    row = dict(posting_key=key, normalized_url=payload["url"], platform=payload["platform"],
               platform_id=payload["platform_id"], company=payload["company"], title=payload["title"],
               payload_json=payload, eligibility_json=REVIEW, first_seen_at=STAMP, last_seen_at=STAMP)
    row.update(changes)
    return row


def queue_snapshot(postgrest, row=None, evaluation=None, application=None, legacy=False):
    """A fixed response transcript, not an in-memory persistence implementation."""
    import copy
    rows = [row] if row else []
    postgrest.replies.extend(copy.deepcopy([(200, [] if legacy else rows, {}),
                                          (200, rows, {}), (200, rows, {})]))
    if row:
        postgrest.replies.extend(copy.deepcopy([(200, [evaluation] if evaluation else [], {}),
                                              (200, [application] if application else [], {})]))


@pytest.mark.parametrize("explicit,valid", [(False, True), (1, True), (True, False)])
def test_save_preflight_never_reads_settings_or_contacts_storage(tmp_path, postgrest, explicit, valid):
    touched = []

    class UnreadableSettings:
        def __getattribute__(self, name):
            touched.append(name)
            raise AssertionError("synthetic-private-marker")

    path = input_file(tmp_path, batch_data() if valid else batch_data(education=None))
    receipt = tmp_path / "receipt.json"
    with pytest.raises((ValueError, RuntimeError)) as error:
        api().save_cloud_batch(UnreadableSettings(), path, explicit_write=explicit, receipt_path=receipt, now=NOW)
    assert "synthetic-private-marker" not in str(error.value)
    assert touched == []
    assert postgrest.calls == []
    assert not receipt.exists()


def test_save_new_row_exact_readback_second_false_and_durable_attempts(tmp_path, postgrest, health_contract, state_settings):
    path = input_file(tmp_path)
    receipt_path = tmp_path / "receipt.json"
    health_contract()
    queue_snapshot(postgrest)

    def acknowledged(calls):
        journal = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert journal["status"] == "pending"
        assert journal["attempts"][-1]["status"] == "pending"
        assert len(journal["attempts"]) == len([c for c in calls if c[0] == "POST"])
        return 200, len(journal["attempts"]) == 1, {}

    postgrest.replies.append(acknowledged)
    queue_snapshot(postgrest, stored_row())
    postgrest.replies.append(acknowledged)
    queue_snapshot(postgrest, stored_row())
    receipt = api().save_cloud_batch(state_settings, path, explicit_write=True, receipt_path=receipt_path, now=NOW)
    assert receipt["status"] == "verified"
    assert receipt["rows"] == [{"key": "점핏:123", "outcome": "new", "duplicate_check": "verified"}]
    assert [(a["attempt"], a["status"], a["result"]) for a in receipt["attempts"]] == [(1, "reported", True), (2, "reported", False)]
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == receipt
    posts = [c for c in postgrest.calls if c[0] != "GET"]
    assert len(posts) == 2
    assert all(c[0] == "POST" and c[1] == "/rest/v1/rpc/job_assist_save_posting" for c in posts)
    assert posts[0][3]["p_payload"] == batch_data()["postings"][0]
    assert posts[0][3]["p_eligibility"] == REVIEW
    assert posts[1][3] == posts[0][3]
    from urllib.parse import parse_qs, urlsplit
    expected = stored_row()
    for method, path, _, _ in postgrest.calls:
        if method == "GET":
            query = parse_qs(urlsplit(path).query)
            for field in ("posting_key", "normalized_url", "platform", "platform_id"):
                if field in query:
                    assert query[field] == ["eq." + expected[field]]
    assert not postgrest.replies
    text = receipt_path.read_text(encoding="utf-8")
    assert all(value not in text for value in ["합성 계약회사", "Java", "sb_secret", "requirements", "notes"])


def preserved_state():
    payload = batch_data(title="기존 원문 제목", source_kind="user_reviewed_manual")["postings"][0]
    row = stored_row(payload, key="legacy:canonical", eligibility_json={"status": "excluded", "reasons": ["원본 유지"]},
                     first_seen_at="2026-11-01T00:00:00+00:00", last_seen_at="2026-11-01T00:00:00+00:00")
    evaluation = {"posting_key": row["posting_key"], "evaluation_json": {"total": 71, "rationale": ["원래 평가"]}, "updated_at": STAMP}
    application = {"posting_key": row["posting_key"], "status": "submitted", "notes": {"memo": "원래 메모"},
                   "attempt_id": "earlier", "submitted_at": STAMP, "confirmation_evidence": "원래 증빙", "updated_at": STAMP}
    return row, evaluation, application


def test_save_existing_canonical_duplicate_preserves_all_state(tmp_path, postgrest, health_contract, state_settings):
    row, evaluation, application = preserved_state()
    health_contract()
    queue_snapshot(postgrest, row, evaluation, application, legacy=True)
    for _ in range(2):
        postgrest.replies.append((200, False, {}))
        queue_snapshot(postgrest, dict(row, last_seen_at=STAMP), evaluation, application, legacy=True)
    receipt = api().save_cloud_batch(state_settings, input_file(tmp_path), explicit_write=True,
                                    receipt_path=tmp_path / "receipt.json", now=NOW)
    assert receipt["status"] == "verified"
    assert receipt["rows"] == [{"key": "점핏:123", "outcome": "existing_duplicate", "duplicate_check": "verified"}]
    assert [a["result"] for a in receipt["attempts"]] == [False, False]
    assert not postgrest.replies
    assert all(c[1] == "/rest/v1/rpc/job_assist_save_posting" for c in postgrest.calls if c[0] != "GET")


@pytest.mark.parametrize("field", ["payload_json", "eligibility_json", "company", "title", "first_seen_at",
                                   "last_seen_at", "evaluation", "application", "notes", "evaluation_time"])
def test_save_detects_changed_existing_state_without_second_write(tmp_path, postgrest, health_contract, state_settings, field):
    import copy
    row, evaluation, application = preserved_state()
    health_contract()
    queue_snapshot(postgrest, row, evaluation, application, legacy=True)
    postgrest.replies.append((200, False, {}))
    changed, ev, app = copy.deepcopy((dict(row, last_seen_at=STAMP), evaluation, application))
    if field == "evaluation":
        ev["evaluation_json"]["total"] = 99
    elif field == "evaluation_time":
        ev["updated_at"] = "2026-11-15T02:00:00+00:00"
    elif field == "application":
        app["status"] = "manual_review"
    elif field == "notes":
        app["notes"] = {}
    else:
        changed[field] = {} if field.endswith("json") else "wrong"
    queue_snapshot(postgrest, changed, ev, app, legacy=True)
    target = tmp_path / "receipt.json"
    with pytest.raises(RuntimeError, match="^Cloud collection save could not be verified; inspect the receipt\\.$"):
        api().save_cloud_batch(state_settings, input_file(tmp_path), explicit_write=True, receipt_path=target, now=NOW)
    receipt = json.loads(target.read_text(encoding="utf-8"))
    assert receipt["status"] == "unknown"
    assert len([c for c in postgrest.calls if c[0] == "POST"]) == 1


def test_save_race_with_exact_new_state_is_distinguished(tmp_path, postgrest, health_contract, state_settings):
    health_contract()
    queue_snapshot(postgrest)
    for _ in range(2):
        postgrest.replies.append((200, False, {}))
        queue_snapshot(postgrest, stored_row())
    receipt = api().save_cloud_batch(state_settings, input_file(tmp_path), explicit_write=True,
                                    receipt_path=tmp_path / "receipt.json", now=NOW)
    assert receipt["status"] == "verified"
    assert receipt["rows"][0]["outcome"] == "concurrent_duplicate"


@pytest.mark.parametrize("field", ["payload_json", "eligibility_json", "normalized_url", "first_seen_at", "evaluation", "application", "missing"])
def test_save_new_row_must_match_exact_expected_state(tmp_path, postgrest, health_contract, state_settings, field):
    health_contract()
    queue_snapshot(postgrest)
    postgrest.replies.append((200, True, {}))
    row = stored_row()
    ev = app = None
    if field == "missing":
        row = None
    elif field == "evaluation":
        ev = {"posting_key": "점핏:123", "evaluation_json": {}, "updated_at": STAMP}
    elif field == "application":
        app = {"posting_key": "점핏:123", "status": "collected", "notes": {}}
    else:
        row[field] = {} if field.endswith("json") else "wrong"
    queue_snapshot(postgrest, row, ev, app)
    target = tmp_path / "receipt.json"
    with pytest.raises(RuntimeError):
        api().save_cloud_batch(state_settings, input_file(tmp_path), explicit_write=True, receipt_path=target, now=NOW)
    assert json.loads(target.read_text(encoding="utf-8"))["status"] == "unknown"
    assert len([c for c in postgrest.calls if c[0] == "POST"]) == 1


def test_save_existing_receipt_is_not_overwritten_before_settings_access(tmp_path, postgrest):
    target = tmp_path / "receipt.json"
    target.write_text("preserve previous attempt", encoding="utf-8")
    with pytest.raises(RuntimeError, match="^Cloud collection receipt unavailable\\.$"):
        api().save_cloud_batch(None, input_file(tmp_path), explicit_write=True, receipt_path=target, now=NOW)
    assert target.read_text(encoding="utf-8") == "preserve previous attempt"
    assert not postgrest.calls


@pytest.mark.parametrize("stage,existing", [(1, False), (2, False), (1, True), (2, True)])
@pytest.mark.parametrize("reply", [(500, {"error": "synthetic-private-marker"}, {}),
                                   (200, "synthetic-private-marker", {}),
                                   (302, {}, {"Location": "https://do-not-follow.invalid"})], ids=["http", "shape", "redirect"])
def test_save_uncertain_ack_reconciles_exact_state_without_retry(tmp_path, postgrest, health_contract, state_settings, stage, existing, reply):
    health_contract()
    row, ev, app = preserved_state() if existing else (stored_row(), None, None)
    queue_snapshot(postgrest, row if existing else None, ev, app, legacy=existing)
    if stage == 2:
        postgrest.replies.append((200, not existing, {}))
        queue_snapshot(postgrest, dict(row, last_seen_at=STAMP), ev, app, legacy=existing)
    postgrest.replies.append(reply)
    queue_snapshot(postgrest, dict(row, last_seen_at=STAMP), ev, app, legacy=existing)
    target = tmp_path / "receipt.json"
    receipt = api().save_cloud_batch(state_settings, input_file(tmp_path), explicit_write=True, receipt_path=target, now=NOW)
    assert receipt["status"] == "reconciled"  # Never verified without both reported ACKs.
    assert receipt["attempts"][-1]["status"] == "reconciled"
    assert receipt["attempts"][-1]["result"] is None
    assert len([c for c in postgrest.calls if c[0] == "POST"]) == stage
    assert not postgrest.replies
    assert json.loads(target.read_text(encoding="utf-8")) == receipt
    assert "synthetic-private-marker" not in target.read_text(encoding="utf-8")
    with pytest.raises(RuntimeError, match="receipt unavailable"):
        api().save_cloud_batch(state_settings, input_file(tmp_path), explicit_write=True, receipt_path=target, now=NOW)
    assert len([c for c in postgrest.calls if c[0] == "POST"]) == stage


@pytest.mark.parametrize("stage", [1, 2])
@pytest.mark.parametrize("observation", ["absent", "corrupt", "read_failure"])
def test_save_uncertain_unverifiable_state_is_unknown(tmp_path, postgrest, health_contract, state_settings, stage, observation):
    health_contract()
    queue_snapshot(postgrest)
    if stage == 2:
        postgrest.replies.append((200, True, {}))
        queue_snapshot(postgrest, stored_row())
    postgrest.replies.append((500, {"message": "synthetic-private-marker"}, {}))
    if observation == "read_failure":
        postgrest.replies.append((500, {"message": "synthetic-private-marker"}, {}))
    else:
        queue_snapshot(postgrest, None if observation == "absent" else stored_row(company="corrupt"))
    target = tmp_path / "receipt.json"
    with pytest.raises(RuntimeError) as error:
        api().save_cloud_batch(state_settings, input_file(tmp_path), explicit_write=True, receipt_path=target, now=NOW)
    receipt = json.loads(target.read_text(encoding="utf-8"))
    assert receipt["status"] == "unknown"
    assert receipt["attempts"][-1]["status"] == "unknown"
    assert len([c for c in postgrest.calls if c[0] == "POST"]) == stage
    assert "synthetic-private-marker" not in str(error.value)
    assert error.value.__suppress_context__


def test_save_partial_success_survives_later_unknown(tmp_path, postgrest, health_contract, state_settings):
    data = batch_data()
    second = batch_data(platform_id="124", url="https://jumpit.saramin.co.kr/position/124")["postings"][0]
    data["postings"].append(second)
    health_contract()
    queue_snapshot(postgrest)
    queue_snapshot(postgrest)
    for result in (True, False):
        postgrest.replies.append((200, result, {}))
        queue_snapshot(postgrest, stored_row())
    postgrest.replies.append((500, {}, {}))
    queue_snapshot(postgrest)
    target = tmp_path / "receipt.json"
    with pytest.raises(RuntimeError):
        api().save_cloud_batch(state_settings, input_file(tmp_path, data), explicit_write=True, receipt_path=target, now=NOW)
    receipt = json.loads(target.read_text(encoding="utf-8"))
    assert receipt["status"] == "unknown"
    assert receipt["rows"][0] == {"key": "점핏:123", "outcome": "new", "duplicate_check": "verified"}
    assert len(receipt["attempts"]) == 3
    assert receipt["attempts"][-1]["key"] == "점핏:124"
    assert receipt["attempts"][-1]["status"] == "unknown"


def test_save_preflights_every_input_row_before_any_credentials(tmp_path, postgrest):
    data = batch_data()
    data["postings"].append(batch_data(platform_id="124", education=None)["postings"][0])
    target = tmp_path / "receipt.json"
    with pytest.raises(ValueError):
        api().save_cloud_batch(None, input_file(tmp_path, data), explicit_write=True, receipt_path=target, now=NOW)
    assert not target.exists()
    assert not postgrest.calls


@pytest.mark.parametrize("changes", [
    {"experience": "신입 여부 확인 필요"}, {"experience": "신입 불가"},
    {"experience": "경력무관 여부 미확인"},
    {"requirements": "Java 백엔드 모집 종료"},
    {"requirements": "Java 백엔드 계약직 채용"},
    {"requirements": "Java 백엔드 근무지: 제주"},
])
def test_load_rejects_explicitly_unknown_or_conflicting_evidence(tmp_path, changes):
    with pytest.raises(ValueError, match="^Invalid cloud collection batch\\.$"):
        api().load_cloud_batch(input_file(tmp_path, batch_data(**changes)), now=NOW)


@pytest.mark.parametrize("detail", [
    "Java 백엔드 개발. 신입 지원 불가, 경력자만 채용.",
    "Java 백엔드 개발. 신입은 지원할 수 없습니다.",
    "Java 백엔드 개발. 신입 채용 제외.",
    "Java 백엔드 개발. 경력직만 지원 가능.",
    "Java 백엔드 개발. 경력자 필수.",
])
def test_load_rejects_entry_level_header_conflicting_with_detail(tmp_path, detail):
    with pytest.raises(ValueError, match="^Invalid cloud collection batch\\.$"):
        api().load_cloud_batch(input_file(tmp_path, batch_data(requirements=detail)), now=NOW)


@pytest.mark.parametrize("location", ["경기 광주시", "경기도 광주시", "경기 광주", "경기도 광주시 태전동"])
def test_load_distinguishes_gwangju_city_within_gyeonggi(tmp_path, location):
    source = batch_data(location=location)
    assert api().load_cloud_batch(input_file(tmp_path, source), now=NOW)[0].location == location


@pytest.mark.parametrize("detail", ["Java 백엔드 개발. 경력자 우대.", "Java 백엔드 개발. 신입 지원 가능."])
def test_load_does_not_promote_experience_preferences_to_requirements(tmp_path, detail):
    assert api().load_cloud_batch(input_file(tmp_path, batch_data(requirements=detail)), now=NOW)


@pytest.mark.parametrize("location", ["광주광역시", "경기 광주광역시", "서울 광주광역시", "경기 또는 광주시"])
def test_load_still_rejects_outside_or_conflicting_administrative_regions(tmp_path, location):
    with pytest.raises(ValueError):
        api().load_cloud_batch(input_file(tmp_path, batch_data(location=location)), now=NOW)


@pytest.mark.parametrize("detail,accepted", [
    ("Java 백엔드 개발. 근무지: 광주시", True),
    ("Java 백엔드 개발. 근무지: 광주광역시", False),
])
def test_load_resolves_gwangju_detail_using_explicit_gyeonggi_province(tmp_path, detail, accepted):
    source = batch_data(location="경기도 광주시", requirements=detail)
    if accepted:
        assert api().load_cloud_batch(input_file(tmp_path, source), now=NOW)
    else:
        with pytest.raises(ValueError):
            api().load_cloud_batch(input_file(tmp_path, source), now=NOW)


def test_load_ten_valid_distinct_postings_and_24_hour_boundary(tmp_path):
    data = batch_data()
    data["postings"] = [batch_data(platform_id=str(i), url="https://jumpit.saramin.co.kr/position/" + str(i))["postings"][0]
                        for i in range(10)]
    assert len(api().load_cloud_batch(input_file(tmp_path, data), now=NOW)) == 10
    data = batch_data()
    data["collected_at"] = data["postings"][0]["collected_at"] = "2026-11-14T03:00:00Z"
    assert len(api().load_cloud_batch(input_file(tmp_path, data), now=NOW)) == 1


def test_save_preserves_legacy_url_duplicate_with_null_platform_id(tmp_path, postgrest, health_contract, state_settings):
    row, ev, app = preserved_state()
    row["platform_id"] = row["payload_json"]["platform_id"] = None
    health_contract()
    queue_snapshot(postgrest, row, ev, app, legacy=True)
    # The platform+ID query must be empty for this legacy row.
    postgrest.replies[-3] = (200, [], {})
    for _ in range(2):
        postgrest.replies.append((200, False, {}))
        queue_snapshot(postgrest, dict(row, last_seen_at=STAMP), ev, app, legacy=True)
        postgrest.replies[-3] = (200, [], {})
    receipt = api().save_cloud_batch(state_settings, input_file(tmp_path), explicit_write=True,
                                    receipt_path=tmp_path / "receipt.json", now=NOW)
    assert receipt["status"] == "verified"
    assert receipt["rows"][0]["outcome"] == "existing_duplicate"


@pytest.mark.parametrize("place", ["evaluation", "notes"])
def test_save_exact_json_comparison_does_not_equate_boolean_and_number(tmp_path, postgrest, health_contract, state_settings, place):
    import copy
    row, ev, app = preserved_state()
    target = ev["evaluation_json"] if place == "evaluation" else app["notes"]
    target["flag"] = 1
    health_contract()
    queue_snapshot(postgrest, row, ev, app, legacy=True)
    postgrest.replies.append((200, False, {}))
    changed_ev, changed_app = copy.deepcopy((ev, app))
    changed = changed_ev["evaluation_json"] if place == "evaluation" else changed_app["notes"]
    changed["flag"] = True
    queue_snapshot(postgrest, dict(row, last_seen_at=STAMP), changed_ev, changed_app, legacy=True)
    receipt = tmp_path / "receipt.json"
    with pytest.raises(RuntimeError):
        api().save_cloud_batch(state_settings, input_file(tmp_path), explicit_write=True, receipt_path=receipt, now=NOW)
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "unknown"
    assert len([c for c in postgrest.calls if c[0] == "POST"]) == 1


def test_load_accepts_aware_non_utc_clock_without_changing_source(tmp_path):
    from zoneinfo import ZoneInfo
    source = batch_data()
    result = api().load_cloud_batch(input_file(tmp_path, source), now=NOW.astimezone(ZoneInfo("Asia/Seoul")))
    assert result[0].to_dict() == source["postings"][0]


def test_load_uses_korean_deadline_date_even_when_collection_clock_is_utc(tmp_path):
    source = batch_data(deadline="2026-11-14")
    stamp = "2026-11-14T17:00:00+00:00"  # Already November 15 in Korea.
    source["collected_at"] = source["postings"][0]["collected_at"] = stamp
    with pytest.raises(ValueError):
        api().load_cloud_batch(input_file(tmp_path, source), now=datetime.fromisoformat(stamp))


@pytest.mark.parametrize("fraction", ["1", "12", "123", "1234", "12345", "123456"])
def test_load_accepts_all_postgres_fractional_utc_precisions(tmp_path, fraction):
    from datetime import timedelta

    source = batch_data()
    stamp = "2026-11-15T03:00:00." + fraction + "+00:00"
    source["collected_at"] = source["postings"][0]["collected_at"] = stamp
    loaded = api().load_cloud_batch(input_file(tmp_path, source), now=NOW + timedelta(seconds=1))
    assert loaded[0].collected_at == stamp


@pytest.mark.parametrize("step", [1, 2, 3, 4, 5, 6])
def test_save_checkpoint_failure_never_claims_success_or_retries(tmp_path, postgrest, health_contract, state_settings, monkeypatch, step):
    import os
    health_contract()
    queue_snapshot(postgrest)
    for result in (True, False):
        postgrest.replies.append((200, result, {}))
        queue_snapshot(postgrest, stored_row())
    real_replace = os.replace
    replaced = []

    def fail_once(source, destination):
        replaced.append(destination)
        if len(replaced) == step:
            raise OSError("synthetic-private-marker")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_once)
    target = tmp_path / "receipt.json"
    with pytest.raises(RuntimeError) as error:
        api().save_cloud_batch(state_settings, input_file(tmp_path), explicit_write=True, receipt_path=target, now=NOW)
    receipt = json.loads(target.read_text(encoding="utf-8"))
    assert receipt["status"] == "unknown"
    assert len([c for c in postgrest.calls if c[0] == "POST"]) == {1: 0, 2: 1, 3: 1, 4: 2, 5: 2, 6: 2}[step]
    assert "synthetic-private-marker" not in str(error.value)
    assert list(tmp_path.glob(".cloud-receipt-*.tmp")) == []


def test_save_health_failure_has_no_write_and_redacted_failed_receipt(tmp_path, postgrest, state_settings):
    postgrest.replies.append((403, {"message": "synthetic-private-marker"}, {}))
    target = tmp_path / "receipt.json"
    with pytest.raises(RuntimeError) as error:
        api().save_cloud_batch(state_settings, input_file(tmp_path), explicit_write=True, receipt_path=target, now=NOW)
    assert json.loads(target.read_text(encoding="utf-8")) == {"schema_version": 1, "status": "failed", "attempts": [], "rows": []}
    assert all(c[0] == "GET" for c in postgrest.calls)
    assert "synthetic-private-marker" not in str(error.value)


def test_save_checks_all_remote_identities_before_first_write(tmp_path, postgrest, health_contract, state_settings):
    data = batch_data()
    data["postings"].append(batch_data(platform_id="124", url="https://jumpit.saramin.co.kr/position/124")["postings"][0])
    health_contract()
    queue_snapshot(postgrest)
    # A contradictory canonical reply for the second item must abort the batch
    # before the already-validated first item can be written.
    postgrest.replies.append((200, [stored_row()], {}))
    target = tmp_path / "receipt.json"
    with pytest.raises(RuntimeError):
        api().save_cloud_batch(state_settings, input_file(tmp_path, data), explicit_write=True, receipt_path=target, now=NOW)
    receipt = json.loads(target.read_text(encoding="utf-8"))
    assert receipt["status"] == "failed" and receipt["attempts"] == []
    assert all(c[0] == "GET" for c in postgrest.calls)


def test_save_requires_second_false_even_if_readback_is_exact(tmp_path, postgrest, health_contract, state_settings):
    health_contract()
    queue_snapshot(postgrest)
    for _ in range(2):
        postgrest.replies.append((200, True, {}))
        queue_snapshot(postgrest, stored_row())
    target = tmp_path / "receipt.json"
    with pytest.raises(RuntimeError):
        api().save_cloud_batch(state_settings, input_file(tmp_path), explicit_write=True, receipt_path=target, now=NOW)
    receipt = json.loads(target.read_text(encoding="utf-8"))
    assert receipt["status"] == "unknown"
    assert [a["result"] for a in receipt["attempts"]] == [True, True]
    assert not postgrest.replies
