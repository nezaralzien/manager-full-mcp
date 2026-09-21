"""'Ask first' must really stop and ask, and take no for an answer."""

import pytest

from manager_full_mcp import approval, engine, server as S
from manager_full_mcp.catalog import build_catalog
from manager_full_mcp.permissions import ALLOW, ASK, DENY, coerce_mode, load_policy, save_policy


class _Asked:
    """Records approval requests and decides the answer for the test."""

    def __init__(self) -> None:
        self.calls: list[approval.ApprovalRequest] = []
        self.answer = approval.ONCE

    def __len__(self) -> int:
        return len(self.calls)

    def __getitem__(self, index):
        return self.calls[index]

    def __eq__(self, other) -> bool:
        return self.calls == other


@pytest.fixture
def asked(monkeypatch):
    """Capture approval requests instead of opening a real dialog."""
    recorder = _Asked()

    async def fake_ask(request):
        recorder.calls.append(request)
        return recorder.answer

    monkeypatch.setattr(engine, "ask", fake_ask)
    approval.GRANTS.clear()
    yield recorder
    approval.GRANTS.clear()


async def _set(resource, **modes):
    session = await engine.get_session()
    policy = load_policy(session.business.id, session.catalog)
    policy.resources[resource] = {
        "read": ALLOW, "create": DENY, "update": DENY, "delete": DENY, **modes
    }
    save_policy(policy)


def test_modes_accept_old_boolean_files(openapi_doc):
    assert coerce_mode(True) == ALLOW
    assert coerce_mode(False) == DENY
    assert coerce_mode("ask") == ASK
    assert coerce_mode("nonsense") == DENY


def test_high_risk_group_ticked_in_the_extension_means_ask(openapi_doc, env, monkeypatch):
    monkeypatch.setenv("MANAGER_FULL_WRITE_TAX", "true")
    monkeypatch.setenv("MANAGER_FULL_WRITE_SALES", "true")
    from manager_full_mcp.permissions import policy_from_env

    catalog = build_catalog(openapi_doc)
    policy = policy_from_env("b", catalog)
    assert policy.decide(catalog.get("tax_codes"), "create") == ASK
    assert policy.decide(catalog.get("sales_invoices"), "create") == ALLOW


async def test_ask_stops_and_writes_only_after_approval(env, asked):
    await _set("customers", create=ASK)
    created = await S.manager_create("customers", {"Name": "Approved Co"})
    assert created["ok"] is True
    assert len(asked) == 1
    request = asked[0]
    assert request.operation == "create"
    assert "Approved Co" in request.details
    assert request.business == "Test Books"
    assert created["created_key"] in env.customers


async def test_declining_writes_nothing(env, asked):
    asked.answer = approval.DENY
    await _set("customers", create=ASK)
    out = await S.manager_create("customers", {"Name": "Rejected Co"})
    assert out["ok"] is False
    assert out["error"] == "approval_declined"
    assert env.customers.keys() == {"c1"}
    assert [c for c in env.calls if c[0] == "POST"] == []


async def test_no_dialog_available_is_treated_as_no(env, asked):
    asked.answer = approval.UNAVAILABLE
    await _set("customers", delete=ASK)
    out = await S.manager_delete("customers", "c1")
    assert out["ok"] is False
    assert out["error"] == "approval_unavailable"
    assert "c1" in env.customers


async def test_remember_skips_the_next_dialog(env, asked):
    asked.answer = approval.REMEMBER
    await _set("customers", create=ASK)
    await S.manager_create("customers", {"Name": "One"})
    await S.manager_create("customers", {"Name": "Two"})
    assert len(asked) == 1
    assert len(env.customers) == 3


async def test_delete_dialog_shows_what_will_be_deleted(env, asked):
    await _set("customers", delete=ASK)
    await S.manager_delete("customers", "c1")
    assert "Acme" in asked[0].details
    assert "c1" not in env.customers


async def test_allow_never_asks(env, asked):
    await _set("customers", create=ALLOW)
    await S.manager_create("customers", {"Name": "Silent"})
    assert asked == []


async def test_deny_never_asks(env, asked):
    await _set("customers", create=DENY)
    out = await S.manager_create("customers", {"Name": "Blocked"})
    assert out["error"] == "permission_denied"
    assert asked == []


async def test_tools_report_ask_first(env, asked):
    await _set("tax_codes", create=ASK)
    perms = await S.manager_permissions()
    assert "tax_codes(create)" in perms["ask_first"]
    catalog = await S.manager_catalog(search="tax_codes", limit=5)
    row = next(r for r in catalog["returned"] if r["resource"] == "tax_codes")
    assert row["ask_first"] == ["create"]
    assert row["risk"] == "high"
