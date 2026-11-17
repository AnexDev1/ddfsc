# -*- coding: utf-8 -*-
from odoo import api, fields, models


def _parse_distribution(existing):
    """{'1,2': 60, '3': 40} -> [((1, 2), 60.0), ((3,), 40.0)]"""
    rows = []
    for key, pct in (existing or {}).items():
        ids = tuple(int(x) for x in str(key).split(',') if x.strip().isdigit())
        if ids:
            rows.append((ids, float(pct or 0.0)))
    return rows


def _combine_rows(rows, env):
    """Combine rows that each cover different plans into one row per
    combination, e.g. {'18': 100, '31': 100, '19': 100} -> {'18,31,19': 100}.

    Rows are grouped by the set of plans they cover. When the groups cover
    disjoint plans and each group totals 100%, the result is their cartesian
    product (percentages multiplied). Otherwise rows are kept unchanged.
    """
    if not rows or not env:
        return rows
    all_ids = {acc for ids, _pct in rows for acc in ids}
    accounts = env['account.analytic.account'].browse(list(all_ids)).exists()
    root_plan = {acc.id: (acc.root_plan_id or acc.plan_id).id for acc in accounts}

    groups = {}
    for ids, pct in rows:
        plans = frozenset(root_plan.get(acc) for acc in ids)
        groups.setdefault(plans, []).append((ids, pct))
    if len(groups) < 2:
        return rows

    plan_sets = list(groups)
    seen = set()
    for plans in plan_sets:
        if seen & plans:
            return rows  # overlapping plans: ambiguous, leave untouched
        seen |= plans
    if any(abs(sum(p for _ids, p in grp) - 100.0) > 0.01 for grp in groups.values()):
        return rows  # partial distributions: cannot safely combine

    combined = [((), 100.0)]
    for grp in groups.values():
        combined = [
            (ids_a + ids_b, pct_a * pct_b / 100.0)
            for ids_a, pct_a in combined
            for ids_b, pct_b in grp
        ]
    return combined


def merge_analytic_distribution(existing, account_to_set=None, plan=None, remove_plan=False, env=None):
    """
    Safely merges or replaces an analytic account in a distribution dictionary:
    - If account_to_set is provided: replaces any existing account from account_to_set's plan with account_to_set at 100.0%.
    - If remove_plan is True and plan is provided: removes any account from that plan.
    - Preserves accounts from all other plans.
    - Accounts from different plans are combined on a single distribution row
      (e.g. {'18,31,19': 100.0}) instead of one row per account.
    """
    if not env and account_to_set:
        env = account_to_set.env
    elif not env and plan:
        env = plan.env

    rows = _parse_distribution(existing if isinstance(existing, dict) else {})

    target_plan = plan or (account_to_set.plan_id if account_to_set else False)
    if target_plan and env:
        target_root = target_plan.root_id if 'root_id' in target_plan._fields else target_plan
        plan_acc_ids = set(env['account.analytic.account'].search(
            [('root_plan_id', '=', target_root.id)]).ids)
        stripped = []
        for ids, pct in rows:
            kept = tuple(acc for acc in ids if acc not in plan_acc_ids)
            if kept:
                stripped.append((kept, pct))
        rows = stripped

    if account_to_set and not remove_plan:
        rows.append(((account_to_set.id,), 100.0))

    rows = _combine_rows(rows, env)

    res = {}
    for ids, pct in rows:
        key = ','.join(str(acc) for acc in dict.fromkeys(ids))
        res[key] = res.get(key, 0.0) + pct
    return res or False


class ResCompany(models.Model):
    _inherit = 'res.company'

    branch_analytic_plan_id = fields.Many2one(
        'account.analytic.plan',
        string='Branch / Location Analytic Plan',
        help="Analytic plan representing Branches / Locations (e.g. Branch / Location).",
    )
    product_analytic_plan_id = fields.Many2one(
        'account.analytic.plan',
        string='Product Analytic Plan',
        help="Analytic plan representing Products / Product Lines (e.g. Product Line).",
    )
    cost_center_analytic_plan_id = fields.Many2one(
        'account.analytic.plan',
        string='Cost Center Analytic Plan',
        help="Analytic plan representing Cost Centers / Departments (e.g. Department / Cost Center).",
    )

    def get_branch_analytic_plan(self):
        self.ensure_one()
        if self.branch_analytic_plan_id:
            return self.branch_analytic_plan_id
        plan = self.env['account.analytic.plan'].search([
            '|', ('name', 'ilike', 'Branch'), ('name', 'ilike', 'Location')
        ], limit=1)
        if plan:
            self.sudo().branch_analytic_plan_id = plan
        return plan

    def get_product_analytic_plan(self):
        self.ensure_one()
        if self.product_analytic_plan_id:
            return self.product_analytic_plan_id
        plan = self.env['account.analytic.plan'].search([
            '|', ('name', 'ilike', 'Product Line'), ('name', 'ilike', 'Product')
        ], limit=1)
        if plan:
            self.sudo().product_analytic_plan_id = plan
        return plan

    def get_cost_center_analytic_plan(self):
        self.ensure_one()
        if self.cost_center_analytic_plan_id:
            return self.cost_center_analytic_plan_id
        plan = self.env['account.analytic.plan'].search([
            '|', ('name', 'ilike', 'Cost Center'), ('name', 'ilike', 'Department')
        ], limit=1)
        if plan:
            self.sudo().cost_center_analytic_plan_id = plan
        return plan
