"""The control panel is local-only and token-gated."""

import json
import urllib.error
import urllib.request

import pytest

from manager_full_mcp import panel
from manager_full_mcp.config import Business, load_registry, save_registry


@pytest.fixture
def running_panel(env):
    registry = load_registry()
    registry.businesses = [
        Business(id="test-books", name="Test Books", api_url=env.base_url, api_key="TEST-KEY")
    ]
    save_registry(registry)
    panel._SERVER = None
    url = panel.start_panel(open_browser=False)
    yield url
    panel._SERVER.shutdown()
    panel._SERVER = None


def _call(url, path, body=None):
    origin = url.split("/?")[0]
    token = url.split("token=")[1]
    request = urllib.request.Request(
        f"{origin}{path}{'&' if '?' in path else '?'}token={token}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(request))


def test_state_lists_every_resource_with_its_boxes(running_panel):
    state = _call(running_panel, "/api/state")
    assert state["catalog_ready"] and len(state["groups"]) > 10
    total = sum(len(g["resources"]) for g in state["groups"])
    assert total > 300
    assert set(state["matrix"]["customers"]) == {"read", "create", "update", "delete"}


def test_saving_the_grid_takes_effect(running_panel):
    state = _call(running_panel, "/api/state")
    matrix = state["matrix"]
    matrix["customers"] = {"read": True, "create": True, "update": True, "delete": False}
    out = _call(
        running_panel,
        "/api/permissions",
        {"business": "test-books", "matrix": matrix, "raw_read": True, "raw_write": False},
    )
    assert out["ok"] and out["summary"]["source"] == "control-panel"
    assert out["summary"]["allowed"]["create"] == 1


def test_a_wrong_token_is_refused(running_panel):
    origin = running_panel.split("/?")[0]
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(f"{origin}/api/state?token=nope")
    assert caught.value.code == 403


def test_page_is_served_with_the_token(running_panel):
    html = urllib.request.urlopen(running_panel).read().decode()
    assert "Manager.io MCP" in html and "Save permissions" in html


def test_three_state_values_round_trip(running_panel):
    state = _call(running_panel, "/api/state")
    matrix = state["matrix"]
    matrix["customers"] = {"read": "allow", "create": "ask", "update": "allow", "delete": "deny"}
    matrix["tax_codes"] = {"read": "allow", "create": "ask", "update": "ask", "delete": "deny"}
    out = _call(
        running_panel,
        "/api/permissions",
        {"business": "test-books", "matrix": matrix, "raw_read": True, "raw_write": False},
    )
    assert out["ok"]
    assert out["summary"]["allowed"]["update"] == 1
    assert out["summary"]["ask_first"]["create"] == 2
    again = _call(running_panel, "/api/state")
    assert again["matrix"]["customers"]["create"] == "ask"
    assert again["matrix"]["customers"]["delete"] == "deny"


def test_state_marks_high_risk_resources(running_panel):
    state = _call(running_panel, "/api/state")
    rows = {r["name"]: r for g in state["groups"] for r in g["resources"]}
    assert rows["tax_codes"]["risk"] == "high"
    assert rows["tax_codes"]["risk_note"]
    assert rows["sales_invoices"]["risk"] == "normal"
    assert sum(1 for r in rows.values() if r["risk"] == "high") > 100
