from pathlib import Path
from typing import Dict

from .application import DraftOnlyApplication


FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "application_form.html"


def run_local_form_dry_run() -> Dict[str, str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Install Playwright, then run playwright install chromium.") from exc
    settings = type("SettingsView", (), {"form_autofill_enabled": True})()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(FIXTURE.as_uri())
        result = DraftOnlyApplication(settings).fill_known_fields(
            page,
            {
                "이름": "검증용 이름",
                "이메일": "dry-run@example.invalid",
                "지원동기": "검증용 문장입니다.",
            },
        )
        fields = page.locator("input, textarea").evaluate_all(
            "(items) => items.map(item => ({name: item.name, value: item.value}))"
        )
        submitted = page.locator("body").get_attribute("data-submitted")
        browser.close()
    return {
        "status": result["status"],
        "filled_fields": result.get("filled_fields", ""),
        "form_values_verified": str(all(item["value"] for item in fields)),
        "submission_occurred": str(submitted == "true"),
    }
