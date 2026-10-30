import pytest

from invlite import InventoryStore, NotFoundError, ValidationError


def make_store():
    s = InventoryStore()
    s.add_item("A1", "Apple", 10, 0.5)
    s.add_item("B2", "Banana", 4, 0.25)
    return s


def test_total_value():
    assert make_store().total_value() == 6.0


def test_remove_and_get():
    s = make_store()
    s.remove_item("A1")
    with pytest.raises(NotFoundError):
        s.get("A1")


def test_adjust_negative():
    with pytest.raises(ValidationError):
        make_store().adjust_qty("B2", -5)


def test_csv_roundtrip(tmp_path):
    from invlite import load_csv, save_csv

    p = tmp_path / "inv.csv"
    save_csv(make_store(), p)
    assert load_csv(p).total_value() == 6.0
