import pytest


def test_search_case_insensitive_sorted(store):
    assert [i.sku for i in store.search("APPLE")] == ["A1", "C3"]


def test_search_no_match(store):
    assert store.search("kiwi") == []


@pytest.mark.parametrize("q", ["", "   "])
def test_search_empty_query_fails(store, q):
    with pytest.raises(Exception):
        store.search(q)
