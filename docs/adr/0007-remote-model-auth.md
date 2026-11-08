# ADR-0007: 원격 GPT 인증·보관·갱신 제안

- 기록일: 2026-11-09 (Asia/Seoul)
- 결정 상태: **Proposed — 사용자 기술 선택 전**
- 구현/배포/가동 상태: **운영 미구현·미배포·미가동**. 비밀 없는 메모리 내 프로토콜 모형만 검증한다.
- 연결 이슈: [#13](https://github.com/silverThunder09/hermes-job-automation/issues/13)
- 선행 결정: [ADR-0006](0006-actions-batch-boundary.md)의 일회성 GitHub-hosted 배치·04시·공개 개발/비공개 운영 경계를 유지한다. 이 문서는 해당 결정을 대체하지 않는다.

## 배경과 요구사항

기존 GPT 계정/구독 경로를 우선 검토하되 현재 대화의 인증을 읽거나 원격으로 복사하지 않는다. 신규 유료 API·자동 과금 fallback·상시 VPS를 도입하지 않는다. PC가 꺼져도 원격 작업을 실행하려면 원격 전용 인증과 회전된 최신 자격증명의 안전한 영속화가 필요하다. 이번 승인은 설계·합성 검증·개발 PR 전달이며, 인증 기술 채택이나 실제 자원/권한 생성 승인이 아니다.

## 공식 근거로 확인한 사실

2026-11-09 KST에 아래 공식 문서와 공개 소스를 재조회했다. HTTP 성공은 실제 로그인·모델 요청·원격 갱신 성공의 증거가 아니다.

| 근거 | 확인 사실과 적용 범위 |
|---|---|
| [Hermes Providers](https://hermes-agent.nousresearch.com/docs/integrations/providers) | `openai-codex`는 Hermes 자체 OAuth 경로이며 **“No Codex CLI installation is required.”** 현재 문서는 ChatGPT/Codex 요금제의 정확한 한도 차감 의미를 **“not currently documented”**로 남긴다. |
| [Hermes auth 소스 고정 revision](https://github.com/NousResearch/hermes-agent/blob/acdc8f1ba65c0231ae8277e846a4d55928913991/hermes_cli/auth_codex.py) | refresh token 회전과 원본 auth 저장소의 re-read→교환→write-back transaction을 확인했다. 같은 파일의 로컬 잠금이지 runner 복사본 사이의 분산 잠금이 아니다. 이 revision은 조사 기준이며 운영 설치 버전 채택은 아니다. |
| [OpenAI Codex CI 안내](https://learn.chatgpt.com/docs/auth/ci-cd-auth) | 일반 CI는 API key를 권장하며, 특별히 Codex 계정이 필요한 신뢰하는 private 자동화에 고급 managed-auth 경로를 설명한다. **generic OAuth clients outside Codex에는 적용하지 않는다.** Hermes에 `CODEX_HOME`, `auth_mode`, 약 8일 refresh 규칙을 그대로 적용하지 않는다. |
| [GitHub Secret 주입 시점](https://docs.github.com/en/actions/reference/security/secrets) | repository secret은 workflow **queued 시점**, environment secret은 해당 environment를 참조하는 **job 시작 시점**에 읽는다. repo Secret+concurrency만으로 대기 중인 오래된 credential 복원을 막을 수 없다. |
| [Secrets REST](https://docs.github.com/en/rest/actions/secrets#create-or-update-an-environment-secret) | 값의 readback/CAS를 제공하지 않으며 조회 metadata는 내용 일치 증명이 아니다. environment secret PUT의 fine-grained 권한은 **Environments: write**다. repository secret의 **Secrets: write**와 다르다. |
| [Variables REST](https://docs.github.com/en/rest/actions/variables#update-an-environment-variable) | environment variable 값의 GET/PATCH가 가능하다. 갱신 권한은 **Environments: write**이며 secret PUT과 원자적 transaction을 구성하는 기능은 확인하지 못했다. |
| [Concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency) | 같은 저장소의 group에만 적용한다. 대기 취소·dispatch 순서 변경이 가능하며 로컬/다른 저장소의 토큰 사용자를 잠그지 않는다. |
| [GITHUB_TOKEN 권한](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions) | workflow의 `permissions`에 Secret writer 권한이 없다. `actions: write`나 `contents: write`로 OAuth Secret 갱신을 대신하지 않는다. |
| [App installation token](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app) | 만료는 1시간이며 설치 범위 안에서 저장소·권한을 축소할 수 있다. App private key라는 장기 bootstrap 비밀은 여전히 필요하다. |

## 비교한 대안

| 대안 | 장점 | 제약·판단 |
|---|---|---|
| **Hermes native `openai-codex`** | 현재 에이전트 경로와 일관되고 별도 Codex CLI가 불필요 | remote credential 이식성·요금제 의미·도구 격리는 미검증. **조건부 추천**, 공식 Codex CI 지원을 받는다고 표현하지 않는다. |
| standalone Codex CLI managed auth | OpenAI가 client 자체 refresh와 ephemeral round-trip을 문서화 | Hermes와 다른 클라이언트·저장 형식이다. 별도 도입 선택과 통합 검증이 필요하다. Hermes 경로 불가 시 재검토하며 자동 전환하지 않는다. |
| 별도 API key | OpenAI가 일반 CI에 권장하는 경로 | 별도 API 과금 경로이므로 현재 우선안에서 제외. 추가 승인 없이 발급/호출하지 않는다. |
| repository Secret의 초기 seed 반복 복원 | 겉보기에는 단순 | queued 시점 stale 값·회전 손실·readback 부재 때문에 **권고하지 않음**. |
| **environment Secret + 전용 App writer + 상태 marker/후속 검증 job** | job 시작 시 최신 주입을 이용하고 GitHub 안에서 관리할 수 있음 | private environment 지원 플랜 확인, 넓은 Environments 권한, 비원자적 저장·추가 검증의 복잡성. **조건부 추천**, 현재 지원/구현됐다는 뜻 아님. |
| fine-grained PAT writer | bootstrap 구현은 비교적 단순 | 사용자 권한·만료 의존. environment 대상이면 동일하게 Environments: write가 필요하며 이름 하나에만 제한할 수 있다고 가정하지 않음. 기본 추천 아님. |
| 별도 versioned secret manager | 값 readback/CAS·외부 직렬화 구현에 유리할 수 있음 | 구체 서비스·OIDC·비용을 비교/승인하지 않았으므로 미선정. GitHub 안의 방식이 관문을 충족하지 못하면 새 ADR로 검토한다. |

## 제안과 이유

**Hermes 전용 원격 로그인 + private 운영 영역의 environment Secret + 전용 GitHub App writer**를 첫 비교안으로 제안한다. 현재 로컬 Hermes/Codex의 토큰 가족과 공유하지 않는 독립 로그인이어야 한다. 별도 로그인들이 서로 독립적으로 유지되는지도 실제 승인된 시험 전에는 보장하지 않는다.

App은 선택한 private 운영 저장소 하나에만 설치하고 installation token도 그 저장소·필요 권한으로 제한한다. environment secret과 비밀 없는 제어 marker에는 **Environments: write**가 필요하다. 이것은 특정 environment/Secret 이름만 쓰는 권한보다 넓고 환경 설정 변경까지 가능한 위험이 있다. 공개 개발 저장소·Contents/Actions write·조직 전체 권한을 요구하는 구성을 피한다. 더 좁은 권한인 것처럼 설명하지 않으며 사용자의 명시적 보안 선택이 필요하다.

설계의 순서·실패/취소·복구·권한 표는 [상세 계약](../REMOTE_AUTH_DESIGN.md#credential-lifecycle)이 소유한다. 최초 실운영 후보는 **합성 고정 요청만 하는 수동 인증 진단**이다. 웹/OCR/개인자료/임의 프롬프트와 쓰기 도구를 해당 인증 진단에 섞지 않는다. 실제 채용 agent와 writer의 OS/작업 격리가 검증되기 전에는 전체 업무에 인증을 제공하지 않는다.

## 결과·비용·미확인 관문

- private environment secrets/variables의 현재 계정 지원·접근 통제를 조회/확인하기 전 운영 대상 생성이나 구현에 착수하지 않는다. 불지원이면 **유료 플랜으로 임의 업그레이드하지 않고 재설계**한다. private required-reviewer 기능이 모든 플랜에 있다고 가정하지 않는다.
- GitHub App key의 보관·분실/철회·교체, owner 목록, installation 범위/만료는 아직 생성·승인되지 않았다. 사용자에게 키를 채팅으로 보내라고 요청하지 않는다.
- 한 번의 model client 호출도 내부 refresh/retry·auxiliary 호출을 만들 수 있다. fallback/외부 로그인 채택/pool/보조 모델을 점검해야 하며, 단순 환경변수 한 개로 사용량·비용 차단을 보장하지 않는다.
- 저장소 비공개는 토큰 파일을 Git에 넣는 허가가 아니다. Secrets의 암호화와 로그 마스킹도 악성 코드에 대한 sandbox가 아니다.
- credential 보관만을 제안한다. 개인 원본·초안·접속 계정 세션의 모델 전송·업로드·보존 정책은 별도 관문으로 유지한다.

## 검증·완료 기준

이번 이슈의 완료는 제안 문서·라우팅·합성 수명주기 모형을 검증하고 개발 PR을 리뷰하는 것이다. [모형 실행과 한계](../REMOTE_AUTH_DESIGN.md#model-verification)를 따른다. 이는 OAuth refresh·GitHub 쓰기·잠금·OS 격리의 실제 구현 검증이 아니다.

사용자 선택 후에만 아래 순서로 별도 구현/실행 승인을 요청한다.

1. private 대상·플랜·App 권한/키 운영·전용 로그인 방식·통신 수신처와 비용 한도를 확정한다.
2. 고정 버전/합성 입력의 수동 remote request, 내장 refresh, 실패·중복·강제 종료를 실증한다.
3. 저장본을 **새 job에서 복원해 값 일치**를 검증하고 이후 run도 최신본을 사용하는지 실증한다. marker 유실·쓰기 timeout에서는 credential 사용이 차단돼야 한다.
4. 임의 입력/도구와 credential·writer의 보안 경계를 검증한 뒤 채용 작업 연결을 별도로 승인받는다.
5. 실제 수동 전체 흐름·비용/누락 감지 검증 후 예약 승인을 별도로 받는다. 예약은 지원 제출 승인이 아니다.

## 되돌리기·재검토·승인 이력

Hermes 원격 이식/갱신, 요금제 적합성, private environment 지원 또는 정확한 round-trip을 증명하지 못하면 **가동 보류**다. 자동으로 CLI/API/VPS로 전환하지 않는다. 실제 노출이면 운영을 멈추고 사용자가 세션·App/key를 철회하는 범위를 확인한다. 원본 계정/DB/자료는 이 작업에서 변경·삭제하지 않는다.

사용자는 2026-11-09 상세 설계와 비밀 없는 모의 검증 진행을 요청했다. **위 기술 선택의 채택은 아직 미승인**이며 이 문서의 병합으로 Accepted가 되지 않는다.
