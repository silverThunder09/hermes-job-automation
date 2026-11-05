# 채용 플랫폼 접근 정책

확인일: 2026-11-03

이 프로젝트는 채용 사이트 이용약관과 승인된 API 범위 안에서만 자동 수집합니다. 플랫폼별 공식 허가가 없으면 브라우저 검색 화면을 반복 호출하거나, 내부 엔드포인트를 찾아내거나, CAPTCHA·로그인을 우회하지 않습니다.

| 플랫폼 | 자동 접근 상태 | 근거와 다음 단계 |
| --- | --- | --- |
| 사람인 | 승인된 공식 API만 | API 신청·승인 후 access-key 발급이 필요합니다. 현재 개인 회원 약관은 사전 동의 없는 자동화/API 접근 및 DB 정보 수집을 제한합니다. |
| 잡코리아 | 자동 수집 중지 | API 이용약관은 개인 사용·프로젝트·DB 수집 목적의 신청을 승낙하지 않는다고 명시합니다. 구직용 브라우저 확인과 개인 지원 기록은 가능하지만 API 자동 수집은 연결하지 않습니다. |
| 원티드 | 자동 수집 중지 | 개인용 채용 API 또는 자동 접근 허용에 대한 공식 근거가 확인되지 않았습니다. |
| 점핏 | 자동 수집 중지 | 공식 API 및 자동 접근 권한이 확인되지 않았습니다. 공고 상세 페이지에서 접수 상태를 직접 검증해야 합니다. |
| 직행 | 자동 수집 중지 | 공식 API 및 자동 접근 허용에 대한 근거가 확인되지 않았습니다. |
| 로켓펀치 | 자동 수집 중지 | 공식 API 및 자동 접근 허용에 대한 근거가 확인되지 않았습니다. |
| 그룹바이 | 자동 수집 중지 | 공식 API 및 자동 접근 허용에 대한 근거가 확인되지 않았습니다. |

사람인 API는 공식 안내에 따라 사전 이용 신청 승인과 access-key가 필요하고, 일 최대 500회 호출 한도가 있습니다. 이 프로젝트는 5개 키워드만 요청해도 호출 수를 기록하고, 승인 플래그와 키가 모두 없으면 요청하지 않습니다.

잡코리아는 채용정보 API가 공공기관·학교에 우선 제공되며, 공식 API 계약은 개인 사용과 데이터베이스 수집 목적의 이용신청을 허용하지 않습니다. 공개 웹페이지를 자동 복사하는 우회 구현도 포함하지 않았습니다.

## 공식 출처

- 사람인 개인 회원 약관 (https://m.saramin.co.kr/index/clause) — 자동화된 수단/API를 통한 무단 접근과 DB 정보 수집 제한
- 사람인 채용정보 API 이용안내 (https://oapi.saramin.co.kr/guide/info) — 사전 승인과 access-key, 일 500회 제한
- 사람인 채용공고 API 명세 (https://oapi.saramin.co.kr/guide/job-search)
- 잡코리아 API 안내 (https://www.jobkorea.co.kr/service/api)
- 잡코리아 채용정보 API 이용약관 (https://www.jobkorea.co.kr/network/Popup_Xml.asp) — 개인 사용·DB 수집 목적 신청 제한

## 수동 공고 가져오기

브라우저에서 사용자가 직접 확인하고 지원 목적으로 관리할 공고만 JSON으로 저장합니다. 상세 공고 본문이나 기업의 비공개 정보는 불필요하게 복제하지 않습니다.

    [
      {
        "platform": "점핏",
        "platform_id": "example-id",
        "company": "회사명",
        "title": "공고명",
        "url": "https://example.com/job/example-id",
        "deadline": "2026-12-31",
        "location": "서울",
        "experience": "신입",
        "education": "학력무관",
        "employment_type": "정규직",
        "requirements": "사용자가 확인한 지원자격 요약",
        "source_kind": "user_reviewed_manual"
      }
    ]

실행 예:

    python -m hermes_job_automation.cli run --manual-file .\manual-postings.json
