# Cloud development and runtime

## 무엇이 준비되어 있나

이 저장소는 개인 이력서·포트폴리오·인증정보 없이 코드를 개발·테스트하기 위한 저장소입니다.

- `.devcontainer/`: GitHub Codespaces / VS Code Dev Containers용 Python 3.11, Chromium, 한국어 PDF 폰트 설정
- `.github/workflows/ci.yml`: Ubuntu·Windows에서 패키지 설치, 컴파일, 로컬 fixture 테스트
- `skills/job-search`, `skills/job-tailoring`: Hermes 작업 절차
- `profile.example.json`, `.env.example`: 빈 입력 템플릿. 실제 데이터와 토큰은 저장소에 커밋하지 않음

**GitHub에 올린 것과 실제 채용 자동화를 배포한 것은 다릅니다.** 이 설정은 클라우드 개발용이고, 유료 Codespace·Hermes Cloud 인스턴스 생성이나 매일 수집 예약을 자동으로 실행하지 않습니다.

## 1. 서버 없이 브라우저에서 개발: Codespaces

1. GitHub 저장소에서 **Code → Codespaces → Create codespace on main**을 선택합니다.
2. Dev Container 빌드와 `postCreateCommand`가 Python 패키지·Chromium을 설치합니다. 설치에는 네트워크가 필요합니다.
3. 환경이 준비되면 터미널에서 실행합니다.

```bash
python -m pytest -o addopts='' -q
python -m hermes_job_automation.cli health
```

실제 평가를 할 때만 `profile.example.json`을 `profile.json`으로 복사해 원문으로 확인한 사실을 입력합니다. 필요한 연결값은 Codespaces secrets 또는 로컬 `.env`에 별도로 설정합니다. 테스트만 할 때는 로그인·키·개인 이력서가 필요하지 않습니다.

Codespaces는 개발환경이며 유휴 중지/사용량 정책이 있습니다. 이를 매일 정시에 돌아가는 상시 운영 서버라고 가정하지 않습니다. 생성과 과금/무료 할당량 확인은 사용자가 GitHub에서 결정합니다.

## 2. Hermes Cloud: 별도 VPS를 직접 구매할 필요 없음

이 절은 **선택적 Cloud 대안의 조사·설치 예시**입니다. 이번에 선택한 PC-off 방식은 아래 GitHub Actions 배치이며 이 Cloud 인스턴스는 필수도, 이미 가동된 자원도 아닙니다.

공식 문서는 **Hermes Cloud가 hosted Hermes Agent instances를 제공**하고, Nous Portal의 `/agents`에서 관리한다고 설명합니다. 따라서 Hermes Cloud 이용권한이 있다면 AWS EC2/VPS를 따로 만들어 Hermes를 설치할 필요는 없습니다.[1]

필요한 것은 다음과 같습니다.

- Hermes Cloud 접근권한이 있는 Nous Portal 계정과 인스턴스
- 해당 인스턴스에서 비공개 GitHub 저장소에 접근할 권한
- 사용할 모델의 실제 인증/사용권한 및 필요한 도구 설정
- 개인 프로필·결과 파일의 비공개 저장소와 백업 계획

Nous Portal의 **모델/Tool Gateway 구독**, **클라우드 브라우저**, **클라우드 터미널 sandbox**와 **Hermes Cloud 에이전트 인스턴스**는 개념을 구분해야 합니다. Portal 문서는 모델/검색/브라우저를 설명하지만, 모델 구독이 모든 클라우드 인스턴스 비용을 포함한다고 단정하지 않습니다. Cloud 권한·인스턴스 비용은 Portal에서 확인합니다.[1][2]

Cloud 인스턴스가 준비된 뒤의 프로젝트 설치 예:

```bash
gh repo clone silverThunder09/hermes-job-automation
cd hermes-job-automation
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m playwright install --with-deps chromium
# Debian/Ubuntu: 필요시 sudo apt-get install fonts-nanum
python -m pytest -o addopts='' -q
```

Cloud 이미지에 `gh`나 `python3-venv`, sudo 권한이 없다면 먼저 해당 환경의 관리 방법으로 설치/접근을 구성합니다. 위 명령이 Cloud의 모든 이미지에서 검증된 것은 아닙니다. 저장소와 CI는 준비하지만 Cloud 인스턴스와 인증은 별도 확인이 필요합니다.

Hermes에는 저장소의 `skills/job-tailoring/SKILL.md`를 읽고 지정 공고와 첨부 자료를 처리하도록 요청합니다. 스킬 파일이 저장소에 있다는 사실이 사용자 홈의 Hermes 스킬 목록에 자동 설치됐다는 뜻은 아닙니다. 프로젝트 기본 모델 이름을 로컬에 지정한 것만으로 Cloud 인증까지 이전되지도 않습니다.

## 3. PC가 꺼져도 매일 실행

선택한 실행 방식·시간대·격리 경계는 [ADR-0006](adr/0006-actions-batch-boundary.md)입니다. 로컬 PC를 켜 두거나 별도 상시 서버를 마련하는 대신 GitHub-hosted runner를 작업마다 시작·종료하는 배치를 사용합니다. **선택한 방향과 실제 가동 완료는 다릅니다.**

| 방식 | 직접 서버 마련 | 운영 책임 |
|---|---|---|
| GitHub Actions 일회성 배치 — 선택한 방향 | 별도 상시 서버 불필요 | 04:00 Asia/Seoul 목표. 비공개 운영 영역·인증 보존/갱신·영속 저장·비용 차단·지연/누락 처리의 검증과 가동 승인 필요 |
| Hermes Cloud — 선택적 대안 | 별도 VPS 불필요 | Cloud 인스턴스·인증·저장·Gateway/Cron 동작 확인 |
| 직접 설치한 상시 Hermes — 현재 선택하지 않음 | 상시 켜진 PC 또는 VPS 필요 | OS·Hermes·보안·백업·서비스 재시작 직접 관리 |

공개 소스·합성 개발 CI와 인증/개인자료를 사용하는 비공개 운영 영역을 분리합니다. 새 운영 저장소 생성·로그인/Secrets 등록·개인자료 전송·지원·예약 가동은 이번 설계 결정에 포함되지 않습니다. 민감 파일은 비공개 Git에도 커밋하지 않습니다. 모델 클라이언트와 인증 방식 등 미결정 항목은 ADR의 관문을 따릅니다.

자동 수집·평가 예약은 플랫폼 허용 범위와 실제 비제출 전체 경로를 확인한 후 별도 승인으로 등록합니다. 현재 이 공개 저장소의 Actions는 **테스트용**이고 운영 배치·실제 공고 수집/지원 일정은 없습니다. GitHub 예약은 정각 보장이 아닌 best-effort이며 runner 디스크는 종료 후 사라집니다. 현재 개발 CI의 Chromium 성공을 원격 모델·계정·개인자료 또는 전체 MVP 완료로 확대하지 않습니다.

## 4. 현재 기능의 클라우드 경계

- **PDF 문서 생성:** Windows 맑은 고딕 또는 Linux Nanum Gothic TrueType 폰트를 검색합니다. 별도 경로가 필요하면 `JOB_ASSIST_PDF_FONT`를 지정할 수 있습니다.
- **로컬 OCR:** `ocr-image`는 Windows.Media.Ocr용이므로 Linux Codespaces/Hermes Cloud에서 그대로 실행되지 않습니다. Linux OCR 엔진 또는 Hermes 비전 경로의 추가 연결·검증이 필요합니다. 저장소 업로드가 이 제한을 해소하지 않습니다.
- **브라우저:** Python Playwright와 Hermes `browser_exec`는 서로 다른 실행 경로입니다. 전자의 설치가 후자의 Cloud 브라우저 인증을 구성하지 않습니다.
- **평가 모델:** Hermes 모델 경로와 Python의 OpenAI API 직접 호출 경로는 별개입니다. 인증·모델 접근 여부를 각각 확인합니다.
- **지원자 조건 필터:** 현재 `eligibility.py`는 서울·경기·인천/정규직·인턴/학력·경력의 고정 규칙입니다. 빈 예시 프로필로 범용 자동 필터가 되는 것은 아닙니다.
- **실제 지원:** CLI의 `--execute`는 Sheets/Drive/Telegram 기록 허용이며, 사이트별 자동 제출 통합 기능이 아닙니다. 기본 자동 제출은 계속 비활성입니다.

## 5. 개인정보와 인증

`profile.json`, `.env`, `data/`, `generated/`, `logs/`, `work/`, OAuth 토큰·서비스 계정 키는 Git 및 Docker build context에서 제외합니다. 원본 포트폴리오와 회사별 수정본은 PC에 그대로 보존하고 GitHub에는 업로드하지 않습니다.

클라우드에서 실제 문서를 처리하려면 사용자가 승인한 경로로 필요한 파일만 전송합니다. 개발에 필요한 코드와 채용 지원자 개인정보의 보관을 분리합니다. GitHub 저장소를 비공개로 만들어도 비밀정보를 커밋해도 된다는 의미는 아닙니다.

## Sources

[1] https://hermes-agent.nousresearch.com/docs/guides/manage-hermes-cloud-with-mcp
[2] https://hermes-agent.nousresearch.com/docs/integrations/nous-portal
