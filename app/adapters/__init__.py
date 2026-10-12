"""Hardware contracts only; no banking connection or simulated confirmation."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class WeightReading:
    milligrams: int
    stable: bool
    timestamp: datetime
    error: str | None = None


class ScaleAdapter(Protocol):
    def read_stable_weight(self) -> WeightReading: ...


class PaymentTerminalAdapter(Protocol):
    def start(self, request_key: str, amount_rial: int) -> str: ...
    def status(self, request_key: str) -> str: ...
    def cancel(self, request_key: str) -> str: ...


class UnavailableTerminal:
    def start(self, request_key, amount_rial):
        return "unavailable"

    def status(self, request_key):
        return "unknown"

    def cancel(self, request_key):
        return "unavailable"
