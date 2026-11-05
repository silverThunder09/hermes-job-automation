from dataclasses import dataclass, field
from typing import List, Optional

from ..models import Posting


@dataclass
class CollectionResult:
    platform: str
    status: str
    postings: List[Posting] = field(default_factory=list)
    message: str = ""
    error: Optional[str] = None


class Collector:
    platform = "unknown"

    def collect(self) -> CollectionResult:
        raise NotImplementedError


class ManualOnlyCollector(Collector):
    def __init__(self, note: str):
        self.note = note

    def collect(self) -> CollectionResult:
        return CollectionResult(
            platform=self.platform,
            status="manual_only",
            message=self.note,
        )
