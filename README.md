# Hermes 채용 지원 보조 시스템

Hermes Agent가 매일 공고 수집, 조건 판별, GPT 적합도 평가, 맞춤형 문서 초안, Google Workspace 기록, Telegram 보고를 조율합니다. 실제 지원은 기본적으로 꺼져 있으며, 이 프로젝트의 자동화 수집은 플랫폼이 허용한 공식 API에만 연결합니다.

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

이 스크립트는 가상환경과 브라우저를 프로젝트 옆 work 폴더에 둡니다. 패키지를 설치한 뒤 .env.example을 .env로 복사하고 필요한 연결값을 채웁니다. 실사용 자격 증명은 Git이나 공유 폴더에 저장하지 마세요.

## 로컬 확인

$RuntimeRoot = (Resolve-Path .\work\runtime).Path
& "$RuntimeRoot\.venv\Scripts\python.exe" -m hermes_job_automation.cli health
& "$RuntimeRoot\.venv\Scripts\python.exe" -m hermes_job_automation.cli sources
& "$RuntimeRoot\.venv\Scripts\python.exe" -m hermes_job_automation.cli run --collect-only

Hermes Cron은 수집 결과를 받은 뒤 skills/job-search/SKILL.md 절차에 따라 점수와 문서 초안을 작성합니다. 결과 JSON을 검토 후 finalize로 가져옵니다. finalize --execute는 Google Sheets/Drive와 Telegram으로 쓸 수 있으나 지원서 제출 버튼은 실행하지 않습니다.

& "$RuntimeRoot\.venv\Scripts\python.exe" -m hermes_job_automation.cli finalize --file .\data\hermes-review.json

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

- Google Sheets/Drive: OAuth 데스크톱 클라이언트 또는 공유된 서비스 계정
- GPT: Hermes의 ChatGPT/Codex 구독 연결을 우선 사용하거나, OpenAI API key와 model 지정
- Telegram: bot token과 본인 chat ID
- 채용 사이트: 공식 API 신청·승인 및 사용범위 확인

상세 설정은 docs/GOOGLE_WORKSPACE_SETUP.md, docs/OPERATIONS.md, docs/PLATFORM_ACCESS.md를 참고하세요.

## 안전한 지원 처리

양식 검사는 로컬 HTML fixture로만 수행합니다.

& "$RuntimeRoot\.venv\Scripts\python.exe" -m hermes_job_automation.cli form-dry-run

실제 사이트 제출은 조건별 사용자 승인 레코드, AUTO_SUBMIT=true, FORM_AUTOFILL_ENABLED=true가 모두 있어야 시도할 수 있습니다. 제출 직전 SQLite에 시도 ID가 기록되고, 접수 번호나 완료 화면이 확인되지 않으면 결과를 성공으로 표시하지 않습니다. 진행 중이거나 결과가 불명확한 신청은 재시도하지 않고 수동 확인 상태로 남깁니다.
