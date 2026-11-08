# Hermes 채용 지원 보조 시스템

## 개발 규칙

에이전트 문서 탐색은 [AGENTS.md](AGENTS.md)에서 시작합니다. 작업별 후속 문서는 [기능 색인](docs/agents/README.md), 코드·문서·CI/PR 변경은 [개발 진입점](docs/agents/development.md)으로 연결되며 관련 경로만 읽습니다.

작업 흐름은 [CONTRIBUTING.md](CONTRIBUTING.md), 코드·브랜치·커밋 규칙은 [개발 컨벤션](docs/CONVENTIONS.md), 기술 선택 근거는 [ADR](docs/adr/README.md)을 따릅니다. 새 기술·인프라·보안/보존 정책은 구현 전 ADR로 비교하며, 결정 승인과 실제 배포/검증을 구분합니다.

## 제품 방향과 구현 범위

이 프로젝트는 [셀프호스팅형 에이전트 채용 자동화 도구](docs/PRODUCT_SCOPE.md)를 지향합니다. 공통 Python 도구와 에이전트별 스킬/연결 설정을 제공하고, PC가 꺼진 동안에는 별도 원격 실행 환경이 작업하도록 설계합니다. 웹서비스나 다중 사용자 SaaS가 필수인 것은 아닙니다.

현재 여러 사이트의 브라우저 수집부터 회사 조사·맞춤 문서·무인 자동지원까지 전체 흐름이 완성된 것은 아닙니다. 앱 상태 저장은 ADR-0005에 따라 Supabase PostgreSQL로 단일화했습니다. 로컬 HTTP 계약·격리 PostgreSQL 테스트와 실제 Supabase 배포/설정 검증은 별개이며, ADR의 과거 개인환경 검증 기록을 현재 체크아웃의 배포 완료로 해석하지 않습니다.

공고 수집·조건 판별·평가·문서 초안·기록/알림을 단계적으로 조율합니다. 실제 지원은 기본적으로 꺼져 있으며, 현재 자동 수집 구현은 승인된 공식 API 경로입니다. 브라우저 기반 수집은 목표와 구현/검증 상태를 구분합니다.

PR 발행·리뷰·수정·CI 확인은 [에이전트 주도 PR 자동화](docs/PR_AUTOMATION.md)를 따릅니다. 실행 실패에는 필요한 경우 [간단한 실패 기록](docs/templates/run-failure.md)을 사용하며, 모든 실패에 기업용 장애 보고서를 요구하지 않습니다.

## 현재 프로젝트 상태

- 공식 Hermes Windows 설치는 scripts/install_hermes_local.ps1을 사용합니다.
- Python 의존성과 Chromium은 프로젝트 내부 work/ 아래에, Hermes 설정·저장소·도구는 Windows 경로 길이 제한을 피하도록 D:\HermesRuntime에 설치합니다. Windows 사용자 PATH는 영구 변경하지 않습니다.
- 사람인은 이용 승인을 받은 공식 API 키가 있을 때만 조회합니다.
- 잡코리아, 원티드, 점핏, 직행, 로켓펀치, 그룹바이는 별도 허가나 공식 API가 확인되기 전까지 자동 수집하지 않습니다.
- 별도로 확인한 현재 공고는 사용자 관리 시트의 URL 중복을 확인한 뒤에만 수동 검토 대상으로 반영합니다.
- AUTO_SUBMIT 기본값은 false입니다. CAPTCHA, OTP, 로그인 재인증이 나오면 사람이 처리해야 합니다.
- 배포용 계정 자격 증명이 아직 연결되지 않았다면 Google Sheets/Drive와 Telegram 자동 쓰기는 건너뜁니다.

## 클라우드에서 개발

GitHub 저장소의 **Code → Codespaces → Create codespace on main** 또는 VS Code **Reopen in Container**로 개발환경을 만들 수 있습니다. `.devcontainer/`가 Python 3.11·Chromium·한국어 PDF 폰트를 준비하고, GitHub Actions는 Ubuntu·Windows에서 테스트합니다.

개인 이력서·포트폴리오·생성 결과·프로필·자격 증명은 저장소에 포함하지 않습니다. `profile.example.json`은 빈 템플릿입니다. 실제 프로필은 무시되는 `profile.json`에 보관합니다.

**Hermes Cloud를 쓰면 별도 VPS를 직접 마련할 필요는 없습니다.** 다만 Nous Portal의 Cloud 접근권한·인스턴스·모델 인증·비용 확인이 필요하며, Codespaces 개발환경과 상시 자동화 운영은 별개입니다. Windows 전용 OCR의 Linux 대체 경로 등 남은 제한은 [클라우드 개발·운영 안내](docs/CLOUD_DEVELOPMENT.md)를 확인하세요.

## 설치

PowerShell에서 프로젝트 폴더로 이동한 뒤 실행합니다.

    .\scripts\install_windows.ps1

이 스크립트는 가상환경과 브라우저를 프로젝트 옆 work 폴더에 둡니다. 패키지를 설치한 뒤 `.env`가 없을 때만 `.env.example`을 복사하고 필요한 연결값을 로컬에서 채웁니다. 기존 `.env`는 덮어쓰지 마세요. 실사용 자격 증명은 Git이나 공유 폴더에 저장하지 마세요. Supabase 스키마 설치와 상태 연결은 [설정 안내](docs/SUPABASE_STATE.md)를 따릅니다.

## 로컬 확인

$RuntimeRoot = (Resolve-Path .\work\runtime).Path
& "$RuntimeRoot\.venv\Scripts\python.exe" -m hermes_job_automation.cli health
& "$RuntimeRoot\.venv\Scripts\python.exe" -m hermes_job_automation.cli sources
& "$RuntimeRoot\.venv\Scripts\python.exe" -m hermes_job_automation.cli run --collect-only

Hermes Cron은 수집 결과를 받은 뒤 skills/job-search/SKILL.md 절차에 따라 점수와 문서 초안을 작성합니다. 결과 JSON을 검토 후 finalize로 가져옵니다. finalize --execute는 Google Sheets/Drive와 Telegram으로 쓸 수 있으나 지원서 제출 버튼은 실행하지 않습니다.

& "$RuntimeRoot\.venv\Scripts\python.exe" -m hermes_job_automation.cli finalize --file .\data\hermes-review.json

## 오프라인 브라우저 실행 진단

패키지와 Chromium을 설치한 환경에서 운영 설정 없이 확인합니다.

```text
python -m hermes_job_automation.cli runtime-check
# 또는 job-assist runtime-check
```

- `.env`/`Settings.load()`·사용자 프로필·인증 파일을 읽지 않습니다. 임의 URL/프로필 입력 옵션도 없습니다.
- 매번 새 headless Chromium과 비공유 context를 열고 offline·요청 차단·service worker 차단을 적용합니다. 내장 합성 HTML의 한국어 DOM, JavaScript, 양식 입력만 확인하며 제출은 시도하지 않습니다.
- stdout JSON의 `schema_version: 1`, 실제 `browser.version`, boolean `checks`, 관찰한 `page_network_requests`와 `submission_occurred`를 확인하세요. 모두 통과하면 `status: verified`/종료 코드 0, 검사 불일치는 `failed`/1, 실행 불가는 `error`/1입니다. 오류는 일반 메시지와 예외 타입만 출력하며 원문·경로·인증정보는 숨깁니다. 관찰 전 실패한 요청 수·제출 여부·브라우저 버전은 `null`, 미통과/미실행 검사는 `false`입니다.
- 요청 수는 **진단 페이지의 Playwright request 이벤트** 수이지 브라우저 전체 트래픽이나 OS 방화벽 검증이 아닙니다. 실제 사이트·모델·인증·DB·예약은 `scope`에 미검증으로 표시합니다. `health`의 `next_run_schedule: null`, `schedule_status: not_verified`도 예약 등록을 검사하지 않았다는 뜻이며 미등록을 확인했다는 뜻은 아닙니다.
- 기존 GitHub Actions Ubuntu/Windows 테스트 job도 이 명령을 실행합니다. 로컬 성공과 해당 변경의 원격 CI 성공은 별도 증거이며 운영 배포·예약 가동을 의미하지 않습니다.

## 공고별 수정과 이미지 OCR

사용자가 공고 URL과 이력서/포트폴리오를 첨부하면 `skills/job-tailoring/SKILL.md`의 **공고 분석 → 공식 회사 사이트 분석(불가하면 생략 이유 기록) → 원본을 보존한 이력서 수정 → 적합도·사실성 검토 → 결과 저장** 절차를 사용합니다. 이는 Hermes 작업 절차이며, 기존 Python 일괄 실행에 회사 사이트 분석과 원본 이력서 편집이 자동 연결된 것은 아닙니다.

Windows의 설치된 한국어 OCR 기능을 사용하는 로컬 명령을 추가했습니다. API 키나 외부 이미지 업로드는 필요하지 않습니다.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:PYTHONUTF8 = '1'
& '.\work\runtime\.venv\Scripts\python.exe' -m hermes_job_automation.cli ocr-image --file '.\공고.png' --language ko --output '.\data\새로운-공고-ocr.json'
```

원본 이미지는 변경하지 않고 결과 JSON의 기존 파일도 덮어쓰지 않습니다. OCR 결과는 **확인 필요** 상태이며 날짜·숫자·필수조건을 원본과 대조해야 합니다. PDF는 먼저 텍스트 레이어를 읽고 필요한 이미지 페이지만 렌더링해 OCR합니다. 사이트별 브라우저 수집·로그인·CAPTCHA 처리·지원 제출을 이 명령이 수행하지는 않습니다. 매우 긴 이미지는 최대 크기 제한에 맞춰 복사본을 분할해야 합니다.

GitHub 스킬 조사와 출처는 `docs/OCR_SKILL_RESEARCH.md`에 있습니다. 외부 스킬 설치 승인 요청은 만료되어 설치되지 않았고, 위 명령은 별도로 구현한 Windows 로컬 OCR 경로입니다.

## 예약 실행

로그인한 Windows 세션에서 매일 04:00 KST 실행하도록 예약하려면:

    .\scripts\register_task.ps1

Windows가 꺼져 있을 때는 작업이 실행되지 않습니다. PC가 꺼져 있어도 정기 실행하려면 Hermes Cloud 같은 호스팅 인스턴스 또는 직접 운영하는 상시 가동 호스트가 필요합니다. 현재 저장소는 클라우드 개발 설정을 포함하지만 상시 운영 배포나 예약 실행을 완료한 것은 아닙니다. `docs/CLOUD_DEVELOPMENT.md`와 `docs/OPERATIONS.md`를 참고하세요.

예약을 해제하려면 .\scripts\unregister_task.ps1을 실행합니다. Hermes Gateway 작업은 사용자가 로그인한 뒤 실행되며, 모델 인증이 완료되어야 매일 평가와 초안을 만들 수 있습니다.

Hermes Gateway가 상시 실행되는 서버에서는 hermes/cron-job.txt의 Cron 명령을 등록할 수 있습니다.

## 계정 연결

상태 저장은 **Supabase PostgreSQL만** 사용합니다([ADR-0005](docs/adr/0005-supabase-postgres-only.md)). `JOB_ASSIST_STATE_BACKEND` 기본값은 `supabase`이며 `sqlite`나 잘못된 값은 오류로 거부합니다. Supabase 설정이 없거나 연결이 실패하면 저장을 중단하며 로컬 DB로 우회하지 않습니다. 환경 변수, read-only `state-health`, 별도 승인된 공개 샘플 `state-smoke --explicit-write`와 정확한 read-back 절차는 [Supabase 상태 저장소 안내](docs/SUPABASE_STATE.md)를 참고하세요. 기존 SQLite 파일은 보관용으로 남기며 앱은 읽거나 쓰지 않습니다. 자동 복사·이관·삭제는 하지 않습니다. 로컬 PostgreSQL 컨테이너는 SQL 테스트 전용이며 별도 운영 DB가 아닙니다. `run`/`finalize`는 `--execute` 없이도 상태 DB에 쓰며 오프라인 미리보기 명령이 아닙니다.

- Google Sheets/Drive: OAuth 데스크톱 클라이언트 또는 공유된 서비스 계정
- GPT: Hermes의 ChatGPT/Codex 구독 연결을 우선 사용하거나, OpenAI API key와 model 지정
- Telegram: bot token과 본인 chat ID
- 채용 사이트: 공식 API 신청·승인 및 사용범위 확인

상세 설정은 docs/GOOGLE_WORKSPACE_SETUP.md, docs/OPERATIONS.md, docs/PLATFORM_ACCESS.md를 참고하세요.

## 안전한 지원 처리

양식 검사는 로컬 HTML fixture로만 수행합니다.

& "$RuntimeRoot\.venv\Scripts\python.exe" -m hermes_job_automation.cli form-dry-run

실제 사이트 제출은 조건별 사용자 승인 레코드, AUTO_SUBMIT=true, FORM_AUTOFILL_ENABLED=true가 모두 있어야 시도할 수 있습니다. 제출 직전 Supabase 상태 저장소에 원자적 claim과 시도 ID가 기록되고, 접수 번호나 완료 화면이 확인되지 않으면 결과를 성공으로 표시하지 않습니다. 진행 중이거나 결과가 불명확한 신청은 재시도하지 않고 수동 확인 상태로 남깁니다.
