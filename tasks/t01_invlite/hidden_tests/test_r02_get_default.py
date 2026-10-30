import pytest


def test_get_existing(store):
    assert store.get("A1").name == "Green Apple"


def test_get_default_value(store):
    assert store.get("ZZ", 42) == 42


def test_get_default_none(store):
    assert store.get("ZZ", None) is None


def test_get_missing_without_default_fails(store):
    with pytest.raises(Exception):
        store.get("ZZ")
