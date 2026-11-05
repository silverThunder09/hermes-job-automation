from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import Evaluation, Posting
from .state import normalize_url


HEADERS = [
    "수집일",
    "회사명",
    "지원현황",
    "적합도 점수",
    "공고명",
    "경력",
    "URL주소",
    "마감일",
    "지역",
    "플랫폼",
]
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class GoogleWorkspace:
    def __init__(self, settings, sheets_service=None, drive_service=None):
        self.settings = settings
        self.sheets_service = sheets_service
        self.drive_service = drive_service

    def _credentials(self):
        try:
            from google.oauth2.credentials import Credentials as UserCredentials
            from google.oauth2 import service_account
        except ImportError as exc:
            raise RuntimeError("Google client libraries are not installed.") from exc

        if self.settings.google_credentials:
            return service_account.Credentials.from_service_account_file(
                self.settings.google_credentials, scopes=SCOPES
            )
        token_file = self.settings.google_oauth_token_file
        if token_file.exists():
            return UserCredentials.from_authorized_user_file(str(token_file), SCOPES)
        if self.settings.google_oauth_client_secrets:
            from google_auth_oauthlib.flow import InstalledAppFlow

            flow = InstalledAppFlow.from_client_secrets_file(
                self.settings.google_oauth_client_secrets, SCOPES
            )
            credentials = flow.run_local_server(port=0)
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(credentials.to_json(), encoding="utf-8")
            return credentials
        raise RuntimeError("GOOGLE_WORKSPACE_CREDENTIALS_MISSING")

    def _sheets(self):
        if self.sheets_service is None:
            from googleapiclient.discovery import build

            self.sheets_service = build(
                "sheets", "v4", credentials=self._credentials(), cache_discovery=False
            )
        return self.sheets_service

    def _drive(self):
        if self.drive_service is None:
            from googleapiclient.discovery import build

            self.drive_service = build(
                "drive", "v3", credentials=self._credentials(), cache_discovery=False
            )
        return self.drive_service

    def _range(self, a1: str) -> str:
        tab = self.settings.google_sheet_tab.replace("'", "''")
        return "'{}'!{}".format(tab, a1)

    def append_postings(
        self,
        rows: Sequence[Tuple[Posting, Optional[Evaluation]]],
        collected_on: str,
    ) -> Dict[str, int]:
        if not self.settings.google_sheet_id:
            raise RuntimeError("GOOGLE_SHEET_ID_MISSING")
        api = self._sheets()
        response = (
            api.spreadsheets()
            .values()
            .get(spreadsheetId=self.settings.google_sheet_id, range=self._range("A:J"))
            .execute()
        )
        existing = response.get("values", [])
        if not existing:
            raise RuntimeError("Target sheet is empty; refusing to create an unexpected layout.")
        if existing[0][: len(HEADERS)] != HEADERS:
            raise RuntimeError("Target sheet headers do not match the requested 10-column layout.")

        seen_urls = {
            normalize_url(str(row[6]))
            for row in existing[1:]
            if len(row) > 6 and row[6]
        }
        new_rows = []
        for posting, evaluation in rows:
            canonical_url = normalize_url(posting.url)
            if canonical_url in seen_urls:
                continue
            score = (
                "{} · {}".format(evaluation.total, evaluation.eligibility)
                if evaluation
                else "확인 필요"
            )
            new_rows.append(
                [
                    collected_on,
                    posting.company,
                    "",
                    score,
                    posting.title,
                    posting.experience or "미확인",
                    posting.url,
                    posting.deadline or "미확인",
                    posting.location or "미확인",
                    posting.platform,
                ]
            )
            seen_urls.add(canonical_url)

        if not new_rows:
            return {"appended": 0, "duplicates": len(rows)}

        (
            api.spreadsheets()
            .values()
            .append(
                spreadsheetId=self.settings.google_sheet_id,
                range=self._range("A:J"),
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": new_rows},
            )
            .execute()
        )
        self._standardize_sheet(api, len(existing) + len(new_rows))
        return {"appended": len(new_rows), "duplicates": len(rows) - len(new_rows)}

    def _standardize_sheet(self, api, row_count: int) -> None:
        meta = (
            api.spreadsheets()
            .get(
                spreadsheetId=self.settings.google_sheet_id,
                fields="sheets(properties(sheetId,title,gridProperties(rowCount)))",
            )
            .execute()
        )
        sheet = next(
            (
                item
                for item in meta.get("sheets", [])
                if item.get("properties", {}).get("title") == self.settings.google_sheet_tab
            ),
            None,
        )
        if not sheet:
            raise RuntimeError("Configured Google Sheet tab was not found.")
        props = sheet["properties"]
        sheet_id = props["sheetId"]
        capacity = max(row_count, props.get("gridProperties", {}).get("rowCount", row_count))
        api.spreadsheets().batchUpdate(
            spreadsheetId=self.settings.google_sheet_id,
            body={
                "requests": [
                    {
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": 0,
                                "endRowIndex": capacity,
                                "startColumnIndex": 0,
                                "endColumnIndex": 10,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "textFormat": {"fontFamily": "Arial", "fontSize": 10},
                                    "horizontalAlignment": "LEFT",
                                    "verticalAlignment": "MIDDLE",
                                }
                            },
                            "fields": (
                                "userEnteredFormat.textFormat.fontFamily,"
                                "userEnteredFormat.textFormat.fontSize,"
                                "userEnteredFormat.horizontalAlignment,"
                                "userEnteredFormat.verticalAlignment"
                            ),
                        }
                    },
                    {
                        "sortRange": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": row_count,
                                "startColumnIndex": 0,
                                "endColumnIndex": 10,
                            },
                            "sortSpecs": [{"dimensionIndex": 0, "sortOrder": "DESCENDING"}],
                        }
                    },
                ]
            },
        ).execute()

    def find_or_create_company_folder(self, company: str) -> str:
        service = self._drive()
        safe_name = company.replace("'", "\\'")
        parent = self.settings.google_drive_parent_id
        parent_clause = " and '{}' in parents".format(parent) if parent else ""
        query = (
            "mimeType='application/vnd.google-apps.folder' and trashed=false "
            "and name='{}'{}".format(safe_name, parent_clause)
        )
        found = service.files().list(q=query, fields="files(id,name)", pageSize=10).execute()
        folders = found.get("files", [])
        if folders:
            return folders[0]["id"]
        body = {
            "name": company,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent:
            body["parents"] = [parent]
        return service.files().create(body=body, fields="id").execute()["id"]

    def upload_document(self, company: str, file_path: Path) -> str:
        from googleapiclient.http import MediaFileUpload

        folder_id = self.find_or_create_company_folder(company)
        uploaded = (
            self._drive()
            .files()
            .create(
                body={"name": file_path.name, "parents": [folder_id]},
                media_body=MediaFileUpload(
                    str(file_path),
                    mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    resumable=True,
                ),
                fields="id,webViewLink",
            )
            .execute()
        )
        return uploaded.get("webViewLink", uploaded["id"])
