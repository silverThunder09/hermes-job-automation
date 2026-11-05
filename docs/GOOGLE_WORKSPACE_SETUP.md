# Google Sheets와 Drive 연결

기존 스프레드시트 백엔드_채용공고_통합관리의 전체공고 탭을 사용합니다. 프로젝트는 다음 10개 열을 확인한 뒤 새 행만 추가합니다.

    수집일, 회사명, 지원현황, 적합도 점수, 공고명, 경력, URL주소, 마감일, 지역, 플랫폼

기존 URL을 먼저 읽어 정규화 중복을 확인합니다. 시트 헤더가 다르거나 Google 인증이 없으면 변경을 중단합니다. 데이터 셀 값은 덮어쓰지 않습니다.

## OAuth 데스크톱 연결

1. Google Cloud Console에서 Sheets API와 Drive API를 켭니다.
2. 사용자 소유의 Desktop OAuth client를 만들고 JSON을 프로젝트 밖의 안전한 로컬 경로에 저장합니다.
3. .env의 GOOGLE_OAUTH_CLIENT_SECRETS에 JSON 경로를 지정합니다.
4. 처음 실행할 때 브라우저에서 Google 권한 승인을 완료합니다.
5. GOOGLE_SHEET_ID를 기존 스프레드시트 ID로 지정하고 GOOGLE_SHEET_TAB=전체공고로 둡니다.
6. GOOGLE_DRIVE_PARENT_ID는 회사별 폴더를 만들 상위 폴더가 있을 때만 지정합니다. 비워 두면 내 드라이브 최상위에 회사별 폴더를 만듭니다.

OAuth token 파일은 .gitignore에 포함되며 data/google-token.json에 저장됩니다. 토큰을 다른 사람에게 전달하지 마세요.

## 서비스 계정 연결

1. Google Cloud에서 서비스 계정을 만들고 Sheets 및 Drive API를 켭니다.
2. JSON 키를 프로젝트 밖의 로컬 비밀 경로에 저장하고 GOOGLE_APPLICATION_CREDENTIALS로 지정합니다.
3. 스프레드시트와 Drive 상위 폴더를 해당 서비스 계정 이메일에 공유합니다.
4. 이미 공유받은 사용자 소유 파일에서 서비스 계정이 권한을 가지는지 확인합니다.

Google Workspace API를 직접 호출하는 이 프로젝트는 Codex Google Drive 연결의 자격 증명을 자동으로 가져오지 않습니다. 현재 Codex 연결로 시트에 반영한 결과와 예약 실행용 API 자격 증명은 별도로 관리됩니다.
