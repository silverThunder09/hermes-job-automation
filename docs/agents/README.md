# 기능별 문서 라우팅

이 파일은 필요할 때 여는 색인입니다. 작업에 맞는 **한 섹션·한 행부터** 읽고 그 행의 조건이 성립할 때만 다음 문서를 엽니다. 단일 공고 전체 작업은 [job-tailoring](../../skills/job-tailoring/SKILL.md), 일괄 작업은 [job-search](../../skills/job-search/SKILL.md)가 순서를 소유합니다. 문서 탐색만으로 도구 실행·계정 연결·외부 변경을 승인하지 않습니다.

## Research

| 작업 | 먼저 읽을 곳 | 필요한 경우에만 추가 |
|---|---|---|
| 공고 내용·접수 상태·URL 실패 복구 | [공고 분석](../../skills/job-tailoring/SKILL.md#posting-analysis) | 실제 사이트 접근 전 Access 섹션 |
| 회사 공식 홈페이지 분석만 | [회사 분석](../../skills/job-tailoring/SKILL.md#company-analysis) | 채용 플랫폼 페이지를 경유하면 [Access](#access)를 먼저 확인. 회사 정보와 지원자 경험을 구분. 이력서 수정까지 요청한 경우에만 Documents 섹션 |

## Documents

| 작업 | 먼저 읽을 곳 | 필요한 경우에만 추가 |
|---|---|---|
| 원본 근거 정리·이력서 편집 | [원본 보존·입력 확인](../../skills/job-tailoring/SKILL.md#input-safety) → [이력서 수정](../../skills/job-tailoring/SKILL.md#resume-edit) | [수정 후 검토·저장](../../skills/job-tailoring/SKILL.md#document-review) |
| 이미지 OCR·PDF 텍스트 추출 | [원본 보존](../../skills/job-tailoring/SKILL.md#input-safety) → [OCR 사실 검증](../../skills/job-tailoring/SKILL.md#ocr-evidence) → [로컬 OCR](../../skills/job-tailoring/SKILL.md#local-ocr) | 엔진 비교/변경 때만 [OCR 조사](../OCR_SKILL_RESEARCH.md). 원격 OS 지원은 Runtime 섹션 |
| DOCX/PDF 생성 코드 수정 | [개발 진입점](development.md) → `documents.py`, `tests/test_documents.py` | 설치 폰트/OS 문제일 때만 [클라우드 문서 출력 경계](../CLOUD_DEVELOPMENT.md#4-현재-기능의-클라우드-경계) |

## Access

| 작업 | 먼저 읽을 곳 | 필요한 경우에만 추가 |
|---|---|---|
| 수집기·플랫폼 이용 허용 범위 | [플랫폼 정책](../PLATFORM_ACCESS.md) | 사람인은 [개인/기업 약관·단계별 미확인 관문](../SARAMIN_ACCESS.md). 공개 안내 재조회와 반복 공고 수집은 별개 |
| 지원 승인·중복 방지·실제 제출 | [운영 문서의 제출 승인](../OPERATIONS.md#제출-승인) | 플랫폼 정책, 해당 계정·공고별 승인, `application.py`와 `state.py`의 실제 구현 대조. helper 존재는 실사이트 제출 통합 증거가 아님 |

## Storage

| 작업 | 먼저 읽을 곳 | 필요한 경우에만 추가 |
|---|---|---|
| Supabase 설정·상태 조회/쓰기·SQL | [상태 저장소](../SUPABASE_STATE.md) | 구조 변경은 [ADR-0005](../adr/0005-supabase-postgres-only.md). 실제 DB 쓰기는 해당 대상 승인 후 |
| Google Sheets/Drive 연결 | [Google 설정](../GOOGLE_WORKSPACE_SETUP.md) | [운영 실행 단계](../OPERATIONS.md#실행-단계)의 `--execute` 외부 쓰기 경계 |
| Telegram·실행 결과·로그 | [운영 가이드](../OPERATIONS.md) | 장애 기록이 필요할 때만 [실패 템플릿](../templates/run-failure.md) |

## Runtime

| 작업 | 먼저 읽을 곳 | 필요한 경우에만 추가 |
|---|---|---|
| 인증 없는 Chromium 진단·CI 실패 | [runtime-check 계약](../../README.md#오프라인-브라우저-실행-진단) | `runtime_check.py`, `tests/test_runtime_check.py`, `.github/workflows/ci.yml`. 운영 설정/모델 인증 문서 로드 불필요 |
| 설치·Codespaces·OS/폰트 경계 | [개발/클라우드 실행 경계](../CLOUD_DEVELOPMENT.md) | 패키지/테스트 명령은 [개발 진입점](development.md). 개발환경은 운영 배포가 아님 |
| GPT 모델·구독·인증 연결 조사 | [기존 공식 조사](../HERMES_OFFICIAL_RESEARCH.md) | 역사적 조사이므로 [최신 Hermes 공식 문서](https://hermes-agent.nousresearch.com/docs/integrations/providers)와 실제 호출 코드를 대조. Hermes 모델 경로·Python API·향후 원격 인증을 분리 |
| PC-off 예약·인증 보존·임시파일 정리 | [미확정 예약/보존 ADR-0003](../adr/0003-scheduled-collection-and-retention.md) | [운영 예시](../OPERATIONS.md#예약과-재부팅), [클라우드 예시](../CLOUD_DEVELOPMENT.md#3-pc가-꺼져도-매일-실행)는 대안 설명이지 배포/가동 증거가 아님. 예약 배치 우선 요구를 유지하고 새 인프라·인증·삭제는 결정/승인 후 |

## Product

| 작업 | 먼저 읽을 곳 | 필요한 경우에만 추가 |
|---|---|---|
| 제품 목표·MVP 범위·구현 여부 | [제품 범위](../PRODUCT_SCOPE.md) | [README](../../README.md)의 해당 기능 설명과 실제 코드/검증 증거 |
| 새 기술·의존성·권한·보존 선택 | [ADR 작성 규칙과 상태 색인](../adr/README.md) | 해당 ADR만 읽고 Proposed/Accepted/Historical 구분 |
| 훅·세부 품질/승인 정책 | [정책 문서](../WORKFLOW_POLICY.md) | [ADR-0004](../adr/0004-quality-gates-and-approvals.md)는 훅 등 미결정 제안. 승인된 PR 반복 규칙은 [PR 절차](../PR_AUTOMATION.md#review-loop)가 단일 원본 |

## 읽기 완료 기준

현재 작업의 입력·출력·실제 변경·승인 경계와 검증 접점을 설명할 수 있으면 탐색을 멈춥니다. 관련 파일이 없거나 문서와 코드가 다르면 필요한 경로만 검색하고 차이를 기록합니다. 모든 문서/ADR·조사 보고서·과거 대화를 먼저 읽는 방식으로 돌아가지 않습니다. 기능을 추가/이동하면 해당 행과 라우팅 계약 테스트를 함께 갱신합니다.
