import inspect
import typing

from invlite.store import InventoryStore

PUBLIC = [n for n, f in inspect.getmembers(InventoryStore, inspect.isfunction) if not n.startswith("_")]


def test_all_public_methods_fully_annotated():
    for name in PUBLIC:
        fn = getattr(InventoryStore, name)
        hints = typing.get_type_hints(fn)
        params = [p for p in inspect.signature(fn).parameters if p != "self"]
        missing = [p for p in params if p not in hints]
        assert not missing, f"{name}: missing hints for {missing}"
        assert "return" in hints, f"{name}: missing return hint"


def test_core_types():
    hints = typing.get_type_hints(InventoryStore.add_item)
    assert hints["sku"] is str and hints["qty"] is int
