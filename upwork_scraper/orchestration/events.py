"""Events passed from platform workers to the central processor."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import JobLead


@dataclass(frozen=True)
class KeywordResult:
    platform_worker: str
    keyword: str
    leads: list[JobLead] = field(default_factory=list)
    error: str = ""


@dataclass(frozen=True)
class PlatformFinished:
    platform_worker: str
