import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

RATES = {"base": "EUR", "rates": {"USD": 1.08, "XAF": 655.957}}


@pytest.fixture
def rates_url():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(RATES).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}/rates.json"
    srv.shutdown()


def test_convert_usd(store, rates_url):
    from invlite.fx import convert_total

    assert convert_total(store, "USD", rates_url) == round(store.total_value() * 1.08, 2)


def test_convert_base(store, rates_url):
    from invlite.fx import convert_total

    assert convert_total(store, "EUR", rates_url) == store.total_value()


def test_convert_unknown(store, rates_url):
    from invlite.fx import convert_total

    with pytest.raises(Exception):
        convert_total(store, "JPY", rates_url)
