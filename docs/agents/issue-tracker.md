# GitHub 이슈 경로

대상: `silverThunder09/hermes-job-automation`. 이 저장소의 개발 이슈/spec와 PR 추적에만 적용합니다. 실제 채용 사이트 계정/지원 이슈와 혼동하지 않습니다.

## 읽기·중복 확인

기존 인증된 `gh`를 사용하며 자격 증명 값/파일을 추출하지 않습니다.

```text
gh issue view <번호> --repo silverThunder09/hermes-job-automation --comments
gh issue list --repo silverThunder09/hermes-job-automation --state all --search <문제>
gh pr list --repo silverThunder09/hermes-job-automation --state open --search <문제>
```

본문과 최신 댓글을 함께 읽고 문제·범위/제외·완료 기준·실제 승인 범위를 확인합니다. 연결 spec을 찾지 못했으면 추정하지 말고 질문합니다. 중복 이슈가 있으면 갱신하고 새로운 결함이면 원래 이슈/PR에 연결합니다.

## 쓰기·종료

게시/댓글/상태 변경은 사용자 승인 대상·범위 안에서만 합니다. 현재 공개범위는 `gh repo view silverThunder09/hermes-job-automation --json visibility,isPrivate`로 확인하며 비공개라고 가정하지 않습니다. 개인 서류·토큰·원시 API 응답을 올리지 않습니다.

이슈 양식은 [.github/ISSUE_TEMPLATE](../../.github/ISSUE_TEMPLATE/change_request.yml), PR 본문은 [PR 템플릿](../../.github/pull_request_template.md)을 사용합니다. 이슈 번호를 만들거나 예시 번호를 실제로 연결하지 않습니다. 쓰기 실패가 불명확하면 정확한 대상을 조회한 뒤 재시도합니다.

재이슈·횟수·중단·종료 기준은 [PR 반복 규칙](../PR_AUTOMATION.md#review-loop)만 따릅니다. 단순 리뷰 통과/이슈 생성은 해결이 아니며 정확한 병합·검증 결과를 이슈에 연결하고 재조회합니다.
