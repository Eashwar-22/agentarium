"""Bounded, incremental reads of a JSONL event recording."""

from __future__ import annotations

from pathlib import Path
from .events import AgentEvent


class EventTail:
    def __init__(self, path: Path | str, chunk_bytes: int = 256 * 1024) -> None:
        self.path = Path(path)
        self.chunk_bytes = chunk_bytes
        self.offset = 0
        self.pending = b""
        self.signature = None
        self.identity = None
        self.prefix = b""
        self.has_more = False
        self.bytes_read = 0
        self.lines_parsed = 0
        self.invalid_lines = 0

    def poll(self) -> list[AgentEvent]:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            self.signature = self.identity = None
            self.offset, self.pending, self.prefix = 0, b"", b""
            self.has_more = False
            return []
        signature = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        if signature == self.signature and not self.has_more:
            return []
        identity = (stat.st_dev, stat.st_ino)
        with self.path.open("rb") as stream:
            prefix = stream.read(len(self.prefix) or min(256, stat.st_size))
            self.bytes_read += len(prefix)
            if identity != self.identity or stat.st_size < self.offset or (self.prefix and prefix != self.prefix):
                self.offset, self.pending = 0, b""
            self.prefix = prefix
            stream.seek(self.offset)
            chunk = stream.read(self.chunk_bytes)
        self.bytes_read += len(chunk)
        self.offset += len(chunk)
        self.identity, self.signature = identity, signature
        self.has_more = self.offset < stat.st_size
        lines = (self.pending + chunk).split(b"\n")
        self.pending = lines.pop()
        events = []
        for line in lines:
            if not line.strip():
                continue
            self.lines_parsed += 1
            try:
                events.append(AgentEvent.from_json(line.decode("utf-8")))
            except (UnicodeError, ValueError):
                self.invalid_lines += 1
        return events
