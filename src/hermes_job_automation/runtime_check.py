"""Offline browser proof only: no operational settings, profiles or live sites."""
from typing import Any, Dict


_SYNTHETIC_HTML = """<!doctype html>
<html lang="ko"><meta charset="utf-8"><title>합성 실행 진단</title>
<h1 id="heading">한국어 브라우저 확인</h1>
<p id="javascript-result"></p>
<form id="application">
  <label>이름 <input id="name" name="name"></label>
  <label>직무 <select id="role" name="role"><option value="">선택</option>
    <option value="backend">백엔드 개발</option></select></label>
  <label><input id="consent" type="checkbox">합성 입력 확인</label>
  <button type="submit" disabled>제출 금지</button>
</form>
<script>
window.runtimeProbe = {submissions: 0};
document.getElementById('javascript-result').textContent = '자바스크립트 실행 확인';
document.getElementById('application').addEventListener('submit', event => {
  event.preventDefault();
  window.runtimeProbe.submissions += 1;
});
</script></html>"""


def run_runtime_check() -> Dict[str, Any]:
    """Return JSON-safe observations from a fresh headless Chromium context.

    This verifies only built-in synthetic content, never an account, production
    configuration, model, database or scheduler. No form submission is attempted.
    """
    result: Dict[str, Any] = {
        "schema_version": 1,
        "status": "error",
        "browser": {"engine": "chromium", "version": None, "headless": True},
        "checks": {name: False for name in (
            "korean_dom", "javascript", "form_fill", "no_submission", "no_page_requests",
        )},
        "page_network_requests": None,
        "submission_occurred": None,
        "scope": {
            "synthetic_html": True,
            "offline_context": False,
            "external_requests_blocked": False,
            "live_site_verified": False,
            "model_verified": False,
            "authentication_verified": False,
            "database_verified": False,
            "schedule_verified": False,
        },
    }
    requests = []
    observing_requests = False
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            with playwright.chromium.launch(headless=True) as browser:
                result["browser"]["version"] = browser.version
                with browser.new_context(offline=True, service_workers="block") as context:
                    result["scope"]["offline_context"] = True
                    context.route("**/*", lambda route: route.abort())
                    result["scope"]["external_requests_blocked"] = True
                    page = context.new_page()
                    page.set_default_timeout(5000)
                    page.on("request", lambda request: requests.append(request))
                    observing_requests = True
                    page.set_content(_SYNTHETIC_HTML, wait_until="load")
                    checks = result["checks"]
                    checks["korean_dom"] = page.locator("#heading").inner_text() == "한국어 브라우저 확인"
                    checks["javascript"] = page.locator("#javascript-result").inner_text() == "자바스크립트 실행 확인"
                    page.locator("#name").fill("합성 지원자")
                    page.locator("#role").select_option("backend")
                    page.locator("#consent").check()
                    checks["form_fill"] = (
                        page.locator("#name").input_value() == "합성 지원자"
                        and page.locator("#role").input_value() == "backend"
                        and page.locator("#consent").is_checked()
                    )
                    result["submission_occurred"] = page.evaluate("window.runtimeProbe.submissions !== 0")
                    checks["no_submission"] = not result["submission_occurred"]
        checks["no_page_requests"] = len(requests) == 0
        result["status"] = "verified" if all(checks.values()) else "failed"
    except Exception as exc:
        result["error"] = {
            "type": type(exc).__name__,
            "message": "Offline browser diagnostic could not complete.",
        }
    finally:
        if observing_requests:
            result["page_network_requests"] = len(requests)
    return result
