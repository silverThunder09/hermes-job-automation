# Supabase 재사용 기반 GPT 인증 상세 설계 — Proposed

> 현재 우선 검토안은 [ADR-0008](adr/0008-supabase-auth-reuse.md)이다. **기술 선택·최소권한 접점·운영 구현은 미승인/미구현**이며 이 문서는 활성 설정이나 실행할 SQL이 아니다. 이전 [GitHub 보관안](REMOTE_AUTH_DESIGN.md#credential-lifecycle)은 비교 이력으로 보존한다.

## 1. 무엇을 재사용하고 무엇을 추가하나

| 객체 | 위치·역할 | 현재 상태 |
|---|---|---|
| 공고·적격성·평가·지원 상태·실행 기록 | 기존 Supabase 업무 테이블 | 기존 앱 경로. 업무 상태 저장이 로그인 저장은 아님 |
| 원본/생성 문서 | 별도 파일 처리·보존 경계 | Vault나 업무 JSONB에 넣는 대상으로 승인하지 않음 |
| GPT 원격 전용 로그인 bundle | 후보: 같은 Supabase 프로젝트의 Vault | 실제 Vault 사용 가능 여부·권한·저장 미검증 |
| credential owner·version·중간 상태 | 후보: 권한 제한 인증 제어 테이블 | 새 설계/버전 SQL 필요. 일반 실행 로그와 분리 |
| 최초 Supabase 접속 자격 | DB 외부의 승인된 비밀 전달 경로 | bootstrap 종류·권한·만료·등록은 미선정/미승인 |

줄일 수 있는 것은 **OAuth 갱신본을 GitHub에 쓰는 App/PAT·App private key·Secret 후속 주입 대조 구성**이다. DB에 처음 접속하는 자격, private 운영 영역, provider 갱신과 실패 차단, 도구 격리는 없어지지 않는다. repository Secret 등으로 bootstrap을 전달하더라도 교체 시 stale queued run 처리와 철회가 필요하다. 기존 서버 키 재사용이나 모든 Secret 제거를 뜻하지 않는다.

새 저장 서비스를 추가하지 않아 외부 운영 구성을 줄일 수 있지만 전용 DB 권한/함수·transaction·복구 개발은 늘어난다. 같은 DB 장애나 관리자 권한 침해가 업무와 인증 양쪽에 영향을 줄 수 있다. 별도 schema만으로 물리적 격리가 생기지 않는다. Supabase 기능/용량/비용 확인 전 항상 무료라고 보장하지 않는다.

<a id="access-boundary"></a>
## 2. 접근·암호화·bootstrap 경계

Vault는 암호화 저장과 권한 있는 SQL의 복호화 조회/갱신 기능을 제공한다. **Vault 설치만으로 원격 전용 API·CAS·lease·역할별 접근이 자동 구성되지 않는다.** 현재 앱의 Data API factory와 업무 RPC도 Vault adapter가 아니다.

- 기존 `SUPABASE_SECRET_KEY`는 `service_role`/BYPASSRLS로 동작한다. 새 이름의 secret key도 좁은 DB role이 되지 않는다. 기존 업무 table grant를 함께 갖는 키를 model/도구에 주지 않는다. RLS만으로 이 키를 제한했다고 표현하지 않는다.
- **구체 접근 접점은 미선정**이다. 전용 DB role의 제한된 SQL 접근 또는 제한된 신뢰 서버 접점/RPC의 권한·bootstrap을 비교한 뒤 사용자 선택을 받는다. 접속 password/JWT/서버 secret 종류를 임의 채택·발급하지 않는다.
- 어떤 경로든 고정 credential 식별자·필요한 함수만 허용한다. 전체 Vault/schema/복호화 view의 원격 공개, 임의 secret ID/SQL 실행·광범위 table 직접 권한을 피한다. anon/일반 authenticated 사용자에게 credential 조회를 허용하지 않는다.
- 기존 업무 RPC의 SECURITY INVOKER 정책은 유지한다. 새 제한 함수가 DEFINER를 필요로 한다면 별도 보안 선택이며 owner 최소권한·빈 search_path·완전한 객체 이름·PUBLIC/anon 및 직접 부여 EXECUTE 회수·반환 범위/호출자 확인을 모두 검증한다. 현재 정책을 이 문서로 바꾸지 않는다.
- DB 최초 접속 자격을 **Vault 안에만** 보관하면 처음 꺼낼 수 없다. 외부 bootstrap 비밀 전달·만료/교체·철회·사용자/작업 범위를 정해야 한다. bootstrap 종류 확정 전 실행하지 않는다.
- Vault의 root encryption key 운영·백업/복구·관리자 접근을 확인한다. root key를 runner로 복사하거나 애플리케이션이 직접 암호화 키를 관리하는 방식을 전제하지 않는다. 허용된 복호화 view 사용자는 평문을 읽을 수 있으므로 암호화가 관리자 접근까지 차단한다고 보장하지 않는다.
- 인증 controller는 DB bootstrap과 상태 접근을 소유하고, model child에는 원격 전용 provider bundle만 최소 전달하는 경계를 설계한다. 같은 UID·환경변수 분리·별도 step·HERMES_HOME만으로 악성 프로세스를 격리하지 못한다. 실제 OS/작업 경계·자식 종료·로그 통제 검증 전 실사이트/첨부/임의 tool 입력을 연결하지 않는다.

<a id="credential-lifecycle"></a>
## 3. 갱신·저장·재조회 계약

```text
승인된 private 일회성 실행기
  → 외부 bootstrap으로 제한된 인증 접점 접근
  → DB에서 최신 version/상태 확인 + durable in-flight 선기록
  → Vault의 최신 원격 전용 bundle 복원
  → Hermes 자체 openai-codex 실행·내장 refresh
  → owner/예상 version 검증 + Vault 최종본/상태의 DB transaction
  → 별도 읽기로 실제 최종 값·version·상태 대조
  → ready 또는 paused 상태 확정
```

1. **신뢰/대상 확인:** 승인된 private 대상·정확한 코드/클라이언트/action 버전·고정 비개인 요청·한도/timeout을 확인한다. 공개 개발 CI, fork/임의 revision, 임의 프롬프트·외부 artifact에는 실제 credential을 주지 않는다. 최초 수동 진단은 tool-disable을 검증한 합성 입력만 사용한다.
2. **single owner 선확보:** DB 안의 단일 실행 소유권과 `ready`/예상 version을 확인하고 고유 실행 식별자의 durable `in_flight`를 기록한다. 성공·정확한 읽기 확인 후에만 provider credential을 사용한다. 누락/조회 불가/non-ready/다른 owner는 중단한다. GitHub concurrency는 보조 통제이며 서로 다른 client 복사본의 분산 잠금을 대신하지 않는다.
3. **최신본 복원/실행:** 좁은 접점에서 해당 owner에게만 최신 bundle과 일치하는 version을 전달한다. 전용 `HERMES_HOME`·provider/pool/schema·파일 권한을 확인한다. 로컬 기본 Hermes/Codex 로그인과 token 가족을 공유하지 않는다. 직접 refresh endpoint를 구현하지 않고 Hermes 자체 갱신을 사용한다. provider/fallback/외부 로그인 채택과 보조 모델 통제는 [기존 인증 경로의 제한](REMOTE_AUTH_DESIGN.md#1-계정과-실행-경로)을 유지한다. 실제 이식성·독립 로그인·구독 한도는 별도 실증 대상이다.
4. **종료 후 저장 후보 확인:** client/자식이 끝난 뒤 최종 bundle을 수집한다. 업무 성공과 유효 인증 갱신을 구분한다. quota/업무 실패라도 최종 인증이 유효하게 갱신된 것으로 확인되면 저장 절차는 진행하되 업무를 재시도하지 않는다. terminal auth failure·취소·판별 불명은 차단한다.
5. **DB 안의 원자적 갱신:** 고정 함수가 활성 owner/예상 version/허용 state를 확인하고, Vault 갱신과 인증 제어 레코드 갱신을 같은 transaction으로 묶는 안이다. 중복/이전 owner/이전 version 저장은 거부해야 한다. 이것은 앞으로 구현할 조건부 갱신이지 `vault.update_secret()` 자체에 CAS가 있다는 뜻이 아니다. token 내용이나 name을 임의 정규화하지 않는다.
6. **독립 readback과 상태 확정:** ACK/updated_at/version만 믿지 않는다. 별도 읽기에서 같은 credential의 실제 최종 값·version·owner/상태를 기대한 후보와 대조한다. 내용은 내부에서만 비교하고 로그/보고는 판정만 남긴다. 재조회 전에는 다음 일반 실행을 허용하지 않는다. 조건부 상태 확정/응답 불명 처리도 정확한 대상 재조회로 조정한다.

**DB transaction은 외부 OpenAI/Hermes refresh를 rollback하지 못한다.** refresh 이후 DB 저장 실패/timeout이 나면 token이 이미 회전했을 수 있다. DB 상태를 되돌렸다는 이유로 이전 token을 재사용하지 않는다. 사용 전 남긴 durable non-ready marker가 다음 실행을 차단해야 하며, lease 만료/job 종료만으로 자동 승계/READY 초기화하지 않는다. DB 저장/readback 성공 전 owner의 오래된 후보를 수락하지 않는지 실증해야 한다.

## 4. 실패·복구·보존

| 사건 | 제안하는 결과 |
|---|---|
| bootstrap/대상/marker/권한 확인 실패 | provider client 호출 전 중단. 넓은 키나 로컬 로그인으로 우회하지 않음 |
| 동시 실행·stale version·다른 owner | 하나만 사용권 획득, 나머지 거부. 사용 중이거나 사용 결과 불명인 token을 TTL만으로 재할당하지 않음 |
| 외부 refresh 뒤 저장 실패·ACK 유실 | 오래된 seed 복원/새 refresh retry 금지. durable non-ready 유지, 후보/실제 저장본 확인 후 승인된 수동 복구 |
| client/runner 강제 종료 | `always()`/로컬 임시 파일 정리에 의존하지 않음. 선행 DB marker로 다음 사용 차단 |
| terminal 401/만료/철회 | 전용 세션의 사용자 재인증 관문. 다른 계정/유료 API 자동 전환 없음 |
| quota/429·업무 실패 | 유효 갱신본을 저장·실제 값 대조한 뒤 각각 paused 상태. 사용량/reset/재개 정책 확인 전 즉시 재시도 없음 |
| DB 장애·제어 레코드 유실·값 불일치 | credential이 있어 보여도 실행하지 않음. fail-closed 상태와 수동 조정 필요 |
| 키/credential 노출 | 사용 중단 후 사용자 승인 범위에서 해당 키/세션 철회·재등록. 단순 DB ciphertext 변경을 전체 복구로 보지 않음 |

토큰 값·bootstrap·auth 파일/내용 fingerprint를 Git/로그/PR/업무 report JSON·cache/artifact·HTTP/SQL 오류에 노출하지 않는다. parameter binding만으로 모든 로그 유출이 해결됐다고 가정하지 않는다. 비밀 없는 제어 정보와 provider bundle을 구분하고 SQL/HTTP/SDK/진단 로그를 실제 검사해야 한다. 원본 DB/자료/로그인을 보존하며 token·임시 파일·backup의 보존/폐기 정책은 별도 승인한다.

## 5. 검증·구현 경계

이번 PR은 새 SQL·adapter·key·Vault 연결·실제 OAuth 시험을 포함하지 않는다. 기존 [메모리 모형](../scripts/auth_lifecycle_model.py)도 변경하지 않는다. 그 모형의 trust/lease/value-match는 가정한 입력이며 실제 PostgreSQL/Vault 원자성·권한·내구성 증거가 아니다. 문서 계약은 링크/앵커·현재 우선안 발견·이전 Proposed 이력 보존을 검증할 뿐이다.

구현 선택 후 필요한 증거:

- Vault 사용 가능 여부·root key/backup 복구·실제 대상·비용/한도, bootstrap 종류/만료/철회를 확정한다.
- 승인된 버전 SQL을 격리 환경에 적용하고 재실행·권한 음성 검사·owner/version 경쟁·transaction rollback·restart 후 marker를 실제 검사한다. 일반 PostgreSQL만의 성공을 Vault extension 검증으로 대체하지 않는다.
- 승인된 실제 대상에서 합성 저장/조회와 native refresh round-trip을 실행한다. HTTP fixture·메모리 모형·SQL 단위 검사를 운영 인증 성공으로 보고하지 않는다.
- refresh/저장 사이 중단·반영 전후 ACK 유실·강제 종료·동시 소비·철회·quota에서 다음 실제 호출이 차단되는지 확인한다.
- 도구/개인자료 전송·파일 업로드·예약·실제 제출은 별도 관문을 유지한다. 기존 Supabase 업무 DB 승인은 이 인증 보관 권한을 소급 승인하지 않는다.

## 공식 근거

선택 이유와 공식 Vault/API key/functions/pgsodium/PostgreSQL/GitHub 근거는 [ADR-0008](adr/0008-supabase-auth-reuse.md#확인한-사실과-미확인)이 소유한다. 기존 [업무 상태 저장소](SUPABASE_STATE.md)와 credential 저장을 혼동하지 않는다. Vault 자체와 pgsodium 신규 암호화 도입을 같은 것으로 취급하지 않는다.
