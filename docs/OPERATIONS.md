# 운영 가이드

## 필수 설정

1. `.env`가 없을 때만 `.env.example`을 복사합니다. 기존 파일/자격 증명은 덮어쓰지 않고 필요한 값만 로컬에서 채웁니다.
2. profile.example.json을 profile.json으로 복사하고 원본 이력서에서 확인한 연락처를 필요한 경우에만 채웁니다.
3. 수집 설정 전 [선택한 수집 경로와 기존 코드](PLATFORM_ACCESS.md#선택한-수집-경로와-기존-코드)를 확인합니다.
4. GPT API를 직접 쓸 경우 OPENAI_API_KEY와 OPENAI_MODEL을 지정합니다. Hermes Cron은 Hermes에 로그인한 모델을 사용하며 [일괄 검토 절차](../skills/job-search/SKILL.md)를 따릅니다.
5. Google Sheets/Drive와 Telegram 연결은 별도 안내에 따라 설정합니다.
6. 상태 DB는 Supabase PostgreSQL만 사용합니다. `JOB_ASSIST_STATE_BACKEND`는 미지정 또는 정확히 `supabase`로 설정하고, `SUPABASE_URL`·`SUPABASE_SECRET_KEY`·`SUPABASE_STORAGE_BUCKET`을 구성합니다. `sqlite`/알 수 없는 값은 오류이며 자격 증명 누락이나 네트워크 장애 때 로컬 DB로 우회하지 않습니다. [상태 저장소 안내](SUPABASE_STATE.md)의 read-only health와 별도 승인된 smoke 검증을 확인하세요.

## 실행 단계

공개 공고 수집에는 [현행 플랫폼의 진행·중단 기준](PLATFORM_ACCESS.md#진행중단-기준)을 적용합니다. 아래는 기존 Python CLI 명령입니다. 실행 전에 [공통 승인 경계](../AGENTS.md#always-on-boundaries)를 확인합니다. 사이트 읽기 권한은 DB 쓰기·외부 업로드·알림·예약·제출 권한이 아닙니다.

- python -m hermes_job_automation.cli health: 실행 도구와 인증 설정 여부를 요약합니다. 값 자체는 출력하지 않습니다.
- python -m hermes_job_automation.cli sources: 기존 Python 수집기를 실행합니다. 기존 사람인 API 설정이 활성화돼 있으면 실제 API를 호출할 수 있습니다. 선택한 클라우드 브라우저/MCP 경로의 상태 조회 명령이 아닙니다.
- python -m hermes_job_automation.cli run --collect-only: 기존 Python 경로에서 설정된 소스와 수동 파일을 처리하고, 신규 검토 후보가 있으면 data/to-review.json을 만듭니다. 빈 결과로 기존 검토 대기열을 지우지 않습니다.
- Hermes 모델이 점수와 문서 초안을 만든 뒤 job-assist finalize --file <검토 JSON>으로 Supabase에 상태를, 로컬에 문서를 저장합니다. `run`/`finalize`는 `--execute` 없이도 Supabase 상태 DB에 쓰므로 오프라인 미리보기 명령이 아닙니다.
- `run --execute`와 `finalize --execute`는 설정과 처리 결과에 따라 Google Sheets에 행을 추가하고, Drive에 생성 서류를 업로드하고, Telegram으로 요약을 보낼 수 있습니다. 두 명령 모두 CLI에서 대상별 사용자 승인 기록을 검사하지 않으므로 실행 전에 운영자가 대상·데이터·전송 범위의 승인을 확인합니다. `--execute`는 실제 사이트 제출을 실행하거나 승인하지 않습니다.

### 수집 결과와 종료 코드

`run`의 JSON `status`와 Supabase 실행 상태는 일치합니다. 모든 수집원이 차단됐을 때 수집 0건은 **공고가 없다는 확인이 아니라 데이터를 수집하지 못했다는 뜻**입니다.

| status | 의미 | CLI 종료 코드 |
|---|---|---|
| `blocked` | 승인·키가 없거나 수동 전용 등으로 성공한 수집원/수동 입력이 없음 | 1 |
| `failed` | 실제 수집 오류 또는 알 수 없는 결과만 있고 성공/부분 성공이 없음 | 1 |
| `completed_with_gaps` | 일부 수집 실패/부분 성공 또는 평가·검토 보완이 남음 | 0 |
| `completed` | 실행한 유효 수집원/수동 입력이 정상 처리됨 | 0 |

`zero_results_confirmed=true`는 실행한 성공 소스/유효 수동 입력이 모두 0건을 반환했고 부분 성공·실패가 없을 때만 표시합니다. 차단·실패·불완전 수집은 false이며, 어떤 값도 **자동 접근하지 않은 다른 플랫폼까지 공고가 없다는 뜻은 아닙니다**. 상세 범위는 `sources`를 함께 확인하세요. 성공·부분 성공 이외 상태에서 전달된 공고는 저장하지 않습니다.

신규 공고가 없으면 개인 프로필을 읽지 않습니다. `run`은 차단 상태라도 실행 기록을 DB에 저장하므로 읽기 전용 진단으로 사용하지 마세요. `--execute`를 사용한 알림은 실제 상태에 맞춰 차단/실패/보완 필요/완료를 구분하며, 이 동작이 전송·운영 실행 승인을 대신하지 않습니다.

## 제출 승인

기본 작업은 초안·검토까지이며, 실제 지원서 제출은 공고별 승인만 허용합니다. `approve-posting`은 대화형 터미널에서 플랫폼·공고 ID·도메인·점수 상한·조건을 표시하고, 사용자가 고정 승인문을 직접 입력해야 승인 파일을 저장합니다. 승인은 지정한 플랫폼·공고 ID·도메인·조건·유효기간·점수 상한 안에서만 유효합니다. 회사와 공고가 맞는지, 실제로 승인 조건을 충족하는지는 운영자가 확인합니다. helper는 조건이 기록됐는지만 검사합니다.

공고별 승인 파일과 `AUTO_SUBMIT=true`, `FORM_AUTOFILL_ENABLED=true`, 적합 판정이 모두 필요합니다. CAPTCHA·OTP·로그인 요구는 [접근 정책](PLATFORM_ACCESS.md#진행중단-기준)에 따라 중단하며, 마감이 상충하거나 필수 입력이 없으면 사람의 검토를 기다립니다. 운영 절차상 이미 제출을 시도했거나 시도 여부가 불명확한 공고는 다시 제출하지 않고 사람이 결과를 확인합니다.

제출 helper는 클릭 직전 Supabase RPC로 원자적 claim을 획득해 시도 ID를 기록합니다. RPC는 `submitting`, `submitted`, `unknown` 상태의 중복 claim을 막지만, 상태 검사만으로 과거 시도가 없다고 보장하지는 않습니다. helper는 화면의 성공 관련 문자열로 상태를 판정하며 접수번호 값이나 접수 상태를 검증하지는 않습니다. 운영자는 실제 접수번호 또는 명시적인 접수 완료 상태를 확인한 경우에만 성공으로 보고합니다. 증거가 없으면 결과를 미확인으로 남기고 재시도하지 않습니다. 기본값은 `AUTO_SUBMIT=false`이며 기존 `run`/`finalize`에는 실사이트 제출이 연결돼 있지 않습니다.

## 예약과 재부팅

Windows 작업은 사용자 로그인이 되어 있고 PC가 켜져 있을 때만 실행됩니다. 꺼진 시간의 작업은 Windows가 다음 로그인 후 처리합니다. Hermes Gateway도 Windows 사용자 세션과 브라우저·모델 로그인 상태를 점검해야 합니다.

PC-off 운영은 [ADR-0006](adr/0006-actions-batch-boundary.md)에 따라 **매일 04:00 `Asia/Seoul`의 GitHub-hosted 일회성 배치**로 정했습니다. 공개 개발 CI와 비공개 민감 운영은 분리합니다. [ADR-0011](adr/0011-private-collection-writer.md)의 [수집 경로](PLATFORM_ACCESS.md#선택한-수집-경로와-기존-코드)와 별도 collection/storage job을 적용합니다. 비공개 운영 저장소·기존 DB 설정의 Secrets 등록·조건부 1회 수동 원격 저장 검증은 승인 범위에 포함됩니다. 예약 가동은 이 검증 후 별도 승인하며, 모델 인증 이전·개인자료·제출도 별도 승인입니다. 운영 workflow·인증·예약은 미구현·미가동이며 GitHub 예약은 지연·누락될 수 있습니다. 별도 상시 Cloud/VPS/Gateway는 필수가 아니며 위 Windows/Gateway 절차는 선택적 로컬 경로입니다. [클라우드 실행 경계](CLOUD_DEVELOPMENT.md#3-pc가-꺼져도-매일-실행)를 참고하세요.

## 로그와 개인정보

- Supabase PostgreSQL: 공고 URL, 적격성, 지원 상태/메모, 점수, 실행 상태
- 기존 SQLite 파일: 보관용으로만 유지합니다. 앱은 읽거나 쓰거나 초기화하지 않으며 자동 복사·이관·삭제하지 않습니다.
- 로컬 PostgreSQL: 네트워크 격리 SQL 테스트 전용입니다. 별도 운영 서버나 앱 대체 backend가 아닙니다.
- data/runs/: 실행별 JSON 요약
- logs/job-assistant.log: 원인과 오류 요약
- generated/: 생성한 회사별 이력서·자기소개서 DOCX 및 PDF 초안
- .env, OAuth token, 서비스 계정 키는 Git에 추가하지 않습니다.
- Telegram에는 요약과 승인 대기 정보만 보냅니다. 이력서 본문과 연락처는 포함하지 않습니다.
