from dataclasses import dataclass
from .units import DomainError, integer, ratio_round


@dataclass(frozen=True)
class Stock:
    qty: int = 0
    value: int = 0

    def __post_init__(self):
        integer(self.qty)
        integer(self.value)
        if self.qty == 0 and self.value != 0:
            raise DomainError("موجودی صفر باید ارزش صفر داشته باشد")

    def receive(self, qty: int, value: int) -> "Stock":
        integer(qty, minimum=1)
        integer(value)
        return Stock(integer(self.qty + qty), integer(self.value + value))

    def issue(self, qty: int) -> tuple["Stock", int]:
        integer(qty, minimum=1)
        if qty > self.qty:
            raise DomainError("موجودی کافی نیست")
        cost = self.value if qty == self.qty else ratio_round(self.value, qty, self.qty)
        return Stock(self.qty - qty, self.value - cost), cost
