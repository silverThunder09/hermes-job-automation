# 운영 가이드

## 필수 설정

1. `.env`가 없을 때만 `.env.example`을 복사합니다. 기존 파일/자격 증명은 덮어쓰지 않고 필요한 값만 로컬에서 채웁니다.
2. profile.example.json을 profile.json으로 복사하고 원본 이력서에서 확인한 연락처를 필요한 경우에만 채웁니다.
3. 수집은 [ADR-0011](adr/0011-private-collection-writer.md)의 클라우드 브라우저/MCP 경로를 따릅니다. 사람인 공식 API는 운영 선택지에서 폐기했으며 승인·키를 요구하지 않습니다. 아래 기존 Python CLI 예시는 이 새 수집 경로의 구현/배포 증거가 아닙니다.
4. GPT API를 직접 쓸 경우 OPENAI_API_KEY와 OPENAI_MODEL을 지정합니다. Hermes Cron은 Hermes에 로그인한 모델을 사용하도록 skills/job-search/SKILL.md 절차를 따릅니다.
5. Google Sheets/Drive와 Telegram 연결은 별도 안내에 따라 설정합니다.
6. 상태 DB는 Supabase PostgreSQL만 사용합니다. `JOB_ASSIST_STATE_BACKEND`는 미지정 또는 정확히 `supabase`로 설정하고, `SUPABASE_URL`·`SUPABASE_SECRET_KEY`·`SUPABASE_STORAGE_BUCKET`을 구성합니다. `sqlite`/알 수 없는 값은 오류이며 자격 증명 누락이나 네트워크 장애 때 로컬 DB로 우회하지 않습니다. [상태 저장소 안내](SUPABASE_STATE.md)의 read-only health와 별도 승인된 smoke 검증을 확인하세요.

## 실행 단계

- python -m hermes_job_automation.cli health: 실행 도구와 인증 설정 여부를 요약합니다. 값 자체는 출력하지 않습니다.
- python -m hermes_job_automation.cli sources: 기존 Python 수집기를 실행합니다. 기존 사람인 API 설정이 활성화돼 있으면 실제 API를 호출할 수 있습니다. 선택한 클라우드 브라우저/MCP 경로의 상태 조회 명령이 아닙니다.
- python -m hermes_job_automation.cli run --collect-only: 승인된 소스와 수동 파일만 수집하고 data/to-review.json을 만듭니다.
- Hermes 모델이 점수와 문서 초안을 만든 뒤 job-assist finalize --file <검토 JSON>으로 Supabase에 상태를, 로컬에 문서를 저장합니다. `run`/`finalize`는 `--execute` 없이도 Supabase 상태 DB에 쓰므로 오프라인 미리보기 명령이 아닙니다.
- job-assist finalize --file <검토 JSON> --execute: 점수와 문서를 Google Sheets/Drive에 기록하고 Telegram 요약을 보냅니다.

## 제출 승인

지원서 제출은 공고별 승인만 허용합니다. approve-posting은 대화형 터미널에서 회사, 공고 ID, 도메인, 점수 상한, 조건을 표시하고 고정 승인문을 직접 입력해야 승인 파일을 저장합니다. 승인은 지정한 공고 ID와 도메인, 만료시간, 점수 상한 안에서만 유효합니다.

예약된 프로세스에서 AUTO_SUBMIT=true만 켜도 제출은 되지 않습니다. 먼저 공고별 승인 파일이 있어야 하고, FORM_AUTOFILL_ENABLED=true, 적합 판정, CAPTCHA/OTP 부재가 모두 필요합니다. 제출 직전 Supabase RPC로 원자적 claim을 획득하며 submitting, submitted, unknown 상태는 다시 제출하지 않습니다. 접수 완료 문구나 접수번호가 확인되지 않으면 성공으로 기록하지 않습니다.

현재 작업 상태에서는 공고별 지원 승인 파일이 없고 AUTO_SUBMIT=false입니다.

## 예약과 재부팅

Windows 작업은 사용자 로그인이 되어 있고 PC가 켜져 있을 때만 실행됩니다. 꺼진 시간의 작업은 Windows가 다음 로그인 후 처리합니다. Hermes Gateway도 Windows 사용자 세션과 브라우저·모델 로그인 상태를 점검해야 합니다.

PC-off 운영은 [ADR-0006](adr/0006-actions-batch-boundary.md)에 따라 **매일 04:00 `Asia/Seoul`의 GitHub-hosted 일회성 배치**, 공개 개발 CI와 비공개 민감 운영의 분리로 결정했습니다. [ADR-0011](adr/0011-private-collection-writer.md)은 PC-on의 로컬 시작→클라우드 수집, PC-off의 Actions 시작→클라우드 실행, 공통 Supabase 저장과 별도 collection/storage job을 정합니다. 비공개 운영 저장소·기존 DB 설정의 Secrets 등록·조건부 1회 원격 저장 검증은 승인 범위에 포함되지만 아직 구현/배포하지 않았습니다. 예약 가동·모델 인증 이전·개인자료·제출은 별도 승인입니다. 별도 상시 Cloud/VPS/Gateway는 필수가 아니며 위 Windows/Gateway 절차는 선택적 로컬 경로입니다. 현재 운영 workflow/인증/예약은 미구현·미가동이며 정각 시작도 보장하지 않습니다. [클라우드 실행 경계](CLOUD_DEVELOPMENT.md#3-pc가-꺼져도-매일-실행)를 참고하세요.

## 로그와 개인정보

- Supabase PostgreSQL: 공고 URL, 적격성, 지원 상태/메모, 점수, 실행 상태
- 기존 SQLite 파일: 보관용으로만 유지합니다. 앱은 읽거나 쓰거나 초기화하지 않으며 자동 복사·이관·삭제하지 않습니다.
- 로컬 PostgreSQL: 네트워크 격리 SQL 테스트 전용입니다. 별도 운영 서버나 앱 대체 backend가 아닙니다.
- data/runs/: 실행별 JSON 요약
- logs/job-assistant.log: 원인과 오류 요약
- generated/: 생성한 회사별 이력서·자기소개서 DOCX 및 PDF 초안
- .env, OAuth token, 서비스 계정 키는 Git에 추가하지 않습니다.
- Telegram에는 요약과 승인 대기 정보만 보냅니다. 이력서 본문과 연락처는 포함하지 않습니다.
