"""Capture controls applied before events enter memory or the event file."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class CapturePolicy:
    """Retain full payloads, redact credential fields, and optionally redact text.

    ``redact_values`` removes explicitly supplied secrets from every captured
    string. ``redactor`` supports application-specific data such as PII.
    This is not a detector for every possible secret or private value.
    """

    full_payloads: bool = False
    redact_keys: tuple[str, ...] = (
        "password", "api_key", "authorization", "access_token",
        "refresh_token", "client_secret", "secret",
    )
    redact_values: tuple[str, ...] = ()
    redactor: Callable[[str], str] | None = None

    @classmethod
    def from_env(cls) -> "CapturePolicy":
        return cls(full_payloads=os.environ.get("AGENTARIUM_CAPTURE_FULL", "0").lower() in {"1", "true", "yes"})

    def sanitize(self, value: Any, key: str = "") -> Any:
        normalized = key.lower().replace("-", "_")
        if normalized in self.redact_keys:
            return "[REDACTED]"
        if isinstance(value, dict):
            return {
                name: self.sanitize(item, str(name))
                for name, item in value.items()
                if self.full_payloads or (not str(name).endswith("_full") and name != "full_output")
            }
        if isinstance(value, (list, tuple)):
            return [self.sanitize(item) for item in value]
        if isinstance(value, str):
            # SDK tool arguments and outputs often arrive as JSON strings.
            if value.lstrip().startswith(("{", "[")):
                try:
                    value = json.dumps(self.sanitize(json.loads(value)), ensure_ascii=False)
                except (ValueError, TypeError):
                    pass
            for secret in self.redact_values:
                if secret:
                    value = value.replace(secret, "[REDACTED]")
            return self.redactor(value) if self.redactor else value
        return value
