"""In-memory inventory store."""
from typing import Dict, List

from invlite.log import get_logger
from invlite.models import Item, NotFoundError, ValidationError

logger = get_logger(__name__)


class InventoryStore:
    def __init__(self):
        self._items: Dict[str, Item] = {}

    def add_item(self, sku, name, qty, price):
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
        logger.debug("added %s", sku)
        return item

    def remove_item(self, sku):
        if sku not in self._items:
            raise NotFoundError(f"unknown sku {sku}")
        logger.debug("removed %s", sku)
        return self._items.pop(sku)

    def get(self, sku):
        if sku not in self._items:
            raise NotFoundError(f"unknown sku {sku}")
        return self._items[sku]

    def adjust_qty(self, sku, delta):
        item = self.get(sku)
        new_qty = item.qty + int(delta)
        if new_qty < 0:
            raise ValidationError(f"qty for {sku} would become negative")
        item.qty = new_qty
        logger.debug("adjusted %s by %s", sku, delta)
        return item

    def list_items(self) -> List[Item]:
        return sorted(self._items.values(), key=lambda i: i.sku)

    def total_value(self) -> float:
        return round(sum(i.value() for i in self._items.values()), 2)

    def __len__(self):
        return len(self._items)
