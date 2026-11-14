# Architecture Decision Records

기술 선택은 **결정 이유와 대안·비용·위험을 먼저 기록하고 승인 후 구현**합니다. ADR은 기술 목록이나 구현 완료 보고서가 아닙니다.

## 작성 대상과 시점

새 DB/프레임워크/모델 제공자/외부 서비스/실행 인프라/주요 의존성, 개인정보·권한·보존 정책 또는 쉽게 되돌리기 어려운 변경은 코딩 전에 ADR 초안을 작성합니다. 작은 오탈자나 기존 선택 안의 국소 수정은 PR의 `ADR` 항목에 불필요 이유를 적습니다. 표준 라이브러리 함수마다 ADR을 만들지는 않습니다.

1. 기존 ADR과 이슈를 확인하고 다음 번호 `NNNN-kebab-case.md`를 사용합니다. 번호를 재사용하거나 기존 결정을 덮어쓰지 않습니다.
2. [템플릿](template.md)에 요구사항·제약·대안·선택 이유·비용/보안·검증 기준·되돌리는 조건을 씁니다. 사실/추정/미확인을 구분합니다.
3. `Proposed`로 리뷰를 받고 사용자의 결정 확인 뒤 `Accepted`로 바꿉니다. 문서 작성자/AI가 임의로 합의를 만들어내지 않습니다.
4. 구현/배포/검증 상태는 결정 상태와 별도 필드로 관리합니다. Accepted라도 미구현일 수 있습니다.
5. 변경 시 새 ADR에서 이전 번호를 supersede하고 이전 문서에는 상태/후속 링크만 남깁니다. 과거 판단 이유는 보존합니다.

상태: Proposed / Accepted / Rejected / Superseded / Historical. Historical은 **사전 결정 기록이 없던 기존 구현의 사후 기록**이며 당시 대안 비교나 사용자 승인을 소급해 주장하지 않습니다.

## 기록

| ADR | 결정 상태 | 의미 |
|---|---|---|
| [0001](0001-local-sqlite-baseline.md) | Historical | 초기 SQLite 사용 사실과 로컬 실행에서의 장단점 |
| [0002](0002-shared-supabase-state.md) | Superseded | Supabase 도입/SQLite 공존의 이력. 공존 정책은 0005가 대체 |
| [0003](0003-scheduled-collection-and-retention.md) | Proposed | 보존·삭제·운영 세부 미결정. 실행 호스트/시각 경계는 0006 후속 결정 |
| [0004](0004-quality-gates-and-approvals.md) | Proposed | Git 훅·이슈 대응·승인 경계: 구현/활성화 전 결정 필요 |
| [0005](0005-supabase-postgres-only.md) | Accepted | Supabase PostgreSQL 단일 저장소로 통일, 앱/테스트의 SQLite 제거 |
| [0006](0006-actions-batch-boundary.md) | Accepted — 실행·격리 경계만 | 04시 Asia/Seoul GitHub 배치, 공개 개발/비공개 운영 분리. 인증 세부·자원 생성·가동은 별도 |
| [0007](0007-remote-model-auth.md) | Proposed — 비교 이력 | GitHub environment Secret/App writer 후보의 이유·제약 보존. 현재 추가 비교·우선 후보는 0008, 기술 선택은 미승인 |
| [0008](0008-supabase-auth-reuse.md) | Proposed | 기존 Supabase Vault 재사용 우선 검토. bootstrap·최소권한 접점·원격 갱신은 미선정/미구현·미승인 |
| [0009](0009-scoped-auth-db-access.md) | Proposed | 0008의 접점·bootstrap 구체안: 전용 LOGIN role·shared session pooler·private repository Secret 조합 권고. 기술 채택·운영 변경 미승인 |

초기 Python/Hermes/문서 출력/OCR 선택도 사전 ADR은 없었습니다. 기존 기술이 이미 최적이라고 간주하지 않으며, 해당 선택을 바꾸거나 중요 의존성을 추가할 때 대안 비교와 승인 절차를 적용합니다. 실제 의존성 목록은 `pyproject.toml`, 실행 여부는 코드·검증 기록을 확인합니다.
