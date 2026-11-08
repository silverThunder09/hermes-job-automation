# 개발 작업 진입점

코드·문서·테스트·CI 변경 전에 이 진입점을 읽습니다. 제품 실행만 하는 작업은 해당 기능 경로만 사용합니다.

## 필요한 규칙 선택

1. [CONTRIBUTING](../../CONTRIBUTING.md)의 작업 시작·구현과 검증, [컨벤션](../CONVENTIONS.md)을 읽고 변경 범위·테스트 접점을 정합니다. 다른 기능 문서를 전부 읽지 않습니다.
2. 이슈 생성/추적 또는 PR 리뷰의 spec 확인에는 [GitHub 이슈 경로](issue-tracker.md)를 사용합니다. 기존 dirty 변경은 보존하고 목적별 worktree를 사용합니다.
3. 기술/주요 의존성/인프라/보안·보존 선택이 바뀔 때만 [ADR 규칙](../adr/README.md)과 해당 기록을 읽고 사용자 결정 후 구현합니다. 문서 탐색/링크 수정 자체는 새 기술 선택이 아닙니다.
4. 커밋·push·PR·리뷰·병합 작업이면 [PR 절차](../PR_AUTOMATION.md), 결함 재추적 시 [반복 한도](../PR_AUTOMATION.md#review-loop)를 읽습니다. 승인된 동일 범위의 반복을 매 단계 다시 묻지 않습니다.
5. 실제 기능의 계약이 필요하면 [기능 색인](README.md)의 해당 행만 추가합니다. 변경 경로와 무관한 조사·운영 설정은 읽지 않습니다.

## 로컬 개발·검증

- Python 호환 범위/의존성은 `pyproject.toml`, CI 대상은 `.github/workflows/ci.yml`을 확인합니다. 현재 Python 3.9+ 호환, CI 3.11입니다.
- 설치가 필요한 깨끗한 환경에서만 `python -m pip install -e '.[dev]'`, `python -m playwright install --with-deps chromium`을 사용합니다. 이미 준비된 환경을 불필요하게 재설치하지 않습니다.
- 전체 회귀: `python -m pytest -o addopts='' -q`. 다른 checkout의 editable 설치를 사용할 수 있으므로 대상 worktree의 `src`를 `PYTHONPATH`로 지정합니다.
- 코드 구문: `python -m compileall -q src`. 변경/새 파일을 읽고 `git diff --check`와 명시적 staged 경로를 확인합니다.
- 문서/하네스 변경: `python -m pytest -o addopts='' -q tests/test_agent_routing.py`. 로컬 링크·앵커·문서 발견 가능성·기본 로드 크기·절차 계약을 검사합니다. 모델이 항상 라우팅을 따르거나 도구 권한을 강제한다는 검사는 아닙니다.
- Chromium 진단·SQL 테스트는 기능 색인의 해당 행으로 이동합니다. SQL opt-in은 격리 PostgreSQL 전용이며 실사용 Supabase 성공과 구분합니다.

완료 조건: 해당 이슈 기준의 수정 범위/전체 회귀, 두 축 리뷰와 head/base를 기록합니다. 원격 작업이 포함되면 정확한 대상 재조회까지 확인하고, pending·미실행·블로커는 성공과 구분합니다.
