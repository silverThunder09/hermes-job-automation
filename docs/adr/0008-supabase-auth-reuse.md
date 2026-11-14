# ADR-0008: 기존 Supabase의 GPT 인증 저장 재사용 우선 검토

- 기록일: 2026-11-09
- 결정 상태: **Proposed — 설계 검토 후보, 기술 채택 전**
- 구현/배포/가동 상태: **운영 미구현·미배포·미가동**. 이번 변경은 문서·문서 계약 테스트뿐이다.
- 연결 이슈: [#15](https://github.com/silverThunder09/hermes-job-automation/issues/15)
- 선행 관계: [ADR-0007](0007-remote-model-auth.md)의 GitHub 보관 제안을 재비교한다. 기존 제안을 삭제하거나 채택된 결정처럼 취급하지 않는다. [ADR-0005](0005-supabase-postgres-only.md)의 업무 DB와 [ADR-0006](0006-actions-batch-boundary.md)의 실행·격리 결정은 유지한다.

## 배경과 요구사항

사용자는 업무 DB가 이미 Supabase에 있는데 인증 저장에도 별도 GitHub 구성이 필요한지 질문했고, 안전한 재사용 비교 후 설계 문서 수정·리뷰를 요청했다. **로그인 정보의 영속화 필요성이 별도 제품·App 필요성을 뜻하지 않는다.** 현재 Supabase 업무 레코드 저장은 GPT 로그인의 자동 저장이 아니다.

이번 요청은 개발 문서 전달 승인이다. Vault 활성화, DB/권한/인증 경로 구현, 실제 로그인·저장·모델 호출과 원격 예약을 승인하지 않는다. 두 보관 후보는 계속 Proposed이며 이전 ADR을 임의로 Accepted/Superseded로 확정하지 않는다.

## 확인한 사실과 미확인

공식 문서 및 현재 마이그레이션을 읽어 비교했다. 운영 DB·Vault·자격증명에는 접속하지 않았다.

| 근거 | 확인 사실 / 적용 한계 |
|---|---|
| [Supabase Vault](https://supabase.com/docs/guides/database/vault) | secret을 authenticated encryption으로 저장하고, 권한 있는 SQL 사용자는 `vault.decrypted_secrets`로 복호화된 값을 읽을 수 있다. `vault.update_secret()`이 있다. 프로젝트의 실제 설치·권한·원격 접근 가능 여부는 미확인이다. |
| [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys) | 현대 `sb_secret_...`도 `service_role`로 동작하며 RLS를 우회한다. 새 이름의 secret key만으로 최소권한 role이 생기지 않는다. table/function grant도 별도로 적용된다. |
| [Database Functions](https://supabase.com/docs/guides/database/functions) | INVOKER가 기본/권장이다. DEFINER는 owner·search_path·함수/반환 범위·EXECUTE 권한 통제가 필요하다. 현재 앱의 INVOKER 정책을 바꾼 것이 아니다. |
| [pgsodium 안내](https://supabase.com/docs/guides/database/extensions/pgsodium) | pgsodium 사용 대신 Vault를 권한다. Vault는 별도 extension이며 pgsodium에 의존하지 않고 해당 폐기 예정의 영향을 받지 않는다. |
| [PostgreSQL transaction](https://www.postgresql.org/docs/current/tutorial-transactions.html) / [locking](https://www.postgresql.org/docs/current/explicit-locking.html) | DB 안의 변경을 원자적으로 묶고 경쟁을 제어할 근거다. Vault 자체에 CAS/lease가 있다는 뜻이나 외부 OAuth refresh까지 rollback할 수 있다는 뜻은 아니다. |
| [GitHub Secret 주입 시점](https://docs.github.com/en/actions/reference/security/secrets) | repository Secret은 workflow queued 시점, environment Secret은 job 시작 시점에 주입된다. 초기 접속 자격 전달과 매번 회전하는 OAuth bundle 저장을 구분해야 한다. |

현재 `supabase/migrations/202611070001_job_assist_state.sql`은 업무 테이블·고정 INVOKER RPC만 다룬다. Vault/인증 전용 역할·함수·버전/잠금은 구성하지 않는다. Vault root key 운영/복구·현재 요금제/한도·Hermes 전용 로그인 이식성·실제 round-trip은 미확인이다.

## 비교와 조건부 제안

| 후보 | 이점 | 추가 책임·판단 |
|---|---|---|
| **기존 Supabase + Vault** | 기존 서비스 재사용, 저장 값 재조회, DB 안의 version/state와 함께 갱신하는 구조 가능 | 인증 전용 접근 경로·권한·transaction·복구를 개발해야 함. **우선 검토 후보**이지 즉시 사용 가능한 구현은 아님 |
| GitHub environment Secret + App writer | 기존 ADR-0007에 비교된 job-start 주입/후속 job 검증 구조 | App key·넓은 Environments 권한·계정 지원 확인·별도 marker/readback 구성 필요. 비교 이력으로 보존하고 자동 채택하지 않음 |
| 일반 공고 테이블에 평문 token 저장 | 기존 업무 CRUD를 그대로 쓰기 쉬움 | 업무/인증 권한 혼합·노출 위험. **권고하지 않음** |
| 직접 암호화 구현/새 외부 secret manager | 별도 키 보유/버전 관리 선택 가능 | 암호화·키 보관/복구·서비스/비용 비교가 더 필요. 이번 범위에서 미선정 |

**현재 권고는 기존 Supabase Vault 재사용을 먼저 설계·검증하는 것**이다. OAuth 갱신을 위해 GitHub에 쓰는 App/PAT와 그 App key를 생략할 수 있다. 그러나 원격 실행기가 Supabase에 처음 접근하는 **bootstrap 자격**은 DB 외부의 승인된 비밀 전달 경로에 남는다. 기존 서버 키를 무조건 재사용하거나 모든 GitHub Secrets가 불필요하다고 표현하지 않는다.

같은 프로젝트를 쓰므로 관리자 접근·DB 장애의 영향도 업무와 인증에 공통이다. 별도 schema나 Vault 암호화가 프로젝트 관리자까지 물리적으로 격리하지 않는다. 외부 운영 구성은 줄어도 DB 내부 개발이 없어지는 것은 아니다. 재사용은 항상 무료라는 보장도 아니다.

## 설계 소유 문서와 구현 전 관문

보관 객체·접근 권한·갱신/실패 계약·검증 기준은 [Supabase 인증 상세 설계](../SUPABASE_AUTH_DESIGN.md#credential-lifecycle)가 소유한다. 최초 후보는 고정 비개인 요청의 수동 진단이며 실제 업무 agent 연결은 별도다.

접점·bootstrap의 후속 비교는 [ADR-0009](0009-scoped-auth-db-access.md)에 구체화했다. 전용 LOGIN role·shared session pooler·private repository Secret 조합은 **Proposed 권고**이며 이 문서와 함께 기술 채택·운영 구현은 계속 미승인이다. 추가 서비스나 기존 넓은 서버 키를 자동 선택하지 않는다.

1. 실제 프로젝트의 Vault 사용 가능 여부·root key/backup 복구·관리자와 비용/한도를 확인한다.
2. [최소권한 접근 경계](../SUPABASE_AUTH_DESIGN.md#access-boundary)에서 전용 DB role/제한된 서버 접점과 bootstrap 종류를 선택한다. **구체 인증 접점은 미선정**이다. 안전한 접근을 확보하지 못하면 운영하지 않는다.
3. 사용자 기술 선택 후에만 새 버전 SQL·adapter·권한 및 조건부 갱신/실제 읽기 검증을 구현한다. 현재 테이블·INVOKER 정책·기존 credential을 변경하지 않는다.
4. 승인된 대상에서 synthetic 복원→native request/refresh→저장→별도 실제 값 readback→다음 run을 실증한다. SQL 단위 성공을 OAuth 통합 성공으로 대체하지 않는다.
5. provider refresh 후 저장 실패·불확실한 응답·강제 종료·동시 실행·철회·quota의 안전 차단을 검증한다. 사용 전 durable marker와 단일 owner는 저장소 변경 후에도 유지한다.
6. 도구/개인자료·모델 전송·파일 보존·예약·실제 제출은 각각 추가 승인 관문으로 남긴다. [ADR-0007의 Hermes/Codex/API 구분](0007-remote-model-auth.md#공식-근거로-확인한-사실)과 한도 미확인도 유지한다.

## 완료·재검토·승인 이력

이번 완료 기준은 문서/라우팅 계약 RED→GREEN·전체 회귀·exact head/base 두 축 리뷰·CI·개발 PR 병합 재조회다. 인증 모형이나 운영 src/SQL/workflow/의존성은 바꾸지 않는다. 이 성공은 Vault 설치·최소권한·OAuth·원격 실행 안전성 증명이 아니다.

최소권한 접근/복구/비용 조건을 충족하지 못하면 도입을 보류한다. GitHub 후보·API·VPS로 자동 전환하지 않고 별도 사용자 결정을 받는다. 현재 DB·로그인·원본 자료는 보존한다.

사용자는 Supabase 재사용 비교에 이어 **문서 수정·리뷰 진행**을 요청했다. 기술 채택·운영 변경 승인 기록은 아직 없다. 후속 선택이 확인되기 전 Proposed를 유지한다.
