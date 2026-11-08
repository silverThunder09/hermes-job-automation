# Supabase 상태 저장소 설정과 검증

## 경계와 현재 상태

- [ADR-0005](adr/0005-supabase-postgres-only.md)에 따라 **Supabase PostgreSQL만** 앱 상태 저장소로 사용합니다. 미지정 backend의 기본값은 `supabase`이며 `sqlite`/알 수 없는 값은 명확히 거부합니다.
- 기존 SQLite DB와 원본 지원서/문서는 보존합니다. 앱은 이전 DB 파일을 읽거나 쓰거나 만들지 않으며 자동 복사·이관·삭제하지 않습니다. 로컬 PostgreSQL은 SQL 테스트 전용이고 운영 대체 backend가 아닙니다.
- Supabase는 공고/적격성 JSONB, 평가 JSONB, 지원 상태/메모, 실행 기록만 저장합니다. Storage 업로드, 실제 지원, 스케줄링 기능을 켜지 않습니다.
- 코드/로컬 테스트와 **운영 Supabase 검증은 별개**입니다. 로컬 HTTP fixture 성공은 live 성공이 아닙니다. 신규 환경은 아래 SQL Editor 설치가 필요하며, 이미 적용한 환경은 불필요하게 재배포하지 않고 실제 설정으로 health/smoke를 검증합니다. 이 문서는 실시간 검증 결과나 자격 증명을 담지 않습니다.
- `SUPABASE_SECRET_KEY`는 서버 Data/Storage API 인증용입니다. **테이블 생성 권한을 가진 SQL 연결이나 Management API 토큰이 아니므로 이 키로 DDL을 실행하지 않습니다.**
- `AUTO_SUBMIT` / `FORM_AUTOFILL_ENABLED` / 별도 지원 승인 경계는 그대로입니다. 상태를 저장했다고 지원이 승인되거나 제출되지 않습니다.

## 1. 사용자: 단일 SQL 파일 실행

파일:

```text
supabase/migrations/202611070001_job_assist_state.sql
```

1. Supabase 대시보드에서 운영자가 승인한 대상 프로젝트를 선택합니다. 아래의 `<project-ref>`는 해당 프로젝트의 실제 reference로 바꿉니다. 조직 대시보드 URL을 프로젝트 URL로 사용하지 않습니다.
2. **SQL Editor → New query**에서 위 파일의 **전체 내용**을 붙여 넣습니다. API secret은 SQL 안에 넣지 않습니다.
3. DB owner 권한의 SQL Editor로 전체를 한 번 실행합니다. `BEGIN`부터 `COMMIT`까지 한 트랜잭션입니다.
4. 오류가 나면 그대로 중단하고 오류 내용을 확인합니다. 부분만 골라 실행하거나 권한/RLS를 완화하지 않습니다. 같은 연결에서 트랜잭션 오류가 남았다면 `ROLLBACK;` 후 원인을 해결하고 전체 파일을 다시 실행합니다.
5. 같은 파일의 재실행은 허용됩니다: `CREATE ... IF NOT EXISTS`, 고정 서명의 `CREATE OR REPLACE FUNCTION`, 버전 `ON CONFLICT DO NOTHING`이며 기존 행을 지우지 않습니다. 기존의 호환되지 않는 수동 테이블을 자동 수리하는 마이그레이션은 아닙니다. 향후 변경은 새 버전 파일을 추가합니다.
6. 파일 끝의 `NOTIFY pgrst, 'reload schema'`로 REST schema cache를 갱신합니다. 적용 직후 잠깐 route가 없으면 잠시 후 `state-health`를 다시 실행합니다.

생성되는 테이블:

- `public.job_assist_schema_versions` (버전 1)
- `public.job_assist_postings` (공고, 적격성, 정규 URL, 세 가지 중복 식별자)
- `public.job_assist_evaluations` (공고별 최신 평가 JSONB)
- `public.job_assist_applications` (지원 상태, claim, 증빙, `notes` JSONB)
- `public.job_assist_runs` (실행 기록)

RPC:

- `job_assist_save_posting`
- `job_assist_record_application`
- `job_assist_claim_submission`
- `job_assist_finish_submission`
- `job_assist_state_health` (고정 read-only probe)

모든 테이블에 RLS를 켜고 `PUBLIC`/`anon`/`authenticated` 권한을 회수합니다. Supabase 기본 `service_role`의 BYPASSRLS를 전제로 필요한 SELECT/INSERT/UPDATE만 부여합니다(DELETE/TRUNCATE 없음). RPC는 **SECURITY INVOKER**, 빈 `search_path`, `service_role`만 EXECUTE 허용입니다. SQL 문자열을 받아 실행하는 RPC는 없습니다. 스키마/버킷은 앱이 자동 생성하지 않습니다.

## 2. 운영자: 실제 Supabase 설정으로 live 검증

필요한 환경 변수(값/키를 채팅·로그·커밋에 출력하지 마세요):

| 이름 | 용도 |
|---|---|
| `JOB_ASSIST_STATE_BACKEND` | 미지정 시 `supabase`; 지정한다면 정확히 `supabase`만 허용 |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` (HTTPS hosted origin만, 경로/포트/사용자정보 불가) |
| `SUPABASE_SECRET_KEY` | 기존 서버 전용 `sb_secret_...` 키. 브라우저/클라이언트 배포 금지 |
| `SUPABASE_STORAGE_BUCKET` | 대상 프로젝트에 이미 존재하는 비공개 버킷 이름(예: `job-artifacts`) |

잘못된 backend 또는 원격 설정 누락은 로컬 저장소로 우회하지 않고 실패합니다. `health`와 `state-health`는 설정이 부족하면 `state.status` 또는 `status`에 `missing_configuration`과 누락된 변수 이름만 표시하며 DB/디렉터리를 만들지 않습니다. `state-health`는 이 경우 종료 코드 1을 반환합니다. 실제 저장소 선택/쓰기와 smoke는 자격 증명 누락을 오류로 거부합니다. 현대 secret은 `apikey` 헤더로만 보냅니다(`Bearer sb_secret_...` 사용 안 함). HTTPS 인증서 검증을 유지하고 redirect는 따라가지 않습니다. HTTP body/네트워크 예외의 원문은 오류 메시지로 출력하지 않습니다. 자동 재시도도 하지 않습니다: 쓰기 응답이 불확실하면 먼저 해당 키를 조회해 조정해야 합니다.

먼저 `.env`가 없을 때만 `.env.example`을 복사하고 필요한 값을 로컬에서 채웁니다. 기존 설정은 덮어쓰지 마세요. PowerShell 예시:

```powershell
if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
}
notepad .env
```

아래 명령은 저장소 루트에서 프로젝트 패키지를 설치한 Python 가상환경을 활성화한 **Bash/Git Bash** 기준입니다. `.env`의 기존 키는 `Settings.load()`가 읽되 출력하지 않습니다. backend 강제 override 없이 실제 설정을 사용합니다. `PYTHONPATH=src`는 현재 체크아웃 코드를 사용하기 위해 명시합니다. PowerShell에서는 `$env:PYTHONPATH = 'src'`를 먼저 설정한 후 `python -m ...`을 실행합니다.

```bash
PYTHONPATH=src python -m hermes_job_automation state-health
```

성공 조건: 종료 코드 0, `status=ready`, `backend=supabase`, `schema_version=1`, 예상 테이블 5개, `bucket_private=true`. 이 명령은 **GET만** 사용해 버전/RLS, 기대 컬럼, 기존 비공개 버킷을 확인합니다. 테이블/버킷을 만들거나 행을 저장하지 않습니다.

그다음 **승인된 공개 샘플 쓰기 검증**:

```bash
PYTHONPATH=src python -m hermes_job_automation state-smoke --explicit-write
```

선택적으로 공개 정보만 담은 JSON 객체 파일(`company`, `title`, `url`, 선택 `platform`, `platform_id`)을 `--file path/to/public-posting.json`으로 지정할 수 있습니다. 지원자 프로필/이력서/개인정보/토큰을 넣지 마세요. `--explicit-write` 없이는 설정을 읽기도 전에 거부합니다.

기본 샘플은 공개 사람인 55385305 / 도슨티 / AI-native Builder의 최소 공개 식별 필드입니다. 채용 유효성·지원자 적합성을 평가한 데이터가 아닙니다. 매 실행마다 `state-smoke:<uuid>` 공고 키와 새 run ID, 원문 URL에 별도 `job_assist_smoke=<uuid>` 식별 쿼리를 사용해 기존 실제 공고나 이전 샘플과 충돌하지 않도록 합니다. 원문 URL은 provenance로 보존합니다.

검증은 모두 **기존 store 공개 메서드**를 사용합니다:

1. `create_run` → `save_posting` → `get_posting` / `get_eligibility` 정확한 read-back
2. `save_evaluation` → `get_evaluation` 정확한 read-back
3. 샘플에만 `record_application(..., 'manual_review', ...)` → `get_application`
4. tracking URL/다른 키+같은 normalized URL 재저장은 False이며 원본 공고/적격성/평가 보존
5. 다시 `record_application(..., 'ready_for_approval', ...)`해도 기존 상태/메모/나머지 필드 전체가 그대로인지 read-back
6. `finish_run` → `get_run` 상태와 report JSON read-back

성공 조건: 종료 코드 0, `status=verified`, `checks`가 전부 true, `retained=true`. 출력의 **정확한 `sample_key`/`run_id`**를 보관합니다. 샘플은 삭제하지 않습니다(삭제 승인 없음). 실패하면 일부 저장된 샘플/실행이 남을 수 있으며 조정용으로 보존합니다. 성공한 live 검증 결과를 로컬 fixture 결과로 대신해서는 안 됩니다.

추가 조회도 동일 팩토리를 사용합니다. 아래는 운영자가 직접 실행하는 예시이며 이 문서 작성 시 원격 실행한 결과가 아닙니다:

```python
from hermes_job_automation.config import Settings
from hermes_job_automation.state import create_state_store

settings = Settings.load()
store = create_state_store(settings, read_only=True)
key = "state-smoke:<실제 성공 출력 UUID>"
assert store.get_posting(key) is not None
assert store.get_eligibility(key)["status"] == "review"
assert store.get_evaluation(key)["model"] == "storage-smoke-not-an-assessment"
assert store.application_status(key) == "manual_review"
assert store.get_application(key)["notes"] == {}
# get_run에는 smoke 출력의 정확한 run_id를 전달해 report_json까지 확인합니다.
```

승인된 단일 저장소 전환에서 운영자는 기존 `.env`의 backend 값만 `supabase`로 변경하고 다른 설정/키를 보존해야 합니다. 이 문서의 명령은 환경 값을 강제로 덮어쓰지 않습니다. 실제 설정의 **live health → 별도 승인된 live smoke → 정확한 read-back**을 확인해야 합니다. SQLite 기존 데이터는 자동 복사/동기화하지 않습니다. `run`/`finalize`는 `--execute` 여부와 별개로 Supabase 상태 DB에는 씁니다(`--execute`는 Google/Telegram 경계). 네트워크가 없으면 상태 저장을 완료할 수 없습니다.

## 데이터 보존과 동시성

- 신규 공고는 `posting_key`, normalized URL, `(platform, platform_id)` 각각 unique 제약으로 서버에서 원자적 중복 판정합니다. 클라이언트 read-then-write가 아닙니다. 기존 두 행을 서로 연결하는 모순된 식별자는 자동 병합하지 않고 실패시킵니다.
- 중복 저장은 `last_seen_at`만 갱신하며 공고 원본/적격성/평가/지원 상태/메모는 바꾸지 않습니다. False를 받은 중복의 별도 키는 alias로 만들지 않으므로 원래 canonical 키로 조회하세요.
- `record_application`은 최초 상태만 기록하며 기존 상태와 메모를 덮어쓰지 않습니다. 수동 상태 변경 API는 이 범위에 포함되지 않습니다.
- submission claim은 서버 단일 upsert로 경쟁 요청 하나만 성공합니다. `submitting`/`submitted`/`unknown`은 재claim 불가이며 수동 조정이 필요합니다. finish는 활성 `submitting`에서만 가능합니다.
- 이 RPC는 실제 사이트 제출을 수행하지 않으며 smoke는 claim/submission 함수를 호출하지 않습니다.

## 로컬 테스트 (운영 Supabase와 별개)

```bash
PYTHONPATH=src python -m pytest -o addopts='' -q
```

테스트는 `.env` 로드를 차단하고 Supabase 환경 값을 격리합니다. HTTP tests는 실제 stdlib PostgREST adapter와 로컬의 명시적 요청/응답 transcript만 사용하며 DB나 영속성 구현을 흉내 내는 in-memory store가 아닙니다. smoke/CLI는 정확한 payload/적격성/평가/지원 필드/보고서 및 식별자 read-back과 불일치 거부를 검증합니다. 이는 live Supabase 성공을 의미하지 않습니다. 별도 SQL 테스트는 Docker에 **이미 있는** `postgres:16` 이미지와 네트워크가 없는 로컬 컨테이너에서 실제 PostgreSQL을 실행합니다. 원격 Docker endpoint와 네트워크가 켜진 컨테이너는 거부합니다. 라이브 URL이나 키는 필요하지 않습니다.

```bash
# 테스트 전용 새 이름을 사용하고 --pull=never로 다운로드를 막습니다.
docker run --pull=never --network none --name job-assist-pg-test -e POSTGRES_HOST_AUTH_METHOD=trust -d postgres:16
# pg_isready 성공 후:
JOB_ASSIST_TEST_POSTGRES_CONTAINER=job-assist-pg-test PYTHONPATH=src python -m pytest -o addopts='' -q tests/test_supabase_schema.py
# 재실행은 새 test DB를 만들며 기존 DB를 지우지 않습니다.
docker stop job-assist-pg-test
```

SQL 테스트는 마이그레이션 2회 실행, 권한/RLS/search_path, 6개 경쟁 요청의 세 가지 중복 식별자, 기존 상태/메모/평가 보존, 단일 submission claim 승자와 재시도 차단, 정확한 공고/평가/실행 보고서 재조회와 claim 없는 finish 차단을 실제 로컬 PostgreSQL에서 검증합니다. 별도 삭제 승인 전에는 컨테이너/볼륨/테스트 DB를 삭제하지 마세요.

CI의 일반 Ubuntu/Windows `test` 작업은 HTTP/브라우저 등 로컬 fixture를 실행하며 SQL opt-in 환경이 없어 `test_supabase_schema.py`를 skip합니다. 별도 **SQL invariants (PostgreSQL 16)** Ubuntu 작업은 `postgres:16`을 내려받은 뒤 `--network none`인 임시 로컬 컨테이너를 만들고, 준비 상태를 기다려 해당 SQL 테스트를 실제 실행합니다. API 키/저장소 Secrets/실사용 DB는 사용하지 않으며 성공/실패와 관계없이 컨테이너를 중지합니다. 테스트 DB는 이 일회성 runner 안에만 남고 운영 배포나 live 검증을 대신하지 않습니다. workflow 파일의 로컬 검증과 GitHub에서의 실제 CI 성공도 구분합니다.
