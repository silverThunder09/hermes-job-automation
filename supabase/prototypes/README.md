# 인증 제어 SQL — 격리 로컬 프로토타입

[ADR-0009](../../docs/adr/0009-scoped-auth-db-access.md)의 **비밀 없는 로컬 SQL·권한 검증** 단계다. 이 폴더는 자동 적용되는 `supabase/migrations/`가 아니며 실사용 Supabase에 적용할 배포 SQL을 제공하지 않는다.

## 구현한 범위

[auth_control.sql](auth_control.sql)은 `job_auth_test_<32자리 hex>`라는 테스트 DB, postgres 설치 세션, 서버 로컬 Unix socket 연결에서만 적용된다. TCP 연결은 loopback도 포함해 거부한다. 일반 DB·원격 TCP 연결에서는 객체 생성 전에 중단한다. 기존 업무 schema·grant·설정은 수정하지 않는다.

- 제한된 NOLOGIN 함수 owner와 별도 비관리 LOGIN caller를 사용한다. **비밀번호는 NULL인 테스트 계정**이며 socket trust 인증만 사용한다. 기존 lab role에 비밀번호가 있으면 NULL 여부만 확인해 중단하고 기존 값을 변경하지 않는다. 비밀번호 원문·verifier는 출력하지 않는다.
- caller는 facade schema USAGE와 고정 함수 네 개의 EXECUTE만 추가 부여받는다. private 제어 테이블과 합성 업무 sentinel의 직접 읽기/쓰기, owner/postgres로 SET ROLE, facade 객체 생성이 거부되는지 검사한다.
- 함수는 별도 owner의 SECURITY DEFINER, 빈 search_path, 완전 수식 테이블 이름으로 동작한다. PUBLIC EXECUTE와 향후 기본 EXECUTE도 facade 범위에서 회수한다.
- 고정 singleton의 상태·owner·version·epoch·**합성 정수 generation**만 저장한다. SQL 안에 비밀값·비밀번호·OAuth bundle·Vault 대체 테이블은 없다.
- `begin_turn`은 ready 행을 원자적으로 claim하고 `in_flight`를 남긴다. 여러 동시 요청에서 하나만 성공한다.
- `stage_generation`은 같은 owner/version/epoch일 때 합성 generation과 version을 한 transaction에서 갱신하며 `pending_validation`을 유지한다.
- `block_turn`은 같은 owner의 실행을 blocked로 바꾼다. 재적용은 in_flight·blocked를 초기화하지 않는다. 초기 행은 새 control 테이블을 만들 때만 넣으며, 기존 행 유실 또는 기존 lab namespace의 테이블 유실은 AUTH_STATE_MISSING으로 중단한다. 설치 재적용을 복구/reset 경로로 사용하지 않는다.
- **finalize/reset/TTL 승계 함수는 없다.** 실제 credential 값 재조회·검증이 없으므로 caller가 ready로 돌리는 성공 경로를 구현하지 않았다.

`begin_turn`의 실제 사용 전 barrier는 commit과 독립 readback까지 확인해야 한다. 함수가 transaction 내부에서 반환한 것만으로 외부 provider를 실행할 수 있다는 뜻은 아니다. 현재 테스트는 psql의 autocommit 성공 이후 다른 연결로 marker를 확인하며 실제 provider는 전혀 호출하지 않는다.

## 실행과 안전 경계

[tests/test_auth_sql_prototype.py](../../tests/test_auth_sql_prototype.py)는 기존 로컬 Docker endpoint와 이미 실행 중인 아래 조건의 컨테이너만 사용한다.

- `--network none`, host port 공개 없음, 사용자 bind mount 없음.
- 허용 mount는 `/var/lib/postgresql/data`의 Docker 관리 익명 local volume 하나뿐이다. 다른 경로·mount 유형·custom volume 옵션은 거부한다.
- 명시적인 `com.hermes.job.auth-lab=true` label.
- `JOB_ASSIST_TEST_AUTH_CONTAINER`로 지정하며 원격 Docker host/context는 거부한다.
- 컨테이너·이미지 다운로드를 테스트가 자동 수행하지 않는다. 필요한 이미지는 이미 설치된 PostgreSQL 16을 재사용한다.
- 고유 테스트 DB를 만들며 기존 DB나 테스트 결과를 삭제하지 않는다. 마지막 테스트는 **지정된 격리 lab만 재시작**해 commit된 marker의 유지도 확인한다. 해당 컨테이너에 다른 작업을 같이 넣지 않는다.

선택 실행:

```text
JOB_ASSIST_TEST_AUTH_CONTAINER=<조건을 충족하는 전용 lab 컨테이너> python -m pytest -o addopts='' -q tests/test_auth_sql_prototype.py
```

기존 업무 SQL 테스트의 `JOB_ASSIST_TEST_POSTGRES_CONTAINER`와 별도 opt-in이다. 둘 다 같은 새 격리 lab을 명시할 수 있다. 실제 운영 접속 URL·Supabase 키·로그인 파일은 입력하지 않는다. 일반 테스트에서는 파일 분리 검사를 제외한 실제 SQL 검사가 opt-in으로 건너뛰어진다.

## 로컬 Python controller 연결

[scripts/auth_control_lab.py](../../scripts/auth_control_lab.py)는 이미 준비된 격리 lab의 고정 SQL 함수만 호출한다. DB·컨테이너 생성/시작·SQL 설치·초기화는 하지 않고 운영 앱의 Settings나 `.env`·로그인 파일도 읽지 않는다. 새 PostgreSQL driver를 추가하지 않으며 Docker exec/psql의 직접 socket과 비관리 role을 사용한다.

controller는 ready snapshot → claim → 별도 연결의 정확한 owner/version/epoch/state/generation 확인 → 순수 정수 fixture → stage → 별도 metadata 재조회를 수행한다. 성공 결과도 `verified_local_metadata`/`pending_validation`이며 실제 인증 준비 완료나 ready 복구가 아니다. 불확실한 claim/stage 응답에는 재시도하지 않고, 작업 실패에만 block을 한 번 시도한다.

```text
python scripts/auth_control_lab.py --container <전용 lab 이름> --database <이미 설치된 job_auth_test_32hex DB>
```

입력은 위 두 개의 엄격한 lab 식별자뿐이다. 실행 중 로컬 Docker endpoint와 immutable container ID를 고정하고, 최소 inspect metadata·격리 조건을 확인한다. host/container의 외부 접속·서비스·비밀번호 환경 우회는 차단하며 출력·오류·시간 제한을 둔다. 실제 비밀을 입력하지 않는다.

Docker CLI를 종료해도 컨테이너 안의 쿼리는 남을 수 있으므로, 정제된 psql 환경에 고정 `PGOPTIONS=-c statement_timeout=4000 -c lock_timeout=2000`을 적용한다. 서버 쿼리 4초·잠금 대기 2초는 바깥 Docker CLI 제한 15초보다 짧다. 실제 행 잠금과 장시간 쿼리 테스트에서 오류 반환 후 해당 lab DB의 비관리 client backend가 0개이고 상태가 ready 그대로임을 확인한다. 이 제한은 운영 Supabase 설정 변경이 아니다.

[controller 계약 테스트](../../tests/test_auth_control_lab.py)의 대역은 순서·오류·잘못된 metadata·환경/인자 제한을 검증한다. [실제 PostgreSQL 테스트](../../tests/test_auth_sql_prototype.py)의 controller 항목은 정상 순서, 작업 실패의 blocked 상태, 실제 commit 직후 client 예외를 주입한 claim/stage ACK 유실 대응, CLI 첫 실행과 두 번째 실행 차단을 별도 연결로 확인한다. client 예외 주입을 실제 네트워크 패킷 유실 검증으로 해석하지 않는다. 실제 컨테이너 inspect에서 Binds가 nil인 경우도 로컬 통합 실행으로 확인했다.

## 증명하지 않는 것

- Vault 설치/암호화/권한·원격 bundle 복원·native refresh·TLS 양쪽 구간·Supavisor 연결·비밀번호 인증·Secret 발급/회전/철회.
- 전체 실제 Supabase 프로젝트의 PUBLIC/default grant나 다른 SECURITY DEFINER 함수에 대한 안전성.
- 서로 적대적인 caller 실행의 격리. 같은 trusted LOGIN을 공유하는 client가 owner 값을 알면 해당 owner를 제시할 수 있다. owner/version은 정상 controller의 stale/동시성 충돌을 막는 조건이지 별도 caller 인증이나 비밀 capability가 아니다.
- pooler 뒤의 실제 caller 식별. `session_user` 검사는 직접 로컬 LOGIN에서만 검증했다.
- OAuth 값 저장 원자성·정확한 credential readback. 정수 generation 결과를 비밀 저장 성공으로 보고하지 않는다.
- 실제 가동·예약·지원 제출. SQL/테스트 성공은 운영 승인이나 인증 adapter 완성을 뜻하지 않는다.

실사용 접점을 구현하기 전에는 [인증 수명주기 계약](../../docs/SUPABASE_AUTH_DESIGN.md#credential-lifecycle)과 [ADR-0009 운영 관문](../../docs/adr/0009-scoped-auth-db-access.md#검증완료-기준)을 별도로 통과해야 한다.
