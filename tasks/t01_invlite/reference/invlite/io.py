"""CSV persistence for the inventory."""
import csv
import re

from invlite.models import ValidationError
from invlite.store import InventoryStore

FIELDS = ["sku", "name", "qty", "price"]

_PRICE_RE = re.compile(r"^\s*(?:[A-Za-z]{3}|€)?\s*(\d+(?:[.,]\d+)?)\s*(?:[A-Za-z]{3}|€)?\s*$")


def _parse_price(raw):
    m = _PRICE_RE.match(raw or "")
    if not m:
        raise ValidationError(f"cannot parse price {raw!r}")
    return float(m.group(1).replace(",", "."))


def load_csv(path):
    store = InventoryStore()
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                qty = int(row["qty"])
                price = _parse_price(row["price"])
            except (KeyError, ValueError) as exc:
                raise ValidationError(f"bad row {row}: {exc}") from exc
            store.add_item(row["sku"], row["name"], qty, price)
    return store


def save_csv(store, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for item in store.list_items():
            writer.writerow({"sku": item.sku, "name": item.name, "qty": item.qty, "price": item.price})
