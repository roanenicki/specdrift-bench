import pytest

from conftest import write_csv
from invlite import load_csv


@pytest.mark.parametrize("raw", ["12.50 EUR", "EUR 12.50", "12.50€", "12,50 EUR", "12.5", "12,50"])
def test_price_formats(tmp_path, raw):
    p = tmp_path / "inv.csv"
    write_csv(p, [("A1", "Apple", "2", raw)])
    assert load_csv(p).get("A1").price == pytest.approx(12.5)


@pytest.mark.parametrize("raw", ["abc", "EUR", "12.5.3 EUR"])
def test_bad_price_rejected(tmp_path, raw):
    p = tmp_path / "inv.csv"
    write_csv(p, [("A1", "Apple", "2", raw)])
    with pytest.raises(Exception):
        load_csv(p)
