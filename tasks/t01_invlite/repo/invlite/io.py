"""CSV persistence for the inventory."""
import csv

from invlite.models import ValidationError
from invlite.store import InventoryStore

FIELDS = ["sku", "name", "qty", "price"]


def load_csv(path):
    store = InventoryStore()
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                qty = int(row["qty"])
                price = float(row["price"])
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
