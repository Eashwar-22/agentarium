"""Small, dependency-free loading of local development environment files."""

from __future__ import annotations

import os
import shlex
from pathlib import Path


def load_env_file(path: Path | str | None = None) -> bool:
    """Load unset variables from `.env` without printing sensitive values.

    A real shell environment always wins. This keeps deployment configuration
    intact while making local demo scripts work without `source .env`.
    """

    env_path = Path(path) if path else Path.cwd() / ".env"
    if not env_path.is_file():
        return False

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or not key or key in os.environ:
            continue
        try:
            values = shlex.split(raw_value.strip(), comments=True, posix=True)
        except ValueError:
            values = [raw_value.strip()]
        if values:
            os.environ[key] = " ".join(values)
    return True
