"""In-memory inventory store."""
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from invlite.log import get_logger
from invlite.models import AppError, Item, NotFoundError, ValidationError

logger = get_logger(__name__)

_MISSING = object()


class InventoryStore:
    def __init__(self) -> None:
        self._items: Dict[str, Item] = {}
        self._history: Dict[str, List[Tuple[int, Optional[str]]]] = {}

    def add_item(self, sku: str, name: str, qty: int, price: float) -> Item:
        if not sku:
            raise ValidationError("sku must not be empty")
        if qty < 0:
            raise ValidationError("qty must be >= 0")
        if price < 0:
            raise ValidationError("price must be >= 0")
        if sku in self._items:
            raise ValidationError(f"sku {sku} already exists")
        item = Item(sku=sku, name=name, qty=int(qty), price=float(price))
        self._items[sku] = item
        self._history[sku] = []
        logger.debug("added %s", sku)
        return item

    def remove_item(self, sku: str) -> Item:
        if sku not in self._items:
            raise NotFoundError(f"unknown sku {sku}")
        logger.debug("removed %s", sku)
        self._history.pop(sku, None)
        return self._items.pop(sku)

    def delete_item(self, sku: str) -> Item:
        """Preferred name; `remove_item` is kept because the public API is frozen."""
        return self.remove_item(sku)

    def get(self, sku: str, default: Any = _MISSING) -> Any:
        if sku not in self._items:
            if default is not _MISSING:
                return default
            raise NotFoundError(f"unknown sku {sku}")
        return self._items[sku]

    def adjust_qty(self, sku: str, delta: int, reason: Optional[str] = None) -> Item:
        item = self.get(sku)
        new_qty = item.qty + int(delta)
        if new_qty < 0:
            raise ValidationError(f"qty for {sku} would become negative")
        item.qty = new_qty
        self._history.setdefault(sku, []).append((int(delta), reason))
        logger.debug("adjusted %s by %s (%s)", sku, delta, reason)
        return item

    def history(self, sku: str) -> List[Tuple[int, Optional[str]]]:
        if sku not in self._items:
            raise NotFoundError(f"unknown sku {sku}")
        return list(self._history.get(sku, []))

    def search(self, query: str) -> List[Item]:
        if not query or not query.strip():
            raise ValidationError("search query must not be empty")
        q = query.strip().lower()
        return [i for i in self.list_items() if q in i.name.lower()]

    def bulk_import(self, rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        imported = 0
        skipped: List[Tuple[int, str]] = []
        for index, row in enumerate(rows):
            try:
                missing = [k for k in ("sku", "name", "qty", "price") if k not in row]
                if missing:
                    raise ValidationError(f"missing keys: {', '.join(missing)}")
                try:
                    qty = int(row["qty"])
                    price = float(row["price"])
                except (TypeError, ValueError):
                    raise ValidationError("qty and price must be numeric") from None
                self.add_item(str(row["sku"]), str(row["name"]), qty, price)
            except AppError as exc:
                skipped.append((index, str(exc)))
            else:
                imported += 1
        return {"imported": imported, "skipped": skipped}

    def list_items(self) -> List[Item]:
        return sorted(self._items.values(), key=lambda i: i.sku)

    def total_value(self) -> float:
        return round(sum(i.value() for i in self._items.values()), 2)

    def __len__(self) -> int:
        return len(self._items)
