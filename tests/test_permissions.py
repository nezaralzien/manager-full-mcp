"""Nothing is writable until a box is ticked."""

import json

from manager_full_mcp.catalog import build_catalog
from manager_full_mcp.permissions import (
    SOURCE_DEFAULTS,
    SOURCE_PANEL,
    load_policy,
    policy_from_env,
    save_policy,
)


def test_default_is_read_only(openapi_doc, env, monkeypatch):
    catalog = build_catalog(openapi_doc)
    policy = policy_from_env("b", catalog)
    summary = policy.summary(catalog)
    assert summary["allowed"]["read"] > 300
    assert summary["allowed"]["create"] == 0
    assert summary["allowed"]["delete"] == 0


def test_group_env_grants_create_but_not_delete(openapi_doc, env, monkeypatch):
    monkeypatch.setenv("MANAGER_FULL_WRITE_PARTIES", "true")
    catalog = build_catalog(openapi_doc)
    policy = policy_from_env("b", catalog)
    customers = catalog.get("customers")
    assert policy.allows(customers, "create")
    assert policy.allows(customers, "update")
    assert not policy.allows(customers, "delete")
    assert not policy.allows(catalog.get("payments"), "create")


def test_panel_file_overrides_env(openapi_doc, env, monkeypatch):
    monkeypatch.setenv("MANAGER_FULL_WRITE_PARTIES", "true")
    catalog = build_catalog(openapi_doc)
    policy = policy_from_env("b", catalog)
    policy.resources["customers"] = dict.fromkeys(
        ("read", "create", "update", "delete"), False
    ) | {"read": True}
    save_policy(policy)
    reloaded = load_policy("b", catalog)
    assert reloaded.source == SOURCE_PANEL
    assert not reloaded.allows(catalog.get("customers"), "create")


def test_read_only_master_switch(openapi_doc, env, monkeypatch):
    monkeypatch.setenv("MANAGER_FULL_WRITE_SALES", "true")
    monkeypatch.setenv("MANAGER_FULL_READ_ONLY", "true")
    catalog = build_catalog(openapi_doc)
    policy = policy_from_env("b", catalog)
    assert policy.summary(catalog)["allowed"]["create"] == 0
    assert "read-only mode" in policy.denial_reason(catalog.get("sales_invoices"), "create")


def test_permission_file_is_owner_only(openapi_doc, env):
    from manager_full_mcp.config import permissions_file

    catalog = build_catalog(openapi_doc)
    save_policy(policy_from_env("b", catalog))
    path = permissions_file("b")
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text())["version"] == 1


def test_locked_resources_cannot_be_ticked_open(openapi_doc, env):
    catalog = build_catalog(openapi_doc)
    policy = policy_from_env("b", catalog)
    policy.resources["access_tokens"] = dict.fromkeys(
        ("read", "create", "update", "delete"), True
    )
    save_policy(policy)
    reloaded = load_policy("b", catalog)
    assert not reloaded.allows(catalog.get("access_tokens"), "create")
    assert reloaded.allows(catalog.get("access_tokens"), "read")


def test_source_is_reported(openapi_doc, env):
    catalog = build_catalog(openapi_doc)
    assert load_policy("fresh", catalog).source == SOURCE_DEFAULTS
