"""End-to-end tool behaviour against a stub Manager instance."""

import pytest

from manager_full_mcp import engine, server as S
from manager_full_mcp.catalog import build_catalog
from manager_full_mcp.permissions import load_policy, save_policy


async def _allow(business_id, resource, **ops):
    session = await engine.get_session()
    policy = load_policy(business_id, session.catalog)
    policy.resources[resource] = {
        "read": True, "create": False, "update": False, "delete": False, **ops
    }
    save_policy(policy)


async def test_read_works_out_of_the_box(env):
    listed = await S.manager_list("customers")
    assert listed["ok"] and listed["count"] == 1
    record = await S.manager_get("customers", "c1")
    assert record["body"]["Name"] == "Acme"


async def test_writes_are_refused_with_a_useful_message(env):
    denied = await S.manager_create("customers", {"Name": "Nope"})
    assert denied["ok"] is False
    assert denied["error"] == "permission_denied"
    assert "tick" in denied["message"].lower()
    assert env.customers.keys() == {"c1"}


async def test_tick_box_applies_without_restart(env):
    assert (await S.manager_create("customers", {"Name": "X"}))["ok"] is False
    await _allow("test-books", "customers", create=True, update=True, delete=True)
    created = await S.manager_create("customers", {"Name": "New Co", "Code": "N-1"})
    assert created["ok"] and created["created_key"] in env.customers


async def test_update_merges_onto_the_live_document(env):
    await _allow("test-books", "customers", update=True)
    await S.manager_update("customers", "c1", {"Code": "A-2"})
    assert env.customers["c1"] == {
        "Key": "c1", "Name": "Acme", "Code": "A-2", "EmailAddress": "a@acme.test"
    }


async def test_update_replace_sends_the_body_verbatim(env):
    await _allow("test-books", "customers", update=True)
    await S.manager_update("customers", "c1", {"Name": "Only"}, mode="replace")
    assert env.customers["c1"] == {"Name": "Only", "Key": "c1"}


async def test_delete_returns_a_copy_of_what_it_removed(env):
    await _allow("test-books", "customers", delete=True)
    out = await S.manager_delete("customers", "c1")
    assert out["deleted"] and out["deleted_record"]["Name"] == "Acme"
    assert "c1" not in env.customers


async def test_unknown_resource_suggests_the_catalog(env):
    with pytest.raises(ValueError, match="manager_catalog"):
        await S.manager_list("invoicez")


async def test_catalog_reports_what_is_allowed(env):
    await _allow("test-books", "customers", create=True)
    out = await S.manager_catalog(search="customers", limit=10)
    row = next(r for r in out["returned"] if r["resource"] == "customers")
    assert row["allowed"] == ["read", "create"]
    assert row["supports"] == ["read", "create", "update", "delete"]


async def test_raw_write_needs_its_own_box(env):
    out = await S.manager_api_request("POST", "/customer-form", {"Name": "Raw"})
    assert out["ok"] is False and "Raw write" in out["message"]
    assert env.customers.keys() == {"c1"}


async def test_raw_read_is_allowed_by_default(env):
    out = await S.manager_api_get("/customers")
    assert out["ok"] and out["body"]["totalRecords"] == 1


async def test_list_reports_unsupported_parameters(env):
    out = await S.manager_list("customers", from_date="2026-01-01")
    assert out["ignored_params"] == ["fromDate"]


async def test_permissions_tool_names_the_file_to_change(env):
    out = await S.manager_permissions()
    assert out["change_with"] == "open_permissions_panel"
    assert out["permissions_file"].endswith("test-books.json")


async def test_missing_business_explains_the_next_step(tmp_path, monkeypatch):
    monkeypatch.setenv("MANAGER_FULL_HOME", str(tmp_path / "empty"))
    monkeypatch.delenv("MANAGER_API_URL", raising=False)
    monkeypatch.delenv("MANAGER_API_KEY", raising=False)
    engine.clear_sessions()
    with pytest.raises(ValueError, match="open_permissions_panel"):
        await S.manager_list("customers")


async def test_permission_listings_stay_small(env):
    """These lists can cover 300 resources; the tool must not dump them all."""
    session = await engine.get_session()
    from manager_full_mcp.permissions import ASK, load_policy, save_policy

    policy = load_policy("test-books", session.catalog)
    policy.resources = {}  # fall through to the defaults below
    policy.defaults = {"read": "allow", "create": ASK, "update": ASK, "delete": ASK}
    save_policy(policy)
    import json

    out = await S.manager_permissions()
    assert out["ask_first_resources"] > 200
    assert len(json.dumps(out)) < 3000  # the whole answer stays small
    assert out["write_access_by_group"]["Sales"]["ask_first"] > 0
