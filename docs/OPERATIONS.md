# 운영 가이드

## 필수 설정

1. .env.example을 .env로 복사합니다.
2. profile.example.json을 profile.json으로 복사하고 원본 이력서에서 확인한 연락처를 필요한 경우에만 채웁니다.
3. 사람인 API를 쓸 때는 이용 승인이 끝난 뒤 SARAMIN_API_APPROVED=true와 발급 키를 설정합니다.
4. GPT API를 직접 쓸 경우 OPENAI_API_KEY와 OPENAI_MODEL을 지정합니다. Hermes Cron은 Hermes에 로그인한 모델을 사용하도록 skills/job-search/SKILL.md 절차를 따릅니다.
5. Google Sheets/Drive와 Telegram 연결은 별도 안내에 따라 설정합니다.

## 실행 단계

- python -m hermes_job_automation.cli health: 실행 도구와 인증 설정 여부를 요약합니다. 값 자체는 출력하지 않습니다.
- python -m hermes_job_automation.cli sources: 각 플랫폼의 자동 수집 가능 상태를 보여줍니다.
- python -m hermes_job_automation.cli run --collect-only: 승인된 소스와 수동 파일만 수집하고 data/to-review.json을 만듭니다.
- Hermes 모델이 점수와 문서 초안을 만든 뒤 job-assist finalize --file <검토 JSON>으로 로컬 SQLite와 문서를 저장합니다.
- job-assist finalize --file <검토 JSON> --execute: 점수와 문서를 Google Sheets/Drive에 기록하고 Telegram 요약을 보냅니다.

## 제출 승인

지원서 제출은 공고별 승인만 허용합니다. approve-posting은 대화형 터미널에서 회사, 공고 ID, 도메인, 점수 상한, 조건을 표시하고 고정 승인문을 직접 입력해야 승인 파일을 저장합니다. 승인은 지정한 공고 ID와 도메인, 만료시간, 점수 상한 안에서만 유효합니다.

예약된 프로세스에서 AUTO_SUBMIT=true만 켜도 제출은 되지 않습니다. 먼저 공고별 승인 파일이 있어야 하고, FORM_AUTOFILL_ENABLED=true, 적합 판정, CAPTCHA/OTP 부재가 모두 필요합니다. 제출 직전 SQLite 상태를 잠그며 submitting, submitted, unknown 상태는 다시 제출하지 않습니다. 접수 완료 문구나 접수번호가 확인되지 않으면 성공으로 기록하지 않습니다.

현재 작업 상태에서는 공고별 지원 승인 파일이 없고 AUTO_SUBMIT=false입니다.

## 예약과 재부팅

Windows 작업은 사용자 로그인이 되어 있고 PC가 켜져 있을 때만 실행됩니다. 꺼진 시간의 작업은 Windows가 다음 로그인 후 처리합니다. Hermes Gateway도 Windows 사용자 세션과 브라우저·모델 로그인 상태를 점검해야 합니다.

PC 전원이 꺼져도 매일 04:00 실행하려면 Hermes Cloud 인스턴스 또는 직접 관리하는 상시 호스트가 필요합니다. Cloud는 별도 VPS 구매 없이 사용할 수 있지만 계정 권한·인스턴스·비용·인증 확인이 필요합니다. 코드의 GitHub 업로드와 `.devcontainer` 개발 설정은 운영 배포가 아니며, 현재 유료 Cloud/VPS 생성·Gateway/Cron 가동은 수행하지 않았습니다. `CLOUD_DEVELOPMENT.md`를 참고하세요.

## 로그와 개인정보

- data/state.sqlite3: 공고 URL, 지원 상태, 점수, 실행 상태
- data/runs/: 실행별 JSON 요약
- logs/job-assistant.log: 원인과 오류 요약
- generated/: 생성한 회사별 이력서·자기소개서 DOCX 및 PDF 초안
- .env, OAuth token, 서비스 계정 키는 Git에 추가하지 않습니다.
- Telegram에는 요약과 승인 대기 정보만 보냅니다. 이력서 본문과 연락처는 포함하지 않습니다.
