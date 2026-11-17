import json
import logging
from pathlib import Path

from odoo import Command


_logger = logging.getLogger(__name__)


LEGACY_TO_VERA = {
    "101000": "1330",
    "101300": "1100",
    "101401": "1073",
    "101402": "1095",
    "101403": "1091",
    "101404": "1092",
    "101701": "1093",
    "110100": "1260",
    "110400": "1250",
    "110500": "1250",
    "121000": "1100",
    "121100": "1270",
    "122000": "1170",
    "128000": "1300",
    "131000": "1180",
    "132000": "1180",
    "141000": "1300",
    "151000": "1715",
    "191000": "1990",
    "201000": "2045",
    "201100": "2045",
    "211000": "2000",
    "211100": "2045",
    "212000": "2060",
    "230000": "2030",
    "230100": "2120",
    "230200": "2130",
    "251000": "2100",
    "252000": "2100",
    "291000": "2300",
    "301000": "3000",
    "302000": "3110",
    "400000": "4010",
    "441000": "4900",
    "442000": "4900",
    "443000": "6900",
    "450000": "4900",
    "500000": "5100",
    "600000": "6900",
    "610000": "5095",
    "611000": "1730",
    "612000": "6900",
    "620000": "6160",
    "630000": "6010",
    "641000": "6430",
    "642000": "6900",
    "643000": "4900",
    "961000": "6900",
    "962000": "8900",
    "999998": "3200",
    "999999": "3210",
}


HISTORY_MODELS = {"account.move.line", "account.analytic.line"}


def _load_design():
    path = Path(__file__).parent / "data" / "coa.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _find_account(env, company, code):
    return env["account.account"].with_company(company).with_context(active_test=False).search(
        [("code", "=", code), ("company_ids", "in", company.id)], limit=1
    )


def _upsert_accounts(env, company, design):
    result = {}
    for item in design["accounts"]:
        code = item["code"]
        account = _find_account(env, company, code)
        values = {
            "name": item["name"],
            "account_type": item["account_type"],
            "reconcile": item.get("reconcile", item["account_type"] in ("asset_receivable", "liability_payable")),
            "active": True,
            "note": "Vera COA. Normal balance: %s. Required dimension(s): %s. Replaces: %s"
            % (
                item["normal_balance"] or "Not specified",
                item["required_dimensions"] or "None",
                item["replaces"] or "None",
            ),
        }
        if account:
            account.write(values)
        else:
            values.update({"code": code, "company_ids": [Command.set(company.ids)]})
            account = env["account.account"].with_company(company).create(values)
        result[code] = account
    return result


def _upsert_dimensions(env, company, design):
    plan_model = env["account.analytic.plan"].sudo().with_company(company)
    analytic_model = env["account.analytic.account"].sudo().with_company(company)
    for sequence, (plan_name, values) in enumerate(design["dimensions"].items(), start=1):
        plan = plan_model.search([("name", "=", plan_name), ("parent_id", "=", False)], limit=1)
        if plan:
            plan.write({"sequence": sequence * 10, "default_applicability": "optional"})
        else:
            plan = plan_model.create({
                "name": plan_name,
                "sequence": sequence * 10,
                "default_applicability": "optional",
            })
        for code, name in values:
            analytic_company_id = False if plan_name == "Product Line" else company.id
            analytic = analytic_model.with_context(active_test=False).search([
                ("code", "=", code),
                ("plan_id", "=", plan.id),
                ("company_id", "=", analytic_company_id),
            ], limit=1)
            vals = {"name": name, "active": True}
            if analytic:
                analytic.write(vals)
            else:
                vals.update({"code": code, "plan_id": plan.id, "company_id": analytic_company_id})
                analytic_model.create(vals)


def _remap_many2one_references(env, company, old_account, new_account):
    fields = env["ir.model.fields"].sudo().search([
        ("relation", "=", "account.account"),
        ("ttype", "=", "many2one"),
        ("store", "=", True),
    ])
    for field in fields:
        if field.model in HISTORY_MODELS or field.model not in env:
            continue
        model = env[field.model].sudo().with_company(company).with_context(active_test=False)
        if not model._auto:
            continue
        try:
            records = model.search([(field.name, "=", old_account.id)])
        except Exception:
            _logger.debug("Cannot search %s.%s during COA remap", field.model, field.name, exc_info=True)
            continue
        for record in records:
            try:
                with env.cr.savepoint():
                    record.write({field.name: new_account.id})
            except Exception:
                _logger.warning(
                    "Could not remap %s.%s record %s from %s to %s",
                    field.model, field.name, record.id, old_account.code, new_account.code,
                    exc_info=True,
                )


def _remap_many2many_references(env, company, old_account, new_account):
    fields = env["ir.model.fields"].sudo().search([
        ("relation", "=", "account.account"),
        ("ttype", "=", "many2many"),
        ("store", "=", True),
    ])
    for field in fields:
        if field.model in HISTORY_MODELS or field.model not in env:
            continue
        model = env[field.model].sudo().with_company(company).with_context(active_test=False)
        if not model._auto:
            continue
        try:
            records = model.search([(field.name, "in", old_account.id)])
        except Exception:
            continue
        for record in records:
            try:
                with env.cr.savepoint():
                    values = record[field.name] - old_account | new_account
                    record.write({field.name: [Command.set(values.ids)]})
            except Exception:
                _logger.warning(
                    "Could not remap %s.%s record %s from %s to %s",
                    field.model, field.name, record.id, old_account.code, new_account.code,
                    exc_info=True,
                )


def _remap_company_defaults(env, company, old_account, new_account):
    """Company-dependent account fields (partner payable/receivable, product
    category accounts...) fall back to an ir.default value per company. Those
    are not found by a normal search, so remap them explicitly."""
    defaults = env["ir.default"].sudo().search([
        ("company_id", "in", [company.id, False]),
        ("field_id.relation", "=", "account.account"),
        ("field_id.ttype", "=", "many2one"),
    ])
    for default in defaults:
        if default.json_value == str(old_account.id):
            default.json_value = str(new_account.id)


def _remap_legacy_accounts(env, company, accounts):
    move_line_model = env["account.move.line"].sudo().with_company(company)
    for old_code, new_code in LEGACY_TO_VERA.items():
        old_account = _find_account(env, company, old_code)
        new_account = accounts.get(new_code)
        if not old_account or not new_account or old_account == new_account:
            continue
        _remap_many2one_references(env, company, old_account, new_account)
        _remap_many2many_references(env, company, old_account, new_account)
        _remap_company_defaults(env, company, old_account, new_account)
        move_count = move_line_model.search_count([("account_id", "=", old_account.id)])
        superseded = "Legacy account superseded by Vera account %s." % new_code
        note = old_account.note or ""
        if superseded not in note:
            note = (note + "\n" + superseded).strip()
        old_account.write({"note": note, "active": bool(move_count)})


# Accounts Odoo needs for payments and transfers. They must allow reconciliation.
OUTSTANDING_RECEIPTS = "1091"
OUTSTANDING_PAYMENTS = "1092"
LIQUIDITY_TRANSFER = "1093"
# Accounts that earlier versions of this module used for those roles; they are
# replaced automatically. Any other account chosen by a user is left alone.
_REPLACEABLE_CODES = {"1090", "101403", "101404", "101701"}


# One bank journal per Vera bank account: (account code, journal code).
BANK_JOURNALS = [
    ("1070", "CBDC"),  # CBE Dechatu Branch
    ("1071", "CBAD"),  # CBE Adama Branch
    ("1072", "CBJG"),  # CBE Jijiga Branch
    ("1073", "BNKO"),  # Other bank accounts
]


def _ensure_bank_journals(env, company, accounts):
    Journal = env["account.journal"].sudo().with_context(active_test=False)
    for account_code, journal_code in BANK_JOURNALS:
        account = accounts.get(account_code)
        if not account:
            continue
        if Journal.search_count([("company_id", "=", company.id), ("default_account_id", "=", account.id)]):
            continue
        code = journal_code
        if Journal.search_count([("company_id", "=", company.id), ("code", "=", code)]):
            continue
        Journal.with_company(company).create({
            "name": account.name.replace("Cash at Bank - ", "Bank - "),
            "type": "bank",
            "code": code,
            "company_id": company.id,
            "default_account_id": account.id,
        })


def _setup_payment_accounts(env, company, accounts):
    receipts = accounts.get(OUTSTANDING_RECEIPTS)
    payments = accounts.get(OUTSTANDING_PAYMENTS)
    transfer = accounts.get(LIQUIDITY_TRANSFER)
    if not (receipts and payments and transfer):
        return
    journals = env["account.journal"].sudo().with_context(active_test=False).search([
        ("company_id", "=", company.id),
        ("type", "in", ("bank", "cash", "credit")),
    ])
    for line in journals.inbound_payment_method_line_ids:
        if not line.payment_account_id or line.payment_account_id.code in _REPLACEABLE_CODES:
            line.payment_account_id = receipts
    for line in journals.outbound_payment_method_line_ids:
        if not line.payment_account_id or line.payment_account_id.code in _REPLACEABLE_CODES:
            line.payment_account_id = payments
    company = company.sudo()
    if not company.transfer_account_id or company.transfer_account_id.code in _REPLACEABLE_CODES:
        company.transfer_account_id = transfer


def _find_vera_accounts(env, company, design):
    accounts = {}
    for item in design["accounts"]:
        account = _find_account(env, company, item["code"])
        if account:
            accounts[item["code"]] = account
    return accounts


def _ensure_accounts(env, company, design, codes):
    """Create the given Vera accounts when missing and enforce their type and
    reconciliation flag, without rewriting any other account."""
    items = [item for item in design["accounts"] if item["code"] in codes]
    _upsert_accounts(env, company, {"accounts": items})


def sync_payment_accounts(env):
    """Upgrade step: add the outstanding/transfer accounts, one bank journal per
    bank account, and wire the payment methods to the outstanding accounts."""
    design = _load_design()
    for company in env["res.company"].sudo().search([]):
        scoped_env = env(context=dict(env.context, allowed_company_ids=company.ids))
        if not _find_account(scoped_env, company, "1100"):
            # Vera chart was never installed for this company.
            continue
        _ensure_accounts(scoped_env, company, design, {OUTSTANDING_RECEIPTS, OUTSTANDING_PAYMENTS, LIQUIDITY_TRANSFER})
        accounts = _find_vera_accounts(scoped_env, company, design)
        _remap_legacy_accounts(scoped_env, company, accounts)
        _ensure_bank_journals(scoped_env, company, accounts)
        _setup_payment_accounts(scoped_env, company, accounts)


def post_init_hook(env):
    design = _load_design()
    companies = env["res.company"].sudo().search([])
    for company in companies:
        scoped_env = env(context=dict(env.context, allowed_company_ids=company.ids))
        accounts = _upsert_accounts(scoped_env, company, design)
        _upsert_dimensions(scoped_env, company, design)
        _remap_legacy_accounts(scoped_env, company, accounts)
        _ensure_bank_journals(scoped_env, company, accounts)
        _setup_payment_accounts(scoped_env, company, accounts)
    _logger.info(
        "Vera COA migration complete: %s accounts, %s analytic plans",
        len(design["accounts"]), len(design["dimensions"]),
    )
