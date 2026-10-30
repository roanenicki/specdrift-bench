import pytest

from invlite import InventoryStore


@pytest.fixture
def store():
    s = InventoryStore()
    s.add_item("A1", "Green Apple", 10, 0.5)
    s.add_item("B2", "Banana", 4, 0.25)
    s.add_item("C3", "apple pie", 2, 3.0)
    return s


def write_csv(path, rows):
    lines = ["sku,name,qty,price"] + [",".join(f'"{c}"' for c in r) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
