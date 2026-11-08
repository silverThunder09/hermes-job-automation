# 원격 GPT 인증 상세 설계 — Proposed

> **설계안이며 실행 가이드/활성 workflow가 아니다.** 기술 선택은 [ADR-0007](adr/0007-remote-model-auth.md), 확정된 호스트·시각·격리 경계는 [ADR-0006](adr/0006-actions-batch-boundary.md)가 소유한다. 현재 인증·운영 저장소·App·Secret·예약은 만들지 않았다.

## 1. 계정과 실행 경로

```text
현재 로컬 Hermes 로그인 ── 현재 로컬 대화 (이 작업에서 읽거나 복사하지 않음)
원격 전용 Hermes 로그인 ── 전용 HERMES_HOME/auth.json ── openai-codex ── GPT
                           ↑ 최신본 복원 / 갱신된 전체 bundle 반영 ↓
                      private 운영 environment Secret
```

- 같은 GPT 계정 사용과 **같은 회전 token 가족 복제**는 다르다. 전용 로그인을 별도로 만들고 로컬과 공유하지 않는 안이다. 로그인 coexistence/구독 자격/전송 허용은 승인된 실증 전 미확인이다.
- `hermes auth add openai-codex`의 초기 브라우저 승인은 사용자 참여가 필요하다. headless device-code 지원을 무인 최초 로그인으로 표현하지 않는다. 실제 로그인은 이번 범위 밖이다.
- 새 `HERMES_HOME`에는 필요한 provider 한 개와 전용 인증만 둔다. 기본 프로필·다른 계정·pool·로컬 설정을 통째로 업로드하지 않는다. 홈 분리는 경로 분리이지 악성 agent의 sandbox가 아니다.
- 공식 키 기준으로 명시적 `model.provider: openai-codex`, `auth.adopt_external_logins: false`, 빈 `fallback_providers`, legacy `fallback_model` 부재를 요구한다. auxiliary/vision/delegation 모델·플러그인·환경변수·추가 credential pool의 우회 경로도 별도로 검증한다. 이것은 미래 구성 검증 계약이며 현재 설정을 수정했다는 뜻이 아니다.
- GPT 호출과 Actions 실행량·저장 비용은 별개다. 한도 소진/사용량 불명 시 유료 API·다른 계정으로 넘어가지 않고 정지한다. 모델 이름이나 요금제 한도를 임의 확정하지 않는다.

<a id="credential-lifecycle"></a>
## 2. 인증 수명주기 계약

추천 저장 후보는 **private environment Secret**이다. repository Secret은 queued 시점의 값이 될 수 있으므로 토큰 저장 위치로 대신하지 않는다. GitHub Secrets는 읽기 API/CAS가 없으며, 전체 bundle+제어 marker를 원자적으로 갱신해 주지도 않는다.

| 객체 | 제안 내용 | 경계 |
|---|---|---|
| 인증 bundle | 전용 Hermes가 최종 저장한 전체 auth JSON, 형식/크기 확인 후 Secret의 공개키로 암호화하여 저장 | Git·cache·artifact·job output·로그·PR·채팅 금지. 48 KB 제한과 encoding 증가분을 실측해야 함 |
| 제어 marker | environment variable에 `state`, 고유 `run_id`, 승인 코드 버전, credential generation, 기대 값의 SHA-256 fingerprint 등 비밀 없는 제어 정보 | token/계정/개인자료는 넣지 않음. fingerprint도 private 제어 기록만 사용하며 출력/공개하지 않음. plaintext 변수는 비밀 저장소가 아님 |
| 복원 홈 | 해당 job만의 임시 `HERMES_HOME`; directory 0700/file 0600을 요구 | 권한 숫자만으로 같은 UID의 악성 프로세스를 격리하지 못함. 실제 권한·프로세스 경계 검증 필요 |
| 배타 실행 | 한 private 저장소의 모든 인증 소비/갱신/검증 workflow에 **동일한 고정 concurrency group**, `cancel-in-progress: false` | workflow 이름·branch로 group을 분리하지 않음. 외부 client/다른 저장소는 이 lock의 보호 밖이므로 같은 bundle 사용 금지 |

상태는 `ready → in_flight → pending_write → pending_validation → ready`다. quota는 검증 후 `paused_quota`, 업무 실패는 `paused_error`로 끝낸다. 모든 non-ready/missing/unreadable marker는 일반 모델 호출을 막는다. 준비되지 않은 marker를 자동 초기화하지 않는다.

### 순서와 각 단계의 완료 증거

1. **승인된 대상·신뢰 코드 확인:** private 저장소·environment·App installation·정확한 코드 SHA와 허용 수동 이벤트를 allowlist로 확인한다. public PR/fork/임의 ref/임의 prompt·`pull_request_target`/외부 artifact는 credential 경로에 진입시키지 않는다. action/클라이언트도 검토한 immutable 버전에 고정하고 비용·timeout을 확인한다.
2. **배타 실행 확보:** workflow-level group을 획득한 뒤 environment를 참조하는 job이 시작돼야 한다. environment secret의 job-start 주입을 실증한다. repository-secret 중복 이름/우선순위와 오래된 queued 입력은 사용하지 않는다. 현재 Secret의 generation/내용 fingerprint가 최신 제어 기록과 맞지 않으면 client를 시작하지 않는다.
3. **durable `in_flight` 선기록:** 제어 variable을 REST로 최신 조회하고 직전 `ready`·owner/generation을 확인한다. 고유 run marker를 기록하고 **정확한 값 재조회**가 끝난 뒤에만 credential을 사용할 수 있다. marker 쓰기/조회 실패는 모델 호출 전 정지다. lease의 시간 경과만으로 stale owner를 승계하지 않는다. GitHub에 CAS가 있다고 가정하지 않으며 지정된 단일 writer와 repository-wide 직렬화를 깨는 수동 변경도 중단 대상으로 본다.
4. **복원·고정 합성 요청:** Secret을 전용 홈에 복원하고 허용된 auth schema·provider/pool 수·권한을 확인한다. 고정 비개인 요청 하나로 native client를 실행한다. 직접 OAuth refresh endpoint를 호출하지 않는다. 이번 초기 인증 진단에는 사이트·첨부·원본 이력서·shell/browser/쓰기 도구·임의 사용 입력을 제공하지 않는다. 실제 tool-disable 동작을 검증하기 전 실행하지 않는다.
5. **클라이언트 종료·갱신본 수집:** child process tree가 끝난 뒤 Hermes가 남긴 최종 bundle을 다시 검증한다. 업무 성공과 인증 상태를 구분한다. quota/업무 실패라도 인증이 유효하게 갱신됐다고 확인할 수 있으면 그 최종본의 저장 절차는 진행하되 업무를 재시도하지 않는다. auth failure·취소·판별 불명은 성공으로 저장하지 않고 차단/수동 복구한다.
6. **write-back:** private 제어 marker를 `pending_write`와 고유 owner/기대 generation·fingerprint로 갱신하고 재조회한다. writer는 **같은 최종 bundle**만 allowlist 대상 Secret에 PUT한다. `201/204`는 수락 증거일 뿐 값 일치 증거가 아니다. 수락 후 marker를 `pending_validation`으로 기록한다. client 재호출/새 refresh를 포함한 일반 retry는 하지 않는다.
7. **새 job의 실제 값 검증:** writer job이 끝난 뒤 **같은 workflow-level lock 안의 후속 environment job**이 Secret을 새로 주입받는다. 여기서는 client를 실행하지 않고 복원한 **실제 bytes의 fingerprint**·구조/generation을 기대 기록과 대조한다. 이 job에는 원래 seed·이전 job의 Secret snapshot·candidate를 넘겨 검증을 대체하지 않는다. `updated_at`/PUT 응답만으로 통과시키지 않는다. 환경 Secret의 다음 job 반영을 실제로 확인하지 못하면 가동 불가다.
8. **종료 commit:** 검증 job만 정확한 owner/기대 값이 일치할 때 marker를 `ready`/`paused_quota`/`paused_error`로 갱신하고 재조회한다. READY 기록의 응답이 불명확하면 marker의 실제 값을 다시 확인하며 credential refresh부터 반복하지 않는다. 중간 marker·검증 실패는 다음 일반 run을 계속 차단한다. `if: always()`는 종료 기회일 뿐 강제 종료 시 실행 보장이 아니다.

제어 variable/Secret의 원자성·즉시 반영을 가정하지 않는다. 토큰을 쓰기 **전** 남긴 durable non-ready marker가 실패와 강제 종료 후의 안전 장치다. 제어 plane이 유실되거나 권한 있는 외부 actor가 marker를 바꾼 경우의 안전성은 이 프로토콜만으로 보장하지 않는다. 통제된 단일 writer가 깨지면 운영을 보류한다.

## 3. 권한·키·도구의 격리

| 주체 | 필요한 접근 제안 | 주면 안 되는 접근/남은 조건 |
|---|---|---|
| 현재 공개 개발 CI | 기존 fixture/테스트 권한만 | 실제 auth/개인자료/App key/ops writer 없음 |
| private 인증 진단의 model child | 전용 provider의 임시 auth, 고정 합성 입력 | App key·installation token·기존 API key·다른 pool을 환경으로 상속하지 않음. 도구 비활성화 확인 필요 |
| 신뢰 wrapper/writer·검증 controller | private 대상 한 저장소의 App installation token, environment Secret/variable의 지정 endpoint | endpoint·이름 allowlist를 코드에서 고정. 이는 App 자체의 이름별 권한 제한을 뜻하지 않음 |
| App bootstrap | 장기 private key를 승인된 Secret 경계에 보관, 필요한 때만 token 발급 | 설치/권한/키 교체·철회·만료 경보·owner 지정 승인 필요. private key를 auth bundle과 합치거나 model child에 제공하지 않음 |
| 기본 `GITHUB_TOKEN` | 가능한 경우 `contents: read` 등 개발/checkout 최소 권한 | **Secret writer가 아님**. `actions: write`로 대체하지 않음. checkout credential 지속 저장도 피함 |

환경 Secret/variable writer는 **Environments: write**가 필요하다. repository Secret writer의 **Secrets: write**를 잘못 요청하지 않는다. App/PAT 모두 이름 하나에만 제한된 writer라고 주장하지 않는다. App 설치·mint 범위는 한 private 저장소로 한정하며 앱을 새로 만들거나 토큰을 발급한 적은 없다.

별도 step·별도 환경변수만으로 같은 runner UID에서 악성 코드 접근을 막을 수 없다. 초기 고정 합성 진단은 **신뢰하는 client와 wrapper**만 실행하는 범위다. 실사이트/문서 내용을 처리하는 agent는 prompt injection으로 도구·파일을 악용할 수 있으므로, host writer/credential broker와 도구 영역의 실제 OS/작업 격리 및 인증 전달 경계를 별도로 설계·검증하기 전 연결하지 않는다. 현재 `HERMES_HOME` 분리나 이 문서가 그 격리를 구현하지 않는다.

App private key가 노출되면 짧은 installation token만 만료시켜도 복구가 끝나지 않는다. 사용자 범위 승인 후 key/installation/해당 로그인 세션을 철회·재등록하고 기존 snapshot을 자동 복원하지 않는 복구 절차를 실증해야 한다. 로그의 token/JSON 자동 마스킹을 신뢰하지 않고 shell tracing·환경 dump·raw 응답·auth 파일 내용/해시 출력을 피한다.

## 4. 실패·한도·수동 복구

| 사건 | 안전한 결과 |
|---|---|
| trust/lock/marker 확인 실패 | model client 호출 0, credential 사용 전 정지 |
| 다른 owner/old generation/중간 marker 발견 | stale seed로 진행하지 않음. 단순 TTL 만료나 job 종료로 READY 초기화 금지 |
| native refresh 실패·만료/철회·terminal 401 | 다른 token/계정으로 replay하지 않음. 전용 세션의 사용자 재인증 필요. client 자체 bounded recovery와 wrapper 무한 retry를 구분 |
| 429/구독 한도 | 유효 갱신본은 저장·실제 값 검증 후 `paused_quota`; 유료 API·다른 계정·즉시 retry 없음. reset/사용량 확인과 재개 권한 필요 |
| 업무 실패, 인증 bundle은 유효 | 최종 인증 저장을 업무 rollback과 분리하고 `paused_error`로 정지 |
| Secret PUT 실패/timeout·ack 유실 | 저장되지 않았다고 단정하거나 refresh를 다시 하지 않음. durable non-ready marker 유지, 동일 대상의 확인·안전한 재저장/재인증은 수동 복구 승인 후 |
| 후속 job 값 불일치/metadata만 존재 | 정상 저장으로 보고하지 않음. `pending_validation` 또는 차단 상태 유지 |
| 강제 종료·runner 소실 | 선기록한 marker로 다음 모델 호출 차단. `always()`/로컬 파일/기존 seed에 의존하지 않음 |
| 제어 기록 unavailable/유실 | 복원 가능한 인증처럼 보여도 사용하지 않음. 전용 stream을 중지하고 owner/marker/최신 bundle 일치부터 검토 |

복구는 해당 stream을 멈추고 실제 run/marker/Secret metadata를 확인하는 것부터 시작한다. Secret metadata만으로 token 최신성을 복구할 수 없다. 최신 후보가 소실됐으면 사용자 승인 하에 전용 신뢰 환경에서 재인증하고 새 bootstrap과 round-trip을 검증한다. 원본 로컬 로그인·DB·개인 파일을 덮어쓰거나 삭제하지 않는다. 임시 인증 홈의 폐기 대상/시점·로그 보존·키 회전 정책도 운영 승인에 포함하며 이번 작업에서 실제 삭제하지 않는다.

<a id="model-verification"></a>
## 5. 비밀 없는 모형 실행과 한계

```bash
python -m pytest -o addopts= -q tests/test_auth_lifecycle_model.py
python -m pytest -o addopts= -q tests/test_agent_routing.py
```

[scripts/auth_lifecycle_model.py](../scripts/auth_lifecycle_model.py)는 메모리의 integer generation·state·top-level client 호출 횟수만 다룬다. 실제 token·OAuth·env·파일 저장·네트워크·subprocess를 사용하지 않는다. [테스트](../tests/test_auth_lifecycle_model.py)는 정상 round-trip, trust/lease 거부, in-flight 충돌/중단, PUT 실패·적용 전/후 ack 유실, stale/불일치/새 소비자가 아닌 검증, quota/업무 실패, auth 실패·취소, 불법 전이를 검사한다.

모형의 `trusted`, `lease`, `exact_match`, `fresh_consumer`는 **관찰된 보안 속성이 아니라 가정한 입력**이다. 실제 adapter는 trust/lease를 확보하고 새 job의 bytes를 대조해야 한다. integer generation은 credential 변화의 모형이지 분산 fencing/CAS 구현이 아니다. owner/generation 위조·다중 프로세스·실제 lock·제어 variable 내구성·GitHub 반영 시점·암호화·권한·OS 격리는 이 테스트로 증명되지 않는다. `model_calls=1`은 top-level 호출 횟수이며 HTTP 요청/토큰/과금 횟수가 아니다. 기본 `ready`도 사용자 승인된 bootstrap 완료를 가정하며 실서비스 기본 허용 정책이 아니다.

## 6. 운영 구현 전 선택·실증 관문

- 사용자가 ADR-0007의 **클라이언트·저장소·App 권한**을 선택한다. private environment의 실제 요금제 지원이 없으면 유료 전환하지 않고 재설계한다.
- private 대상 이름/접근자·App key 관리·별도 로그인·구독 자격/사용량·수신처·timeout/재시도·budget 차단을 확정한다. API key 없는 것만으로 항상 무료라 하지 않는다.
- bootstrap→native request/refresh→write-back→**후속 job의 실제 값 대조**→다음 run까지 실증한다. Secret 값 readback은 REST metadata가 아닌 승인된 새 consumer에서만 수행한다.
- 동시 run·queued 오래된 값·marker 쓰기 실패·강제 종료·token 철회·PUT timeout을 주입하고 실제 다음 client 호출이 차단되는지 검증한다.
- 실제 도구/개인자료 연결·원격 파일 보존·예약 등록·최종 지원 제출은 각각 별도 승인을 유지한다. 모형/CI 통과로 관문을 자동 통과시키지 않는다.

## 공식 참조

인증/CI/권한의 비교 근거는 [ADR-0007의 공식 근거 표](adr/0007-remote-model-auth.md#공식-근거로-확인한-사실)를 따른다. 추가로 [Hermes fallback 설정](https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers), [Hermes 보안 모델](https://hermes-agent.nousresearch.com/docs/user-guide/security), [GitHub environment 보호·제약](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)을 확인한다. 공식 설명의 현재 동작과 프로젝트의 Proposed 통제를 구분한다.
