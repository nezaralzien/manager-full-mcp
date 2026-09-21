"""A stub Manager instance: the real OpenAPI document, a tiny data set."""

from __future__ import annotations

import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SPEC = Path(__file__).parent / "data" / "openapi.json"


class _Store:
    def __init__(self) -> None:
        self.customers: dict[str, dict] = {
            "c1": {"Key": "c1", "Name": "Acme", "Code": "A-1", "EmailAddress": "a@acme.test"}
        }
        self.calls: list[tuple[str, str]] = []


def _handler(store: _Store, doc: dict):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: D102
            return

        def _json(self, payload, status=200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read(self):
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"{}")

        def _auth(self) -> bool:
            if self.headers.get("X-API-KEY") == "TEST-KEY":
                return True
            self._json({"error": "bad key"}, 401)
            return False

        def do_GET(self):
            store.calls.append(("GET", self.path))
            if not self._auth():
                return
            path = self.path.split("?")[0]
            if path in ("/api2", "/api2/"):
                self._json(doc)
                return
            if path == "/api2/customers":
                self._json(
                    {"customers": list(store.customers.values()),
                     "totalRecords": len(store.customers)}
                )
                return
            match = re.fullmatch(r"/api2/customer-form/(.+)", path)
            if match:
                record = store.customers.get(match.group(1))
                self._json(record or {"error": "not found"}, 200 if record else 404)
                return
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            store.calls.append(("POST", self.path))
            if not self._auth():
                return
            body = self._read()
            if self.path == "/api2/customer-form":
                key = uuid.uuid4().hex[:8]
                body["Key"] = key
                store.customers[key] = body
                self._json({"Key": key}, 201)
                return
            self._json({"error": "not found"}, 404)

        def do_PUT(self):
            store.calls.append(("PUT", self.path))
            if not self._auth():
                return
            body = self._read()
            match = re.fullmatch(r"/api2/customer-form/(.+)", self.path)
            if match and match.group(1) in store.customers:
                body["Key"] = match.group(1)
                store.customers[match.group(1)] = body
                self._json(body)
                return
            self._json({"error": "not found"}, 404)

        def do_DELETE(self):
            store.calls.append(("DELETE", self.path))
            if not self._auth():
                return
            match = re.fullmatch(r"/api2/customer-form/(.+)", self.path)
            if match and store.customers.pop(match.group(1), None) is not None:
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._json({"error": "not found"}, 404)

    return Handler


@pytest.fixture(scope="session")
def openapi_doc() -> dict:
    return json.loads(SPEC.read_text(encoding="utf-8"))


@pytest.fixture
def manager(openapi_doc):
    store = _Store()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(store, openapi_doc))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    store.base_url = f"http://127.0.0.1:{server.server_address[1]}/api2"
    yield store
    server.shutdown()


@pytest.fixture
def env(tmp_path, manager, monkeypatch):
    """Isolated config home pointed at the stub instance."""
    monkeypatch.setenv("MANAGER_FULL_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MANAGER_API_URL", manager.base_url)
    monkeypatch.setenv("MANAGER_API_KEY", "TEST-KEY")
    monkeypatch.setenv("MANAGER_BUSINESS_NAME", "Test Books")
    for name in list(__import__("os").environ):
        if name.startswith("MANAGER_FULL_") and name != "MANAGER_FULL_HOME":
            monkeypatch.delenv(name, raising=False)
    from manager_full_mcp import engine

    engine.clear_sessions()
    yield manager
    engine.clear_sessions()
