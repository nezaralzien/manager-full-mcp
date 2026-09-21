"""The catalog must mirror the instance, not a curated subset."""

from manager_full_mcp.catalog import build_catalog


def test_covers_the_whole_instance(openapi_doc):
    catalog = build_catalog(openapi_doc)
    assert len(catalog.resources) > 300
    writable = [r for r in catalog.resources.values() if r.write_ops]
    assert len(writable) > 200


def test_pairs_irregular_list_and_form_names(openapi_doc):
    catalog = build_catalog(openapi_doc)
    bank = catalog.get("bank_and_cash_accounts")
    assert bank.list_path == "/bank-and-cash-accounts"
    assert bank.form_path == "/bank-or-cash-account-form"
    # Manager spells the investment form "inventment-form".
    assert catalog.get("investments").form_path == "/inventment-form"
    assert catalog.get("billable_time").form_path == "/billable-time-entry-form"


def test_resources_the_old_server_blocked_are_present(openapi_doc):
    catalog = build_catalog(openapi_doc)
    for name in (
        "tax_codes",
        "exchange_rates",
        "projects",
        "divisions",
        "fixed_assets",
        "inventory_transfers",
        "recurring_sales_invoices",
        "lock_date",
        "custom_buttons",
    ):
        assert catalog.get(name) is not None, name
        assert catalog.get(name).write_ops, name


def test_account_security_is_read_only(openapi_doc):
    catalog = build_catalog(openapi_doc)
    for name in ("access_tokens", "user_permissions", "customer_portal"):
        resource = catalog.get(name)
        assert resource.locked is True
        assert resource.ops["read"] is True
        assert resource.write_ops == []


def test_list_only_feeds_have_no_form(openapi_doc):
    catalog = build_catalog(openapi_doc)
    transactions = catalog.get("transactions")
    assert transactions.form_path is None
    assert transactions.ops == {
        "read": True,
        "create": False,
        "update": False,
        "delete": False,
    }


def test_every_resource_lands_in_a_known_group(openapi_doc):
    from manager_full_mcp.catalog import GROUP_LABELS

    catalog = build_catalog(openapi_doc)
    assert all(r.group in GROUP_LABELS for r in catalog.resources.values())
    assert not [r for r in catalog.resources.values() if r.group == "other"]
