import json
import re
from typing import Any, Dict, Iterable

from .models import Posting


def _numbers(text: str) -> set:
    return set(re.findall(r"\d+(?:[.,]\d+)?%?", text))


def _verified_numbers(profile: Dict[str, Any], posting: Posting) -> set:
    allowed = _numbers(json.dumps(profile, ensure_ascii=False))
    allowed.update(_numbers(json.dumps(posting.to_dict(), ensure_ascii=False)))
    return allowed


def validate_draft_numbers(profile: Dict[str, Any], posting: Posting, draft: Dict[str, str]) -> None:
    allowed = _verified_numbers(profile, posting)
    for field in ("resume", "cover_letter"):
        introduced = _numbers(draft.get(field, "")) - allowed
        if introduced:
            raise ValueError(
                "Draft introduces unverified numeric claims: {}".format(", ".join(sorted(introduced)))
            )


class OpenAIWriter:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client

    def draft(self, posting: Posting, profile: Dict[str, Any]) -> Dict[str, str]:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY_MISSING")
        if not self.settings.openai_model:
            raise RuntimeError("OPENAI_MODEL_MISSING")
        client = self.client
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=self.settings.openai_api_key)
        prompt = (
            "Write a Korean, company-specific resume summary and cover letter using only "
            "the supplied verified facts. Preserve the applicant's real education and employment "
            "history. Never invent a skill, employer, title, outcome, or metric. Do not imply paid "
            "backend employment; the applicant has zero years of paid backend experience and nine "
            "months of paid QA experience. Focus on project evidence. Return JSON with string keys "
            "resume and cover_letter.\n\nPROFILE:\n"
            + json.dumps(profile, ensure_ascii=False)
            + "\n\nPOSTING:\n"
            + json.dumps(posting.to_dict(), ensure_ascii=False)
        )
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Write only from evidence and return valid JSON."},
                {"role": "user", "content": prompt},
            ],
        )
        draft = json.loads(response.choices[0].message.content or "{}")
        if not isinstance(draft.get("resume"), str) or not isinstance(
            draft.get("cover_letter"), str
        ):
            raise ValueError("The generated draft has an invalid structure.")
        validate_draft_numbers(profile, posting, draft)
        return draft
