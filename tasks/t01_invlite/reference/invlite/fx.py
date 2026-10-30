"""Currency conversion of the inventory value (standard library only)."""
import json
import urllib.error
import urllib.request

from invlite.models import AppError, ValidationError


class FxError(AppError):
    """Raised when exchange rates cannot be fetched or used."""


def _fetch_rates(rates_url, timeout=10):
    try:
        with urllib.request.urlopen(rates_url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise FxError(f"cannot load rates from {rates_url}: {exc}") from exc


def convert_total(store, currency, rates_url):
    data = _fetch_rates(rates_url)
    base = data.get("base")
    total = store.total_value()
    if currency == base:
        return total
    rates = data.get("rates") or {}
    if currency not in rates:
        raise ValidationError(f"no exchange rate for {currency}")
    return round(total * float(rates[currency]), 2)
