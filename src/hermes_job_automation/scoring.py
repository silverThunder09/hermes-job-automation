import json
from typing import Any, Dict, Optional

from .models import Evaluation, Posting


WEIGHTS = {
    "technical_fit": 35,
    "work_fit": 30,
    "project_fit": 25,
    "preferred_qualifications": 10,
}


def validate_evaluation(payload: Dict[str, Any], model: str = "") -> Evaluation:
    evaluation = Evaluation(
        technical_fit=int(payload["technical_fit"]),
        work_fit=int(payload["work_fit"]),
        project_fit=int(payload["project_fit"]),
        preferred_qualifications=int(payload["preferred_qualifications"]),
        total=int(payload["total"]),
        rationale=list(payload.get("rationale") or []),
        gaps=list(payload.get("gaps") or []),
        eligibility=str(payload.get("eligibility") or "review"),
        model=model,
    )
    evaluation.validate()
    if evaluation.eligibility not in {"eligible", "excluded", "review"}:
        raise ValueError("Eligibility must be eligible, excluded, or review.")
    return evaluation


def build_prompt(posting: Posting, profile: Dict[str, Any]) -> str:
    return (
        "Evaluate this job posting against the applicant's verified profile. "
        "Return one JSON object with integer keys technical_fit (0-35), work_fit (0-30), "
        "project_fit (0-25), preferred_qualifications (0-10), total, eligibility "
        "(eligible/excluded/review), rationale (array), and gaps (array). "
        "The total must equal the four components. Exclude only explicit unmet mandatory "
        "education or backend experience requirements. Treat missing details as review. "
        "QA tenure does not count as paid backend experience. Do not invent applicant facts, "
        "job requirements, metrics, or preferred qualifications.\n\n"
        "VERIFIED APPLICANT PROFILE:\n"
        + json.dumps(profile, ensure_ascii=False)
        + "\n\nJOB POSTING:\n"
        + json.dumps(posting.to_dict(), ensure_ascii=False)
    )


class OpenAIScorer:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client

    def evaluate(self, posting: Posting, profile: Dict[str, Any]) -> Evaluation:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY_MISSING")
        if not self.settings.openai_model:
            raise RuntimeError("OPENAI_MODEL_MISSING")
        client = self.client
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("Install the OpenAI SDK to use API scoring.") from exc
            client = OpenAI(api_key=self.settings.openai_api_key)
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a careful job-fit evaluator. Return valid JSON only.",
                },
                {"role": "user", "content": build_prompt(posting, profile)},
            ],
        )
        content = response.choices[0].message.content or ""
        payload = json.loads(content)
        return validate_evaluation(payload, model=self.settings.openai_model)
