# ADR-0009: 원격 인증 전용 DB 접점과 bootstrap 구체안

- 기록일: 2026-11-11
- 결정 상태: **Proposed — 사용자 기술 선택 전**
- 구현/배포/검증 상태: 문서와 [격리 로컬 SQL 프로토타입](../../supabase/prototypes/README.md)을 검증한다. 프로토타입은 비밀 없는 제어 메타데이터·권한·동시성만 다룬다. 운영 SQL·adapter·실사용 DB 접속·Secret·로그인·모델 호출·예약은 **미구현·미배포·미실행**.
- 연결 이슈/PR: [Issue #24](https://github.com/silverThunder09/hermes-job-automation/issues/24), [Draft PR #25](https://github.com/silverThunder09/hermes-job-automation/pull/25).
- 2026-11-15 상태 확인: PR #25는 Open/Draft이며 미병합입니다. 공개 개발 기록으로 연결됐지만 운영 적용·배포를 뜻하지 않습니다.
- 선행 관계: [ADR-0008](0008-supabase-auth-reuse.md)의 우선 후보를 구체화한다. 0007·0008을 대체하거나 채택하지 않는다. [ADR-0006](0006-actions-batch-boundary.md)의 공개 개발/비공개 운영 분리는 유지한다.

## 배경과 요구사항

로컬 개발을 유지하면서 PC가 꺼진 동안 일회성 GitHub-hosted 배치를 실행하려는 목표다. 기존 Supabase 업무 상태 저장과 원격 GPT 로그인 저장은 별개다. 추가 상시 서버·GitHub OAuth writer 없이 기존 Supabase를 재사용하되, 기존 업무용 `SUPABASE_SECRET_KEY`나 `postgres` 비밀번호를 인증 controller에 재사용하지 않는 후보가 필요하다.

사용자는 선택안 구체화에 이어 **실사용 DB에 접속하지 않는 SQL 초안·로컬 권한 검증**을 승인했다. 새 운영 DB를 만드는 작업이 아니다. 격리 테스트용 PostgreSQL의 합성 role·함수·제어 메타데이터만 사용한다. 실제 Supabase 자원·role·함수·Vault·키·계정·영구 환경변수·workflow 변경과 자격증명 조회/등록을 승인한 것은 아니다.

## 사실·가정·미확인

2026-11-11 공식 공개 문서를 GET으로 읽고 현재 코드·마이그레이션과 비교했다. 운영 DB와 개인 계정 요금제·Secret 값은 조회하지 않았다.

| 공식 근거 | 확인한 사실 / 적용 한계 |
|---|---|
| [Supabase 역할](https://supabase.com/docs/guides/database/postgres/roles) | 사용자 정의 LOGIN role과 GRANT/REVOKE가 가능하다. role 생성만으로 최소권한이 완성되지 않는다. |
| [Postgres 연결](https://supabase.com/docs/guides/database/connecting-to-postgres) | shared pooler는 IPv4에서 접근 가능하며 custom role username 형식은 `[ROLE].[PROJECT-REF]`다. session mode는 5432, transaction mode는 6543이며 후자는 prepared statement 등 세션 상태 제약이 있다. 실제 프로젝트 호스트·접속 가능 여부는 미확인이다. |
| [TLS 검증](https://supabase.com/docs/guides/platform/ssl-enforcement) | `require`는 암호화만 요구하고, `verify-full`은 CA와 호스트 이름도 확인한다. shared pooler의 SSL enforcement는 client→pooler와 pooler→DB 양쪽 구간에 영향을 주며 변경은 DB 재시작을 수반한다. 실제 설정·두 구간의 보호·pooler에 맞는 CA/호스트 검증은 미확인이고 설정 변경은 수행하지 않았다. |
| [Vault](https://supabase.com/docs/guides/database/vault) | 허용된 사용자는 `vault.decrypted_secrets`에서 평문을 읽고 `vault.update_secret()`으로 갱신할 수 있다. 제한 함수 owner로 필요한 권한을 구성할 수 있는지와 실제 Vault 설치/복구는 미검증이다. |
| [Database Functions](https://supabase.com/docs/guides/database/functions) | INVOKER가 권장 기본값이다. DEFINER는 실행 owner 권한을 사용하고 기본 EXECUTE·직접 grant를 제한해야 한다. Dashboard의 postgres owner를 안전한 제한 owner로 가정하지 않는다. |
| [PostgreSQL role membership](https://www.postgresql.org/docs/current/role-membership.html) | INHERIT와 SET ROLE 경로는 별개다. `NOINHERIT`만으로 권한 상승을 차단했다고 할 수 없다. 실제 서버 버전·membership 체인은 따로 검사한다. |
| [PostgreSQL privileges](https://www.postgresql.org/docs/current/ddl-priv.html) | `PUBLIC` 권한은 모든 role에 적용되며 DB CONNECT/TEMPORARY·함수 EXECUTE 등의 기본 권한이 있다. 전용 role에서 REVOKE하는 것만으로 PUBLIC 권한을 제거하지 못한다. |
| [Actions Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) / [주입 시점](https://docs.github.com/en/actions/reference/security/secrets) | repository Secret은 workflow queued 시점에 읽힌다. Secret은 명시적으로 필요한 프로세스에만 전달하고 argv 노출을 피해야 한다. Secret 등록 ACK·이름 조회는 실제 접속 성공 증거가 아니다. |
| [GitHub environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) | private/internal 환경의 environment Secret은 Pro/Team/Enterprise 조건이 있다. required reviewers 같은 보호 규칙은 별도 가용 조건이다. environment Secret을 쓰면 비공개 승인 관문까지 자동 제공된다고 가정하지 않는다. |
| [Hermes providers](https://hermes-agent.nousresearch.com/docs/integrations/providers) | Hermes 자체 `openai-codex` OAuth·내장 refresh 경로가 있다. 원격 로그인 이식성·독립 token 가족·실제 구독 한도는 이 조회로 검증되지 않았다. |

현재 `SupabaseStateStore`는 HTTP/PostgREST 업무 adapter이며 `supabase/migrations/202611070001_job_assist_state.sql`은 업무 INVOKER RPC만 정의한다. 인증 전용 DB adapter나 제한 LOGIN role은 없다. 현재 의존성에 PostgreSQL driver를 추가하거나 기존 adapter를 변경하지 않았다.

## 검토한 대안

| 후보 | 장점 | 추가 책임 / 이번 권고 |
|---|---|---|
| **전용 LOGIN role + shared session pooler + 고정 DB 함수** | 같은 Supabase 재사용, 새 상시 서버·HTTP gateway·JWT 발급기 없음. 단일 저빈도 controller에 단순한 연결 모델 | driver·전용 role/owner/ACL·TLS·안전한 비밀 발급/교체 검증 필요. **우선 구체안** |
| 같은 LOGIN role + transaction pooler | 짧은 연결 다중화에 적합 | prepared statement 비활성화 등 드라이버 제약. 최초 단일 배치에서는 필수 아님. 나중에 변경해도 durable marker 계약은 동일 |
| 제한된 Edge Function/서버 접점 + DB 함수 | 원격 client의 SQL 직접 접근을 줄이는 별도 HTTPS 경계 가능 | 새 배포·caller 인증·서버 보유 권한·호출/로그/비용 책임이 늘어남. 현재 대안이며 생성하지 않음 |
| 기존 Data API와 넓은 서버 키 재사용 | 기존 HTTP 코드를 일부 재사용하기 쉬움 | 업무 권한과 인증 권한이 섞임. 좁은 facade URL만 부르는 것으로 키 자체 권한이 축소되지 않아 권고하지 않음 |
| custom JWT/Data API role 또는 OIDC broker | 승인된 교환기와 정책이 있다면 단기 자격 후보 | 기존 프로젝트에 자동 연결되는 교환기가 확인되지 않음. JWT signing 권한·새 broker를 조용히 도입하지 않음 |

## 결정 제안과 이유

**기존 Supabase의 전용 LOGIN role → IPv4 shared session pooler → 인증 전용 고정 함수**, 최초 접속 비밀은 **승인될 비공개 운영 저장소의 repository Actions Secret**으로 전달하는 조합을 우선 제안한다. 아직 선택된 운영 경로가 아니다.

일회성 단일 controller는 한 번에 연결 하나를 쓰고, 짧은 DB 작업이 끝나면 연결을 닫는다. provider 실행·refresh를 기다리는 동안 DB transaction·row lock·pooler 세션을 붙들지 않는다. DB에 commit한 durable `in_flight`와 owner/version이 소유권 근거이며 연결 생존·session advisory lock·GitHub concurrency를 근거로 대체하지 않는다. 상태/저장/실제 값 재조회는 [기존 수명주기 계약](../SUPABASE_AUTH_DESIGN.md#credential-lifecycle)이 소유한다.

repository Secret 후보는 pooler의 **전용 LOGIN 비밀번호 하나**다. 호스트·DB명·role·TLS 설정은 비밀과 분리한 검토 대상 설정으로 둔다. OAuth bundle은 GitHub의 오래된 초기 Secret을 매번 복원하지 않고 Vault의 승인된 최신본에서 읽는다. private repository Secret 사용은 repository 생성·접근자·신뢰 코드 정책·계정 기능 확인 후에만 가능하며 무료 가동을 보장하지 않는다.

## 권한·호출·실행 경계

1. **LOGIN caller:** 관리자 속성·role 생성·DB 생성·복제·BYPASSRLS·특권 role membership을 부여하지 않는다. 인증 facade schema의 USAGE와 필요한 고정 함수 EXECUTE만 추가 부여하는 안이다. 업무 테이블·제어 테이블·Vault view/함수의 직접 접근, 임의 credential 선택, object 생성/변경을 허용하지 않는지 실제 권한 검사로 증명해야 한다.
2. **effective privilege:** 직접 grant뿐 아니라 PUBLIC·기본 ACL·간접 membership·SET ROLE·소유권·schema CREATE·다른 DEFINER 함수를 검사한다. 일반 DB client는 권한 안에서 임의 SQL을 보낼 수 있으므로 "SQL 전송 자체가 불가능"하다고 주장하지 않는다. 광범위 PUBLIC REVOKE로 기존 업무 기능을 바꾸는 것도 이번 승인 범위가 아니다. 기존 권한과 공존하며 위험 경로를 차단할 수 없으면 후보 채택을 보류한다.
3. **고정 facade:** claim/restore/조건부 저장/실제 값 readback/상태 확정에 필요한 동작만 정의할 예정이다. 고정 credential의 한 행을 서버 쪽에서 결정하고, 임의 secret ID·SQL·schema·대상 URL을 입력으로 받지 않는다. 아직 실행 가능한 함수나 RPC 이름을 등록한 것은 아니다.
4. **별도 owner:** raw Vault 권한을 caller에게 주지 않으려면 제한된 NOLOGIN owner의 새 SECURITY DEFINER 함수가 필요할 수 있다. 이는 기존 업무 INVOKER 정책 변경과 별개인 미승인 보안 선택이다. owner를 postgres로 둔 채 안전하다고 하지 않는다. 빈 search_path·완전 수식 객체명·고정 대상·파라미터 바인딩·PUBLIC와 직접 EXECUTE grant 회수·미노출 schema를 검증한다. DEFINER 내부 current_user는 owner이므로 단순 비교를 caller 인증으로 쓰지 않는다. pooler 경유 실제 caller 식별 방식도 검사해야 한다.
5. **서버 기능 가용성:** 원하는 owner/권한으로 Vault 호출과 원자적 상태 갱신이 불가능하면 넓은 키·postgres로 우회하지 않는다. API/Edge 대안을 별도 검토한다. 같은 프로젝트의 관리자 접근과 장애는 여전히 공통 위험이다.
6. **controller/child:** DB bootstrap은 신뢰 controller만 소유하고 model child에 주지 않는다. 같은 UID의 환경변수 분리·별도 step·HERMES_HOME은 적대적 프로세스 격리 증거가 아니다. 첫 진단은 고정 비개인 입력·tool-disable 확인으로 제한하며, 실제 OS 경계와 자식 종료/출력 통제 전에는 임의 도구·사이트·첨부를 연결하지 않는다.
7. **비밀과 로그:** 비밀번호·OAuth bundle·fingerprint·접속 URL을 argv, Git, 업무 report, artifact/cache, SQL/HTTP/예외 로그에 남기지 않는다. 안전한 role 비밀 생성/등록·회전 경로와 provider/DB/pooler의 로그·진단 보존을 먼저 검증한다. SQL parameter binding이나 Actions masking만으로 서버 로그 유출이 해결됐다고 가정하지 않는다. 실제 비밀은 채팅으로 받지 않는다.

## 접속 자격 회전과 철회

repository Secret은 queued 시점 값을 사용하므로 등록 후 시작하는 오래된 run이 있을 수 있다. bootstrap 비밀번호와 별도로 인증 제어의 활성 epoch·durable non-ready 상태를 두고, 이미 발급된 자격/연결의 정지까지 확인하는 설계가 필요하다. epoch는 오래된 자격 자체를 무효화하는 수단이 아니다.

회전·철회 시 새 사용을 먼저 차단하고, 기존 owner/실행·후손 프로세스와 DB/pooler 연결을 조정한 뒤 role 비밀·외부 Secret의 교체와 새 연결 검증을 수행하는 안이다. **비밀번호 변경 또는 NOLOGIN만으로 기존 인증된 연결까지 끊겼다고 가정하지 않는다.** pooled server/client 세션의 기존 연결·인증 캐시·대기 run을 통제하고, 옛 자격의 새 접속과 기존 연결의 credential 사용이 모두 거부되는지 확인해야 한다. 실제 종료·철회·삭제는 별도 사용자 승인 대상이다.

GitHub Secret은 값을 다시 읽어 동일성을 확인하는 저장 API가 아니다. 등록 후 승인된 새 run이 제한 role로 연결되고 예상 identity/권한/epoch만 확인하는 증거를 요구한다. 대상·권한・비밀 전달을 포함한 최초 원격 수동 시험의 범위가 승인되기 전에는 Secret을 등록하지 않는다. 승인된 등록 뒤 비개인 진단을 수행하며, 등록 성공을 접속 검증 성공으로 대체하지 않는다. GitHub 환경 승인 기능을 확인하지 않은 상태에서 required reviewer를 운영 보안 경계로 삼지 않는다.

## 검증·완료 기준

문서 완료는 링크/앵커·Proposed 유지·기존 우선안/이력 발견·회귀·검토다. 후속 [로컬 SQL 프로토타입](../../supabase/prototypes/README.md)은 자동 migration 경로 밖에서 비관리 LOGIN·고정 함수 ACL·원자적 claim·정수 generation·rollback·재시작 후 marker를 검사한다. Vault나 OAuth를 대체하는 모형을 운영 adapter로 제시하지 않는다. 아래 운영 합격 기준은 **앞으로 실행할 검사**이며 문서·메모리 모형·일반 PostgreSQL 프로토타입의 통과가 대신하지 않는다.

| 관문 | 필요한 실제 증거 / 실패 시 동작 |
|---|---|
| 대상·비용·복구 | 승인된 private 운영 대상, 계정 포함량/초과 차단, 실제 Vault/복구·접속 호스트·CA 확인. 불명확하면 실행 보류 |
| 격리 PostgreSQL | 새 버전 SQL·별도 테스트 계정으로 ACL·소유권·PUBLIC·SET ROLE·함수 owner·동시성·rollback·restart marker 검사. 일반 PostgreSQL 통과는 Vault 검증이 아님 |
| 실제 권한 | 좁은 LOGIN의 필요한 facade 호출은 허용하고 업무 데이터·Vault raw view·다른 credential·특권 role·임의 쓰기는 거부. 기존 업무 경로가 유지되는지도 확인 |
| TLS·접속 | runner→pooler의 verify-full 정상 연결·잘못된 CA/호스트 거부와 pooler→DB 구간 보호, 실제 SSL enforcement 상태를 각각 확인. 두 구간 중 입증 불가가 있으면 실행 보류. 예상 caller identity·pooler mode·연결 종료도 확인. enforcement 변경에 따른 DB 재시작은 별도 승인 대상이며 이번에는 수행하지 않음 |
| 갱신 원자성 | owner/version 경쟁, DB commit/readback, refresh 후 저장 실패/ACK 유실/강제 종료에서 다음 실제 호출 차단. TTL만으로 ready 복원 금지 |
| bootstrap 철회 | 오래된 queued run·활성 controller·기존 DB/pooler 연결을 포함한 옛 자격 사용 차단. 신규 비밀 등록만으로 통과 처리하지 않음 |
| 실제 Hermes | 승인된 고정 비개인 요청에서 native 복원→refresh→저장→값 재조회→다음 run. 외부 로그인 자동 채택·유료 fallback·임의 tool 비활성 검증. 현재 로컬 로그인 복사나 구독량 공유를 전제하지 않음 |
| 정보 흐름 | controller만 DB 접속 자격 보유, child·로그·오류·artifact/cache에서 비밀 노출 없음. 실증 전 실제 자료/사이트/예약은 연결하지 않음 |

## 되돌리기·재검토 조건

최소권한의 effective grant, 안전한 비밀 발급/철회, Vault 제한 owner, TLS, 원자적 갱신·불확실한 refresh 차단 중 하나라도 입증하지 못하면 운영 도입을 보류한다. 추가 서비스·넓은 키·유료 API로 자동 전환하지 않는다. 기존 업무 DB·로그인·stash·로컬 설정을 보존하며 원본 삭제/role 제거/예약 해제도 별도 승인 범위에서만 한다.

## 승인·변경 이력

사용자는 2026-11-11 **운영 변경 없이 선택안을 구체화**하는 후속 작업을 요청했다. 이 문서의 조합은 권고이며 기술 채택은 아직 미승인이다. 이후 로컬 SQL/controller 검증 작업은 Issue #24와 Draft PR #25에 연결된 공개 개발 기록으로 게시됐으며, 이 공개 기록은 기술 채택·운영 변경 승인을 뜻하지 않는다. 실제 DB 적용·Secret 등록·로그인·원격 수동 시험·예약 가동은 각각 허용 대상과 완료 증거를 명시해야 한다.

이후 사용자는 별도 운영 DB가 필요하지 않고 기존 Supabase의 실사용 영역을 뜻한다는 설명을 확인한 뒤 **로컬 SQL·권한 검증을 진행**하도록 요청했다. 해당 제한 범위의 개발 승인만 추가하며 실사용 권한·비밀 전달·운영 배포를 승인한 것으로 확장하지 않는다. 실사용 기술 채택 전인 Proposed 상태는 유지한다.
