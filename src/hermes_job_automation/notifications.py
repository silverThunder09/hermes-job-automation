import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict


def send_telegram(settings, text: str) -> Dict[str, str]:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return {"status": "skipped", "reason": "TELEGRAM_CONFIGURATION_MISSING"}
    body = urllib.parse.urlencode(
        {
            "chat_id": settings.telegram_chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.telegram.org/bot{}/sendMessage".format(settings.telegram_bot_token),
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"status": "error", "reason": type(exc).__name__}
    if result.get("ok"):
        return {"status": "sent", "reason": "telegram_confirmed"}
    return {"status": "error", "reason": "telegram_rejected"}
