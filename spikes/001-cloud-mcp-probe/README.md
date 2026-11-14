# GitHub-hosted Playwright MCP 단건 읽기 실험

## 질문
GitHub-hosted Ubuntu에서 실제 Playwright MCP와 Chromium을 시작해 고정된 공개 점핏 공고 한 건의 최소 정보를 읽을 수 있는가? 로컬 성공, 원격 브라우저 가동, 실제 사이트 읽기, 정기 수집 허용과 04시 예약 가동은 서로 다른 관문이다.

## 범위
Issue #26. 사용자 승인 범위는 별도 시험 브랜치 게시와 단발 클라우드 실행뿐이다. `probe.mjs`의 고정 공개 URL에 한 번 navigate한다. 로그인·추가 동의·CAPTCHA·차단에는 대응하거나 우회하지 않는다. 모델·운영 DB·개인 자료·브라우저 프로필·Secrets·프록시를 사용하지 않는다. MCP 프로세스에는 최소 환경만 전달한다. 외부 포트나 예약 trigger를 만들지 않는다.

## 실행
`npm ci --ignore-scripts --no-audit --no-fund` 후 `npm test`, `npm run tools`는 합성 검사/도구 발견이다. 실제 공개 페이지 탐색인 `npm run probe`는 GitHub-hosted runner에서만 허용한다. 브라우저는 설치된 `playwright` 패키지의 CLI로 설치한다. 잠금 파일의 MCP/SDK 버전을 사용한다. 루트 Python 앱 의존성이나 collector 설정을 변경하지 않는다.

결과는 workflow artifact의 `cloud-probe-result.json`에 최소 메타데이터만 기록한다. 전체 공고 본문·이력서·로그인 정보는 저장하지 않는다. 이 결과는 새로운 공고를 운영 DB에 넣거나 일일 수집을 활성화한 증거가 아니다.

## Verdict: PENDING
원격 실행 전이다. 실제 run 결과는 이슈에 기록하며 예상 출력을 성공 결과로 사용하지 않는다. 성공하더라도 단일 공개 페이지·한 시점·한 runner에서의 관측이며 다른 플랫폼, 로그인, 주기적 수집, 전체 검색 결과나 정확한 04시 시작을 보장하지 않는다.
