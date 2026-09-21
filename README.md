# manager-full-mcp

Full-surface MCP server for [Manager.io](https://www.manager.io/), with a local
control panel where **you tick exactly what Claude may do** — per business, per
resource, per operation.

## Why

The stock `manager-mcp` server exposes 24 hand-curated document types out of the
~310 your Manager instance actually has, and hides the rest behind a hard-coded
denylist (tax codes, exchange rates, custom fields, projects, fixed assets, lock
date, recurring documents …). Permissions are nine coarse CSV "scopes" set in
environment variables.

This server:

- **Reads the API surface from your own instance.** Manager serves an OpenAPI
  document at the API base URL; every path in it becomes a resource. Nothing is
  curated away, and a Manager upgrade that adds document types shows up after
  `refresh_catalog`.
- **Gates every call on a tick box, with three states.** Read / create / update
  / delete, for each of the ~310 resources: **blocked**, **ask first**, or
  **allowed**. Edited in a local web panel and re-read on every tool call — no
  restart.
- **Marks the dangerous resources in red.** 111 of the 310 change the structure
  of the books rather than record a transaction. They are labelled ⚠ HIGH RISK
  everywhere, and switching one to "allowed without asking" needs a second
  confirmation.
- **Serves any number of businesses.** Each one has its own token, its own
  catalog and its own permission file.

The only permanent block is account security: `access_tokens`,
`user_permissions` and `customer_portal` are read-only, because writing there
changes who can reach your books.

## Install

```bash
git clone https://github.com/OWNER/manager-full-mcp.git
cd manager-full-mcp
uv venv --python 3.12 ~/.manager-full-mcp/venv
uv pip install --python ~/.manager-full-mcp/venv/bin/python .
```

For Claude Desktop, build the extension bundle and double-click it:

```bash
python3 build_mcpb.py   # writes manager-full-mcp.mcpb, pointing at the venv above
```

For any other MCP host, add this to its config:

```json
{
  "mcpServers": {
    "manager-full": {
      "command": "/Users/you/.manager-full-mcp/venv/bin/python",
      "args": ["-m", "manager_full_mcp.server"]
    }
  }
}
```

No API URL or token in the config: businesses are added in the control panel.

## First run

1. Ask Claude to **open the permissions panel** (tool `open_permissions_panel`),
   or run `~/.manager-full-mcp/venv/bin/manager-full-panel`.
2. **Businesses** tab → add a business: display name, API URL (usually ends with
   `/api2`), and an access token from Manager → Settings → Access Tokens. The
   panel tests the connection and loads the resource list. Repeat for as many
   businesses as you like.
3. **Permissions** tab → set what Claude may do. Presets: *Read only*,
   *Safe writes* (day-to-day documents, no deletes), *Ask first for everything*,
   *Everything* (high-risk resources land on **ask first**), *Clear all*.
   Press **Save**.

Claude picks up the new settings on its very next call.

## The three states

| State | Meaning |
| --- | --- |
| ✕ **Blocked** | Claude cannot do it. The tool answers with which box to tick. |
| ? **Ask first** | Claude stops before writing and a confirmation box appears on **your** screen with the business, the operation and a preview of the exact fields. Buttons: *Deny*, *Allow once*, *Allow 15 min*. No answer within two minutes counts as Deny, and if no dialog can be shown the operation is refused. |
| ✓ **Allowed** | Goes through without asking. |

"Ask first" is enforced in the server, not suggested to the model: the write
does not happen until the dialog comes back with a yes.

## High-risk resources

Shown in red, tagged ⚠ HIGH RISK, with an explanation on the group:

| Group | Why it is risky |
| --- | --- |
| Chart of accounts & account definitions | Decide how every past and future transaction is classified |
| Starting balances | Feed every period after them |
| Tax (tax codes, withholding) | Apply to documents that already exist, so filed totals can be restated |
| Currencies & exchange rates | Revalue every foreign-currency transaction |
| Custom fields, themes, email templates, **lock date** | Change behaviour business-wide; the lock date is what protects closed periods |
| Bank reconciliations | Audit evidence that an account was checked |
| Account security | Permanently read-only — access tokens, user permissions, customer portal |

`manager_catalog` reports `risk` and `risk_note` for each resource, and every
write to a high-risk resource comes back with a `caution` field so Claude tells
you exactly what changed.

## Tools

| Tool | What it does |
| --- | --- |
| `list_businesses` | Businesses this connection can reach |
| `open_permissions_panel` | Opens the tick-box panel, returns its URL |
| `manager_catalog` | Browse/search every resource and what is allowed |
| `manager_permissions` | What is currently allowed, and where the rules come from |
| `manager_list` | Search/page any collection, feed or report |
| `manager_get` | One record by Key, in Manager's own shape |
| `manager_create` | Create a record |
| `manager_update` | Update a record (merge by default, `replace` optional) |
| `manager_delete` | Delete a record (returns a copy of what was deleted) |
| `manager_api_get` | Raw GET on any path (needs *Raw read*) |
| `manager_api_request` | Raw POST/PUT/DELETE (needs *Raw write*) |
| `refresh_catalog` | Re-read the instance's API description |

Every tool takes an optional `business`; it can be omitted when only one
business is configured.

## Where things live

| Path | Contents |
| --- | --- |
| `~/.manager-full-mcp/businesses.json` | Businesses and access tokens (mode 0600) |
| `~/.manager-full-mcp/permissions/<id>.json` | The tick boxes for one business |
| `~/.manager-full-mcp/catalog/<id>.json` | Cached resource catalog |

Tokens never travel through the chat: they are typed into the local panel, which
binds to `127.0.0.1` only and requires a per-session token on every request.

## Environment variables (optional)

| Variable | Effect |
| --- | --- |
| `MANAGER_FULL_READ_ONLY` | `true` disables every write, whatever is ticked |
| `MANAGER_FULL_WRITE_<GROUP>` | Default create/update for a group before the panel is used. For high-risk groups a tick means **ask first**, never silent access |
| `MANAGER_FULL_DELETE_<GROUP>` | Same, for delete |
| `MANAGER_FULL_RAW_READ` / `MANAGER_FULL_RAW_WRITE` | Defaults for the raw escape hatches |
| `MANAGER_FULL_HOME` | Config directory (default `~/.manager-full-mcp`) |
| `MANAGER_API_URL` / `MANAGER_API_KEY` | Bootstrap a single business without the panel |

Group ids: `parties, sales, purchases, banking, inventory, payroll, assets,
ledger, projects, tax, currencies, recurring, starting_balances, accounts,
reports, customization, attachments`.

Once you save in the panel, the panel file wins and these defaults are ignored.

---

## بالعربي — باختصار

- الـ MCP هاد بيفتح **كل** موارد Manager (~310 مورد) مو بس 24.
- الصلاحيات بتتحكم فيها من **لوحة تحكم محلية**، ولكل مورد ولكل عملية (قراءة /
  إنشاء / تعديل / حذف) ثلاث حالات: **✕ ممنوع**، **؟ اسأل أولاً**، **✓ مسموح**.
- «اسأل أولاً» تنفيذ حقيقي: كلود بيوقف، وبتطلعلك نافذة تأكيد من النظام فيها
  الشركة والعملية وتفاصيل الحقول، وأزرار: رفض / سماح مرة / سماح ١٥ دقيقة.
  ما في جواب خلال دقيقتين = رفض.
- الموارد الخطرة (١١١ مورد: شجرة الحسابات، رموز الضريبة، أسعار الصرف، الأرصدة
  الافتتاحية، تاريخ الإقفال، الإعدادات) بتطلع **بلون أحمر** مع تحذير، وتحويلها
  لـ «مسموح بدون سؤال» بيطلب تأكيد إضافي.
- بتضيف أي عدد شركات من اللوحة نفسها: اسم + رابط الـ API + رمز الوصول.
- التغيير بصير فوري — ما في داعي تسكّر كلود وتفتحه.
- الشي الوحيد المقفول دايماً: رموز الوصول وصلاحيات المستخدمين وبوابة العملاء
  (قراءة فقط).

لفتح اللوحة: اطلب من كلود «افتح لوحة صلاحيات Manager» أو شغّل
`~/.manager-full-mcp/venv/bin/manager-full-panel`.

## Development

```bash
pip install -e ".[dev]"
pytest -q            # 42 tests, no network: a stub Manager instance is served locally
python3 tools/make_icon.py   # regenerates the extension icon
```

`tests/data/openapi.json` is a real Manager 26.9.1 API description with the
instance URL replaced by localhost. It contains no business data.

## Relationship to manager-mcp

Independent implementation, written from scratch, inspired by
[flumpiey/manager-mcp](https://github.com/flumpiey/manager-mcp) — a read-first
server with nine CSV write scopes over 24 curated document types. This project
takes the opposite approach: expose the instance's whole API surface and put a
three-state permission grid in front of it. No code is shared between the two.

## License

MIT
