# ADR-0002: 클라우드·로컬 공유 상태를 Supabase PostgreSQL에 저장

- 기록일: 2026-11-07
- 결정 상태: Superseded — [ADR-0005](0005-supabase-postgres-only.md)가 SQLite 공존/기본값 유지 정책을 대체. Supabase 도입·검증 승인 이력은 아래에 보존
- 기록 성격: 도입·구현 후 작성한 사후 정리. Supabase 도입 승인과 달리 REST 접근의 대안 비교를 구현 전에 ADR로 검토·승인받았다는 증거는 없음. 향후 기술 변경부터 Proposed ADR을 먼저 작성
- 구현 상태: 별도 `feature/supabase-state-store` 작업의 adapter/버전 SQL. 이 규칙 브랜치에 구현 코드를 섞지 않음
- 배포/검증 상태: 사용자가 SQL 실행 후 실제 health·샘플 저장/재조회 검증 성공을 확인한 시점의 기록. 원격 미래 상태를 보증하지 않음
- 연결 이슈/PR: 기존 작업에는 아직 원격 추적 식별자 없음. 게시 승인 후 실제 식별자로 연결
- 관련: [ADR-0001](0001-local-sqlite-baseline.md), [ADR-0003](0003-scheduled-collection-and-retention.md)

## 요구사항과 대안

PC 전원과 무관한 실행기와 로컬에서 같은 공고·평가·지원 상태를 사용해야 합니다. 원본/지원 서류는 이 상태 DB 전환만으로 업로드하지 않습니다.

- 개인 PC SQLite: 로컬 실행은 단순하지만 PC가 꺼졌을 때 공유 원본으로 접근할 수 없습니다.
- Drive의 SQLite snapshot/결과 병합: 가능하지만 충돌·snapshot 일관성·병합 정책을 추가로 관리해야 합니다.
- 자체 PostgreSQL 서버: 제어권은 높지만 운영·패치·백업·접근 관리 책임이 커집니다.
- Supabase PostgreSQL: 관리형 공유 DB와 별도 private Storage를 사용할 수 있습니다. 무료 플랜은 무제한/무중단 보장이 아니며 현재 계정의 한도·휴면·과금을 따로 확인해야 합니다.

## 결정

공유 상태 backend로 Supabase PostgreSQL을 지원합니다. 공고·적격성·평가·지원 상태/메모·실행 기록은 DB에, 파일은 별도 비공개 Storage에 둡니다. 이번 DB 연동은 파일 업로드 기능을 켜지 않습니다.

접근은 기존 store 인터페이스 뒤의 **PostgREST adapter + 고정 목적 RPC**로 구현합니다. Python 표준 HTTP 라이브러리를 사용해 추가 SDK/DB 드라이버 없이 기존 서버 전용 Secret Key로 연결합니다. 중복 판정/지원 시도 claim은 unique 제약과 서버 원자적 연산이 맡습니다.

직접 PostgreSQL 드라이버는 복잡한 transaction/SQL 접근에 유리하지만 연결 문자열·관리자 자격 증명·드라이버/풀링을 추가 관리해야 합니다. 현재 필요한 제한된 저장 동작에서는 REST adapter를 선택하며, 임의 SQL 실행 RPC는 만들지 않습니다. 이 API 사용 결정은 **채용 사이트 수집을 브라우저로 한다는 방향과 별개**입니다.

## 보안·운영·단점

- Secret Key는 통제된 backend에만 보관하며 RLS를 우회할 수 있습니다. 테이블에는 RLS와 역할별 권한을 명시하고 일반 사용자/익명 접근 및 불필요한 삭제 권한을 제한합니다.
- Secret Key는 SQL DDL/Management API 권한이 아닙니다. 버전 SQL은 소유자가 SQL Editor에서 적용하고 앱은 schema를 임의 생성하지 않습니다.
- HTTPS origin 검증과 redirect 거부를 적용하고 인증정보/응답 원문을 로그에 출력하지 않습니다.
- 연결 장애 시 조용히 SQLite로 전환하지 않습니다. 불확실한 쓰기는 정확한 키로 재조회하고 조정합니다.
- 중복 수집은 기존 공고/평가/지원 상태를 보존합니다. 공고 내용의 변경 이력·갱신 정책과 수동 상태 편집 기능은 별도 설계 대상입니다.
- 코드 기본값(SQLite), 로컬 `.env` 선택, 운영 배포 상태는 서로 다릅니다. 기존 SQLite 자동 이관/삭제와 기본값 전환은 이 결정으로 실행되지 않습니다.

## 검증과 재검토

로컬 fixture와 SQL 통합 테스트 전용 Docker PostgreSQL은 실사용 DB가 아닙니다. 이 테스트 결과와 live Supabase 결과를 구분합니다. 실제 schema/RLS/private bucket → 공개 샘플 save/get → 평가 → 중복 → 상태 보존 → run report 재조회가 모두 성공해야 원격 저장을 검증했다고 말합니다. 개인정보를 테스트 데이터로 쓰지 않습니다.

권한·비용·가용성 한도, RPC 복잡도 또는 다중 작업 트랜잭션 요구가 커지면 직접 DB 연결/다른 호스팅을 새 ADR로 재검토합니다. 이전 DB와 원본은 보존하며 backend 선택 변경과 데이터 이관을 분리합니다.
