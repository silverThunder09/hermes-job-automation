# Hermes Agent 공식 기능 확인

- 확인일: 2026-11-03
- 확인 범위: Hermes 공식 문서 및 NousResearch 공식 GitHub 저장소
- 공식 저장소: [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)

## 실행 환경 및 설치

Hermes는 Windows 10/11에서 네이티브 실행을 Tier 1 지원합니다. PowerShell 설치 방법은 다음과 같습니다.

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
hermes --version
hermes setup
```

설치는 기본적으로 사용자 프로필 아래 `%LOCALAPPDATA%\hermes`를 사용하며 관리자 권한은 필요하지 않습니다. 새 터미널을 열어 PATH를 갱신해야 합니다. 공식 문서에는 Linux/WSL2와 Docker도 지원 대상으로 나옵니다. [Windows 네이티브 안내](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native), [플랫폼 지원표](https://hermes-agent.nousresearch.com/docs/getting-started/platform-support)

## GPT 인증과 과금 경계

Hermes는 `hermes model`의 **ChatGPT or Codex Subscription** 항목에서 OpenAI Codex OAuth를 설정할 수 있고, 브라우저가 아닌 기기 코드 로그인이 기본입니다. Hermes는 토큰을 자체 인증 저장소에 보관하고, Codex CLI 인증을 가져오는 기능도 문서화되어 있습니다. 별도 API 경로로는 `openai-api` 공급자와 `OPENAI_API_KEY`가 지원됩니다. 이 경우 API 키 계정으로 청구됩니다. [모델 공급자 안내](https://hermes-agent.nousresearch.com/docs/integrations/providers)

중요한 제한: 공식 문서는 ChatGPT 구독을 통한 Codex 인증 기능은 설명하지만, **어떤 ChatGPT 요금제에서 Hermes 사용이 가능한지와 사용량이 요금제의 Codex 한도에 어떻게 반영되는지는 문서화하지 않았습니다.** 따라서 ChatGPT/Codex OAuth가 API 사용료 없이 계속 가능하다고 단정할 수 없습니다. 실제 계정으로 인증 및 모델 호출을 검증해야 합니다. OAuth가 불가하면 OpenAI API 키가 별도 대안입니다. [공급자별 구독 및 과금 안내](https://hermes-agent.nousresearch.com/docs/integrations/providers)

## 브라우저와 스킬

브라우저 도구 `browser_exec`는 로컬 Chromium 또는 설정된 클라우드 브라우저를 조작합니다. Windows 로컬 실행에는 Hermes Chromium 설치 또는 별도 Chromium 실행 파일이 필요할 수 있습니다. 실제 브라우저 프로필 사용은 기본 비활성이며, Hermes 문서는 이를 로그인된 사용자 권한으로 동작하는 편의 기능으로 분류합니다. 예약 실행은 기본 headless이고, 세션이 만료되면 로그인 화면을 오류로 보고합니다. [브라우저 자동화 안내](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser), [Windows 브라우저 안내](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native)

Hermes 스킬은 `SKILL.md` 기반의 지식/절차 모듈이며, 사용자 데이터 디렉터리에 설치하거나 자체 스킬을 둘 수 있습니다. 예약 작업에 스킬을 붙일 수 있고, 허브에서 설치하는 서드파티 스킬은 보안 검사를 거칩니다. 스킬은 Hermes의 구동 기능이지 채용 사이트별 API/수집기를 자동으로 제공한다는 뜻은 아닙니다. [스킬 시스템](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)

채용 사이트별 자동화는 플랫폼의 이용약관과 접근 제한을 별도로 준수해야 합니다. 브라우저 도구가 제공된다는 사실은 사이트의 자동화 허가를 의미하지 않습니다. CAPTCHA, OTP, 추가 인증은 사용자 개입 대상으로 남겨야 합니다.

## 매일 04:00 KST와 상시 실행

Hermes Cron은 Gateway가 60초 간격으로 확인하며, 예약 작업은 분리된 새 에이전트 세션에서 실행됩니다. 시간대는 설정에서 지정하거나 작업별로 지정할 수 있습니다. 매일 오전 4시 한국 시간은 다음 형식으로 예약할 수 있습니다.

```powershell
hermes cron create "0 4 * * *" --timezone Asia/Seoul --name "daily-job-search" "채용공고 수집 및 결과 요약"
hermes cron list
hermes cron status
```

Windows에서는 `hermes gateway install`이 사용자가 로그인할 때 실행되는 Task Scheduler 작업을 등록합니다. 게이트웨이는 로그아웃/재부팅 이후 자동 재개되도록 설정할 수 있지만, **PC가 꺼져 있거나 사용자가 로그인하지 않은 시간에는 작업을 실행하지 못합니다.** Windows 로그인 전에도 돌리려면 별도 Windows 서비스 설정이 필요하며 관리자 권한을 요구합니다. 사용자 PC가 꺼져도 실행하려는 목표에는 상시 가동 Linux VPS가 더 적합합니다. Linux에서 `sudo hermes gateway install --system`은 부팅 시 시작되는 시스템 서비스를 설치합니다. VPS 설치는 실제 서버 접근권한, 네트워크, 비용이 필요하며 현재 환경에서 접근 불가능하면 배포 완료로 보고할 수 없습니다. [Cron 안내](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron), [Gateway 내부와 서비스 수명](https://hermes-agent.nousresearch.com/docs/developer-guide/gateway-internals), [Windows Gateway 작업](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native)

Hermes Cron은 프로세스 중복 실행을 막는 tick lock을 제공하고, 상태/다음 실행을 `hermes cron status`로 확인합니다. 시스템 cron에서 `hermes cron tick`만 실행해도 에이전트 작업은 처리되지 않으므로 Gateway가 실행 중이어야 합니다. [Cron 동작 및 운영 명령](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron)

## Telegram과 저장소 연동

Telegram 연동에는 BotFather 발급 `TELEGRAM_BOT_TOKEN`과 허용 사용자 ID `TELEGRAM_ALLOWED_USERS`가 필요합니다. `hermes gateway setup`으로 설정할 수 있고, 예약 작업 결과를 Telegram으로 전달할 수 있습니다. 토큰이나 사용자 ID 없이 연결 성공 및 실제 메시지 전송을 검증할 수는 없습니다. [Telegram 설정](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram), [환경 변수 참조](https://hermes-agent.nousresearch.com/docs/reference/environment-variables)

공식 페이지에서 Hermes Gateway/브라우저/스킬 기능은 확인했지만, 이 조사 범위에서는 기존 Google Sheets와 Drive에 대한 내장 읽기·쓰기 연동을 확인하지 못했습니다. 프로젝트 측에서 Google Sheets/Drive API 또는 검증된 MCP 커넥터와 OAuth 권한을 구성해야 합니다.

## 구현 판단

1. PC에서 개발·초기 검증은 네이티브 Windows 설치로 수행할 수 있습니다.
2. 상시 운영은 Hermes Cloud 호스팅 인스턴스 또는 직접 관리하는 상시 호스트/VPS에서 구성할 수 있습니다. 이후 공식 문서 재확인에서 Nous Portal의 Hermes Cloud 관리 기능을 확인했으며, Cloud 사용 시 별도 VPS를 직접 마련할 필요는 없습니다. 기존 VPS 전제와 구분하고 `CLOUD_DEVELOPMENT.md`를 참고하세요. 어느 방식도 실제 인증·실행·저장 결과 확인 전에는 배포 완료로 보고하지 않습니다.
3. 모델은 우선 Codex OAuth 로그인 및 실제 호출을 검증하고, 구독 자격/쿼터가 확인되지 않거나 인증에 실패하면 명시적 API 키 설정이 필요합니다.
4. 초기 상태는 실제 지원 제출을 비활성화하고, 사용자 승인 대기까지만 수행해야 합니다.
