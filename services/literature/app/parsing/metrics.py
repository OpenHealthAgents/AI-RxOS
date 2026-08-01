from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock


@dataclass
class ParserMetrics:
    counters: dict[str, int] = field(
        default_factory=lambda: {
            "parser.documents_parsed": 0,
            "parser.documents_validated": 0,
            "parser.parse_errors": 0,
            "parser.validation_failures": 0,
            "parser.duplicate_documents": 0,
        }
    )
    lock: Lock = field(default_factory=Lock)

    def increment(self, name: str, amount: int = 1) -> None:
        with self.lock:
            self.counters[name] = self.counters.get(name, 0) + amount

    def snapshot(self) -> dict[str, int]:
        with self.lock:
            return dict(self.counters)


parser_metrics = ParserMetrics()
