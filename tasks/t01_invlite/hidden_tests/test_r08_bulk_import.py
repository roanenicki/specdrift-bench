from invlite import InventoryStore


def test_bulk_import_mixed():
    s = InventoryStore()
    rows = [
        {"sku": "A1", "name": "Apple", "qty": 3, "price": 0.5},
        {"sku": "B2", "name": "Banana"},  # missing keys
        {"sku": "C3", "name": "Cherry", "qty": "x", "price": 1},  # bad qty
        {"sku": "D4", "name": "Date", "qty": 1, "price": -2},  # negative price
        {"sku": "A1", "name": "Apple again", "qty": 1, "price": 1},  # duplicate
        {"sku": "E5", "name": "Elderberry", "qty": "7", "price": "1.25"},
    ]
    report = s.bulk_import(rows)
    assert report["imported"] == 2
    assert [idx for idx, _ in report["skipped"]] == [1, 2, 3, 4]
    assert all(isinstance(reason, str) and reason for _, reason in report["skipped"])
    assert len(s) == 2 and s.get("E5").qty == 7


def test_bulk_import_generator():
    s = InventoryStore()
    report = s.bulk_import({"sku": f"S{i}", "name": "x", "qty": i, "price": 1} for i in range(3))
    assert report == {"imported": 3, "skipped": []}
