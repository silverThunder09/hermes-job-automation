from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Posting:
    platform: str
    title: str
    company: str
    url: str
    platform_id: Optional[str] = None
    deadline: Optional[str] = None
    location: Optional[str] = None
    experience: Optional[str] = None
    education: Optional[str] = None
    employment_type: Optional[str] = None
    skills: List[str] = field(default_factory=list)
    requirements: str = ""
    collected_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    source_kind: str = "official_api"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Posting":
        allowed = set(cls.__dataclass_fields__.keys())
        return cls(**{key: value for key, value in data.items() if key in allowed})


@dataclass
class Eligibility:
    status: str
    reasons: List[str] = field(default_factory=list)
    missing_information: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Evaluation:
    technical_fit: int
    work_fit: int
    project_fit: int
    preferred_qualifications: int
    total: int
    rationale: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    eligibility: str = "review"
    model: str = ""
    evaluated_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())

    def validate(self) -> None:
        values = [
            self.technical_fit,
            self.work_fit,
            self.project_fit,
            self.preferred_qualifications,
        ]
        caps = [35, 30, 25, 10]
        if any(value < 0 or value > cap for value, cap in zip(values, caps)):
            raise ValueError("Score component exceeds its allowed range.")
        if self.total != sum(values):
            raise ValueError("Total score must equal the four score components.")
        if self.total > 100:
            raise ValueError("Total score cannot exceed 100.")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
