import pytest


def test_history_records_changes(store):
    store.adjust_qty("A1", 5, "restock")
    store.adjust_qty("A1", -2, reason="sale")
    assert store.history("A1") == [(5, "restock"), (-2, "sale")]
    assert store.get("A1").qty == 13


def test_history_empty(store):
    assert store.history("B2") == []


def test_history_unknown_sku(store):
    with pytest.raises(Exception):
        store.history("ZZ")
