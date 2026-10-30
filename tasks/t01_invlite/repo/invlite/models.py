"""Core data types for invlite."""
from dataclasses import dataclass


class AppError(Exception):
    """Base error for every failure raised by invlite."""


class NotFoundError(AppError):
    """Raised when a SKU does not exist in the store."""


class ValidationError(AppError):
    """Raised when user input is invalid."""


@dataclass
class Item:
    sku: str
    name: str
    qty: int
    price: float

    def value(self) -> float:
        return self.qty * self.price
