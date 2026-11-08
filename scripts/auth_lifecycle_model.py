"""Illustrative in-memory protocol, NOT an authentication/security adapter.

Only integer generations and nonsecret control states exist here. This module
has no filesystem/network/subprocess/environment/credential operations. Real
atomic markers, leases, validation and process isolation remain deployment gates.
"""
from dataclasses import dataclass


@dataclass
class LifecycleModel:
    state: str = "ready"
    credentials_generation: int = 0
    model_calls: int = 0
    release_allowed: bool = False
    owner: str = ""
    outcome: str = ""
    candidate_generation: int = 0

    def _require(self, state: str) -> None:
        if self.state != state:
            raise RuntimeError("INVALID_TRANSITION")

    def begin(self, owner: str, *, trusted: bool, lease: bool) -> None:
        self._require("ready")
        if trusted is not True or lease is not True:
            raise RuntimeError("TRUST_OR_EXCLUSIVE_LEASE_REQUIRED")
        self.state = "in_flight"
        self.owner = owner
        self.release_allowed = False
        self.model_calls += 1

    def client_finished(self, outcome: str, *, refreshed: bool) -> None:
        self._require("in_flight")
        self.outcome = outcome
        if outcome not in {"ok", "quota", "job_failed"}:
            self.state = "blocked"
            return
        self.candidate_generation = self.credentials_generation + int(refreshed)
        self.state = "pending_write"

    def write_back(self, result: str) -> None:
        self._require("pending_write")
        if result in {"ack", "unknown_after"}:
            self.credentials_generation = self.candidate_generation
        self.state = "pending_validation" if result == "ack" else "blocked"

    def verify_roundtrip(
        self, *, observed_generation: int, exact_match: bool, fresh_consumer: bool
    ) -> None:
        self._require("pending_validation")
        if (observed_generation != self.candidate_generation
                or exact_match is not True or fresh_consumer is not True):
            self.state = "blocked"
            raise RuntimeError("FRESH_EXACT_VALUE_VERIFICATION_REQUIRED")
        self.state = {"quota": "paused_quota", "job_failed": "paused_error"}.get(
            self.outcome, "ready"
        )
        self.release_allowed = True
        self.owner = ""
