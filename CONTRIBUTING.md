# 기여·작업 흐름

변경은 아래 절차에 따라 준비합니다. 공유할 변경은 [PR 절차](docs/PR_AUTOMATION.md)를 따릅니다. 로컬 초안과 외부 게시·실행 권한은 별개입니다. 에이전트는 [개발 진입점](docs/agents/development.md)에서 필요한 기능 문서만 선택합니다.

## 데이터베이스 역할

| 구분 | 사용 기술 | 의미 |
|---|---|---|
| 앱의 유일한 실사용 상태 저장소 | **Supabase PostgreSQL** | ADR-0005로 단일화 승인. 공고·평가·지원 상태·실행 기록의 공유 원본이며 로컬 개발도 같은 DB 사용. 단일화 구현/실제 설정 검증은 별도 완료 기준 |
| 이전 데이터 보관 파일 | 기존 SQLite 파일 | 삭제·자동 이관하지 않는 원본 보관물. ADR-0005에 따라 `feature/supabase-state-store`의 앱/테스트 backend와 기본값에서 제거 완료 |
| SQL 마이그레이션·동시성 통합 테스트 | **격리된 Docker PostgreSQL — 테스트 전용** | 테스트 데이터로 SQL/권한/동시성을 검사하는 선택적 환경. 실사용 DB나 개발자의 필수 로컬 DB 서버가 아님 |

개발을 로컬에서 한다는 것이 DB도 로컬 PostgreSQL을 사용한다는 뜻은 아닙니다. 위 표는 [ADR-0005](docs/adr/0005-supabase-postgres-only.md)의 승인된 구조이며 코드 수정·환경 전환·live 검증 완료는 따로 확인합니다. 테스트용 PostgreSQL 결과를 Supabase 운영 검증으로 대체하지 않습니다.

## 작업 시작

1. 기존 이슈·PR·작업 트리를 확인하고 중복 작업을 피합니다. 진행 중인 변경은 보존하며 다른 목적의 변경은 별도 브랜치/작업 트리로 분리합니다.
2. 기능·버그·문서·운영 변경의 추적은 [이슈 경로](docs/agents/issue-tracker.md#쓰기종료)를 따릅니다.
3. 작업 시작 전에 [ADR 작성 대상과 승인 절차](docs/adr/README.md#작성-대상과-시점)를 확인합니다.
4. 브랜치·코드·커밋 규칙은 [컨벤션](docs/CONVENTIONS.md)을 따릅니다.

## 구현과 검증

- 이슈의 완료 기준을 테스트할 공개 인터페이스를 정하고, 재현 실패 → 수정 → 재검증 순서로 작업합니다.
- 로컬 fixture, 테스트 전용 Docker PostgreSQL의 SQL 검증, 실제 Supabase 연동 검증을 각각 구분합니다. 로컬 PostgreSQL을 실사용 DB로 지정한 것이 아닙니다. 실행하지 않은 결과를 성공으로 기록하지 않습니다.
- 코드 기본값, 로컬 환경 설정, 원격 배포 상태를 구분합니다. 환경변수 추가만으로 배포/전환 완료라고 말하지 않습니다.
- 원본 DB와 개인 문서는 유지합니다. 스키마 변경은 버전 SQL과 재실행·롤백/전진 수정 방안을 준비합니다.
- [공통 승인 경계](AGENTS.md#always-on-boundaries)와 [외부 변경 검증·기록 규칙](docs/CONVENTIONS.md#데이터오류보안)을 적용합니다.

## PR과 리뷰

커밋·push·PR·병합 권한과 게시·검토 절차는 [에이전트 주도 PR 자동화](docs/PR_AUTOMATION.md), 차단 결함의 연결 이슈·수정·재리뷰는 [반복 한도](docs/PR_AUTOMATION.md#review-loop)를 따릅니다.

## 훅·이슈 대응·사람 승인 초안

커밋 훅, 심각도별 이슈 대응, 승인 매트릭스의 [현행 규칙과 Proposed 제안 구분](docs/WORKFLOW_POLICY.md#현행-규칙)을 확인합니다.

## 자동 검사와 원격 강제의 차이

`PR policy / metadata`는 제목·이슈 번호 형식·필수 본문·ADR 파일/불필요 사유를 검사합니다. 이슈 실재 여부, ADR의 타당성, 테스트 주장의 진실성은 리뷰에서 확인합니다. 형식 통과는 병합 승인이나 운영 정상의 증거가 아닙니다.

템플릿과 workflow는 저장소에 반영되어야 GitHub에서 동작합니다. main의 PR 필수화, 필수 상태 검사, force-push 제한 등은 GitHub ruleset/branch protection에서 별도로 설정·조회해야 합니다. 사용 플랜·권한에 따라 지원 여부를 확인하고, 이 문서만으로 강제된다고 보고하지 않습니다. 개인 저장소에 작성자 본인의 승인이 불가능한 승인 개수 규칙을 무작정 설정하지 않습니다.

로컬 형식 검사:

```text
python scripts/check_pr_policy.py --event <PR-event.json>
```

위 파일은 GitHub `pull_request` 이벤트의 title/body를 담은 JSON이며 인증정보가 필요 없습니다. 실제 PR을 생성하거나 수정하지 않습니다.
