import pytest


def test_delete_item(store):
    removed = store.delete_item("A1")
    assert removed.sku == "A1"
    assert len(store) == 2


def test_delete_unknown(store):
    with pytest.raises(Exception):
        store.delete_item("ZZ")
