"""Structured error types used across NETLAB."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class NetlabError(Exception):
    code: str
    message: str
    component: str = "core"
    details: Dict[str, Any] = field(default_factory=dict)
    recommendation: str = "Inspect Diagnostics and the correlated command log."
    command_id: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "component": self.component,
            "details": self.details,
            "recommendation": self.recommendation,
            "command_id": self.command_id,
        }


class ValidationError(NetlabError):
    pass


class RuntimeUnavailableError(NetlabError):
    pass


class CommandTimeoutError(NetlabError):
    pass
