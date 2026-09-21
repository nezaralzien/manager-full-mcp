#!/usr/bin/env python3
"""Build the Claude Desktop extension bundle (.mcpb).

The bundle carries the package source plus a manifest whose user_config is a
grid of tick boxes: read, and create/update + delete per resource group. Those
are the *defaults* used until the control panel is saved once; after that the
panel file is authoritative.
"""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from manager_full_mcp.catalog import HIGH_RISK_GROUPS, RISK_NOTES  # noqa: E402
BUILD = ROOT / "build" / "mcpb"
VENV_PYTHON = Path.home() / ".manager-full-mcp" / "venv" / "bin" / "python"

GROUPS: list[tuple[str, str]] = [
    ("parties", "Customers & Suppliers"),
    ("sales", "Sales (invoices, quotes, orders, credit & delivery notes)"),
    ("purchases", "Purchases (invoices, orders, debit notes, goods receipts)"),
    ("banking", "Banking & Cash (receipts, payments, transfers, accounts)"),
    ("inventory", "Inventory (items, kits, transfers, write-offs, production)"),
    ("payroll", "Payroll & Expense Claims"),
    ("assets", "Fixed Assets, Intangibles & Investments"),
    ("ledger", "General Ledger (journal entries, capital accounts)"),
    ("projects", "Projects, Divisions, Folders & Billable Time"),
    ("tax", "Tax (tax codes, withholding tax)"),
    ("currencies", "Currencies & Exchange Rates"),
    ("recurring", "Recurring Transactions"),
    ("starting_balances", "Starting Balances"),
    ("accounts", "Chart of Accounts & Account Definitions"),
    ("reports", "Report Definitions"),
    ("customization", "Custom Fields, Themes, Email Templates & Settings"),
    ("attachments", "Attachments, Emails & History"),
]


def user_config() -> dict[str, object]:
    config: dict[str, object] = {
        "read_everything": {
            "type": "boolean",
            "title": "Read everything",
            "description": (
                "Let Claude read every resource of every connected business. "
                "Reading never changes your books."
            ),
            "required": False,
            "default": True,
        },
        "read_only_mode": {
            "type": "boolean",
            "title": "Read-only mode (master switch)",
            "description": (
                "When on, every write is refused no matter what else is ticked "
                "here or in the control panel."
            ),
            "required": False,
            "default": False,
        },
    }
    for group, label in GROUPS:
        risky = group in HIGH_RISK_GROUPS
        config[f"write_{group}"] = {
            "type": "boolean",
            "title": ("⚠ HIGH RISK — " if risky else "") + f"Create & edit — {label}",
            "description": (
                f"Allow Claude to create and update {label.lower()}. "
                + (
                    "⚠ HIGH RISK — ticking this means ASK FIRST: a confirmation "
                    "box appears on your screen before every change. "
                    + RISK_NOTES.get(group, "")
                    if risky
                    else ""
                )
            ).strip(),
            "required": False,
            "default": False,
        }
    for group, label in GROUPS:
        risky = group in HIGH_RISK_GROUPS
        config[f"delete_{group}"] = {
            "type": "boolean",
            "title": ("⚠ HIGH RISK — " if risky else "") + f"Delete — {label}",
            "description": (
                f"Allow Claude to delete {label.lower()}. Manager has no undo. "
                + (
                    "⚠ HIGH RISK — ticking this means ASK FIRST: you confirm "
                    "every deletion on screen. " + RISK_NOTES.get(group, "")
                    if risky
                    else ""
                )
            ).strip(),
            "required": False,
            "default": False,
        }
    config["raw_read"] = {
        "type": "boolean",
        "title": "Raw read of any API path (advanced)",
        "description": "Lets Claude GET API paths the catalog does not model.",
        "required": False,
        "default": True,
    }
    config["raw_write"] = {
        "type": "boolean",
        "title": "Raw write to any API path (advanced)",
        "description": (
            "Lets Claude POST/PUT/DELETE any path, bypassing the per-resource "
            "boxes. Leave off unless you need it."
        ),
        "required": False,
        "default": False,
    }
    config["config_dir"] = {
        "type": "string",
        "title": "Config folder (optional)",
        "description": (
            "Where businesses, tokens and permission files live. "
            "Empty means ~/.manager-full-mcp."
        ),
        "required": False,
        "default": "",
    }
    return config


def env_map() -> dict[str, str]:
    env = {
        "MANAGER_FULL_READ_ALL": "${user_config.read_everything}",
        "MANAGER_FULL_READ_ONLY": "${user_config.read_only_mode}",
        "MANAGER_FULL_RAW_READ": "${user_config.raw_read}",
        "MANAGER_FULL_RAW_WRITE": "${user_config.raw_write}",
        "MANAGER_FULL_HOME": "${user_config.config_dir}",
        "PYTHONUNBUFFERED": "1",
    }
    for group, _ in GROUPS:
        env[f"MANAGER_FULL_WRITE_{group.upper()}"] = f"${{user_config.write_{group}}}"
        env[f"MANAGER_FULL_DELETE_{group.upper()}"] = f"${{user_config.delete_{group}}}"
    return env


def manifest() -> dict[str, object]:
    return {
        "manifest_version": "0.4",
        "name": "manager-full-mcp",
        "display_name": "Manager.io Full — all resources, your tick boxes",
        "version": "1.0.0",
        "description": (
            "Every Manager.io resource (~310, not 24), any number of businesses, "
            "and three states for each read/create/update/delete: blocked, ask "
            "first, or allowed. Boxes marked ⚠ HIGH RISK reshape the books "
            "themselves (chart of accounts, tax codes, exchange rates, opening "
            "balances, lock date, settings); ticking one of those here means ASK "
            "FIRST — Claude stops and a confirmation box appears on your screen "
            "before every such change. Full control is in the local panel."
        ),
        "long_description": (
            "Ask Claude to 'open the permissions panel' to add businesses "
            "(name, API URL, access token) and to tick exactly which resources "
            "it may read, create, update or delete. Tokens stay on this machine "
            "and never pass through the chat. Account security resources "
            "(access tokens, user permissions, customer portal) are read-only by "
            "design."
        ),
        "author": {"name": "Nezar"},
        "icon": "icon.png",
        "server": {
            "type": "python",
            "entry_point": "server/main.py",
            "mcp_config": {
                "command": str(VENV_PYTHON),
                # Run the source bundled inside the extension, so the venv only
                # has to supply fastmcp + httpx.
                "args": ["${__dirname}/server/main.py"],
                "env": env_map(),
            },
        },
        "tools": [
            {"name": "list_businesses", "description": "List connected Manager businesses"},
            {"name": "open_permissions_panel", "description": "Open the tick-box control panel"},
            {"name": "manager_catalog", "description": "Browse every resource and what is allowed"},
            {"name": "manager_permissions", "description": "Show current permissions"},
            {"name": "manager_list", "description": "Search or page any collection or report feed"},
            {"name": "manager_get", "description": "Fetch one record by key"},
            {"name": "manager_create", "description": "Create a record"},
            {"name": "manager_update", "description": "Update a record"},
            {"name": "manager_delete", "description": "Delete a record"},
            {"name": "manager_api_get", "description": "Raw GET on any API path"},
            {"name": "manager_api_request", "description": "Raw write on any API path"},
            {"name": "refresh_catalog", "description": "Re-read the instance API description"},
        ],
        "user_config": user_config(),
        "compatibility": {"platforms": ["darwin", "win32", "linux"]},
    }


ENTRY = '''"""Entry point for the Claude Desktop extension."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from manager_full_mcp.server import main

if __name__ == "__main__":
    main()
'''

INSTALL = '''#!/bin/sh
# Recreate the Python environment this extension runs from.
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
uv venv --python 3.12 "$HOME/.manager-full-mcp/venv"
uv pip install --python "$HOME/.manager-full-mcp/venv/bin/python" "$DIR/server"
echo "Done. Restart Claude Desktop."
'''


def build() -> Path:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    (BUILD / "server").mkdir(parents=True)
    shutil.copytree(ROOT / "src", BUILD / "server" / "src")
    shutil.copy(ROOT / "pyproject.toml", BUILD / "server" / "pyproject.toml")
    shutil.copy(ROOT / "README.md", BUILD / "server" / "README.md")
    (BUILD / "server" / "main.py").write_text(ENTRY, encoding="utf-8")
    (BUILD / "install.sh").write_text(INSTALL, encoding="utf-8")
    (BUILD / "install.sh").chmod(0o755)
    (BUILD / "manifest.json").write_text(
        json.dumps(manifest(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    icon = ROOT / "mcpb" / "icon.png"
    if icon.is_file():
        shutil.copy(icon, BUILD / "icon.png")

    out = ROOT / "manager-full-mcp.mcpb"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(BUILD.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                bundle.write(path, path.relative_to(BUILD))
    return out


if __name__ == "__main__":
    bundle = build()
    size = bundle.stat().st_size / 1024
    print(f"built {bundle} ({size:.0f} KB)")
