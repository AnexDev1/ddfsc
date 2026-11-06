from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError


class HrPayslipInput(models.Model):
    _inherit = "hr.payslip.input"

    component_ids = fields.Many2many(
        "ddfsc.employee.payroll.component", "ddfsc_component_payslip_input_rel",
        "input_id", "component_id", string="Source Components", readonly=True,
    )
    overtime_ids = fields.Many2many(
        "ddfsc.overtime.request", "ddfsc_overtime_payslip_input_rel", "input_id", "overtime_id",
        string="Approved Overtime", readonly=True,
    )


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    ddfsc_basic_pay = fields.Monetary(string="Basic Pay", compute="_compute_ddfsc_payroll_breakdown", currency_field="ddfsc_payroll_currency_id")
    ddfsc_taxable_earnings = fields.Monetary(string="Taxable Earnings", compute="_compute_ddfsc_payroll_breakdown", currency_field="ddfsc_payroll_currency_id")
    ddfsc_non_taxable_earnings = fields.Monetary(string="Non-taxable Earnings", compute="_compute_ddfsc_payroll_breakdown", currency_field="ddfsc_payroll_currency_id")
    ddfsc_total_deductions = fields.Monetary(string="Total Deductions", compute="_compute_ddfsc_payroll_breakdown", currency_field="ddfsc_payroll_currency_id")
    ddfsc_income_tax = fields.Monetary(string="Income Tax", compute="_compute_ddfsc_payroll_breakdown", currency_field="ddfsc_payroll_currency_id")
    ddfsc_employee_pension = fields.Monetary(string="Employee Pension", compute="_compute_ddfsc_payroll_breakdown", currency_field="ddfsc_payroll_currency_id")
    ddfsc_net_pay = fields.Monetary(string="Net Pay", compute="_compute_ddfsc_payroll_breakdown", currency_field="ddfsc_payroll_currency_id")
    ddfsc_employer_pension = fields.Monetary(string="Employer Pension", compute="_compute_ddfsc_payroll_breakdown", currency_field="ddfsc_payroll_currency_id")
    ddfsc_payroll_currency_id = fields.Many2one(
        related="company_id.currency_id", readonly=True, string="Payroll Currency"
    )

    @api.depends("line_ids.code", "line_ids.total", "line_ids.category_id")
    def _compute_ddfsc_payroll_breakdown(self):
        """Present the computed salary rules as a concise gross-to-net summary.

        The values are derived from payslip lines, never manually entered, so the
        summary always remains consistent with the detailed computation lines.
        """
        for payslip in self:
            totals = {line.code: line.total for line in payslip.line_ids}
            deductions = sum(
                line.total for line in payslip.line_ids if line.category_id.code == "DED"
            )
            payslip.ddfsc_basic_pay = totals.get("BASIC", 0.0)
            payslip.ddfsc_taxable_earnings = totals.get("GROSS", 0.0)
            payslip.ddfsc_non_taxable_earnings = totals.get("NONTAX_ALLOW", 0.0)
            payslip.ddfsc_total_deductions = abs(deductions)
            payslip.ddfsc_income_tax = abs(totals.get("ET_PAYE", 0.0))
            payslip.ddfsc_employee_pension = abs(totals.get("ET_PENSION_EE", 0.0))
            payslip.ddfsc_net_pay = totals.get("NET", 0.0)
            payslip.ddfsc_employer_pension = totals.get("ET_PENSION_ER", 0.0)

    def get_ethiopian_monthly_tax(self, taxable_income):
        """Salary-rule helper for PAY-003.

        Example rule expression: result = payslip.get_ethiopian_monthly_tax(categories.TAXABLE)
        """
        self.ensure_one()
        return self.env["ddfsc.ethiopian.tax.band"].calculate_monthly_tax(
            taxable_income, self.date_to or self.date_from, self.company_id
        )

    def get_effective_basic_salary(self, contract):
        """Return the approved salary in force at the end of this payroll period.

        A later contract wage must never rewrite an already historical payroll
        period.  The compensation-history record is authoritative where one
        exists; the contract wage remains the safe fallback for employees with
        no approved revision history.
        """
        self.ensure_one()
        effective_date = self.date_to or self.date_from or fields.Date.context_today(self)
        history = self.env["ddfsc.compensation.history"].search([
            ("employee_id", "=", contract.employee_id.id),
            ("company_id", "=", self.company_id.id),
            ("date_from", "<=", effective_date),
            "|", ("date_to", "=", False), ("date_to", ">=", effective_date),
        ], order="date_from desc, id desc", limit=1)
        return history.basic_salary if history else contract.wage

    def get_ethiopian_pension(self, pension_salary):
        """Salary-rule helper for PAY-004; returns employee/employer amounts."""
        self.ensure_one()
        return self.env["ddfsc.ethiopian.pension.config"].calculate_contributions(
            pension_salary, self.date_to or self.date_from, self.company_id
        )

    def get_approved_overtime_payment(self, approved_hours, monthly_wage):
        self.ensure_one()
        return self.env["ddfsc.overtime.pay.rate"].calculate_payment(
            approved_hours, monthly_wage, self.date_to or self.date_from, self.company_id
        )

    def action_payslip_done(self):
        result = super().action_payslip_done()
        Repayment = self.env["ddfsc.loan.repayment"]
        for payslip in self:
            repayments = payslip.input_line_ids.component_ids.mapped("loan_repayment_id").filtered(
                lambda repayment: repayment.state == "scheduled"
            )
            if repayments:
                repayments.write({
                    "state": "paid", "paid_payslip_id": payslip.id,
                    "paid_date": payslip.date_to or fields.Date.context_today(payslip),
                })
                closed_loans = repayments.mapped("loan_id").filtered(
                    lambda loan: loan.state == "disbursed" and not loan.repayment_ids.filtered(
                        lambda line: line.state != "paid"
                    )
                )
                if closed_loans:
                    closed_loans.action_close_settled()
        return result

    @api.model
    def get_inputs(self, contracts, date_from, date_to):
        result = super().get_inputs(contracts, date_from, date_to)
        if not contracts or not self.employee_id or not self.employee_id.payroll_eligible:
            return result
        components = self.env["ddfsc.employee.payroll.component"].search([
            ("employee_id", "=", self.employee_id.id), ("company_id", "=", self.company_id.id),
            ("state", "=", "approved"), ("date_from", "<=", date_to),
            "|", ("date_to", "=", False), ("date_to", ">=", date_from),
        ])
        one_off = components.filtered(lambda component: component.recurrence == "one_off")
        if one_off:
            used_ids = set(self.env["hr.payslip.input"].search([
                ("component_ids", "in", one_off.ids), ("payslip_id.state", "=", "done"),
                ("payslip_id.id", "!=", self.id or 0),
            ]).mapped("component_ids").ids)
            components = components.filtered(lambda component: component.id not in used_ids)

        grouped = defaultdict(lambda: {"amount": 0.0, "ids": [], "type": False})
        for component in components:
            grouped[component.code]["amount"] += component.amount
            grouped[component.code]["ids"].append(component.id)
            grouped[component.code]["type"] = component.component_type_id
        contract = contracts[:1]
        for code, values in grouped.items():
            vals = {
                "name": values["type"].name, "code": code, "amount": values["amount"],
                "contract_id": contract.id, "component_ids": [(6, 0, values["ids"])],
            }
            existing = next((line for line in result if line.get("code") == code), None)
            if existing:
                existing.update(vals)
            else:
                result.append(vals)
        approved_overtime = self.env["ddfsc.overtime.request"].search([
            ("employee_id", "=", self.employee_id.id), ("company_id", "=", self.company_id.id),
            ("state", "=", "approved"), ("work_date", ">=", date_from), ("work_date", "<=", date_to),
        ])
        used_overtime = self.env["hr.payslip.input"].search([
            ("overtime_ids", "in", approved_overtime.ids), ("payslip_id.state", "=", "done"),
            ("payslip_id.id", "!=", self.id or 0),
        ]).mapped("overtime_ids")
        approved_overtime -= used_overtime
        if approved_overtime:
            contract = contracts[:1]
            if not contract:
                return result
            amount = self.get_approved_overtime_payment(
                sum(approved_overtime.mapped("approved_hours")), contract.wage
            )
            overtime_values = {
                "name": self.env._("Approved Overtime"), "code": "OT_PAY", "amount": amount,
                "contract_id": contract.id, "overtime_ids": [(6, 0, approved_overtime.ids)],
            }
            existing = next((line for line in result if line.get("code") == "OT_PAY"), None)
            if existing:
                existing.update(overtime_values)
            else:
                result.append(overtime_values)
        return result

    def write(self, vals):
        if any(payslip.payslip_run_id.state == "close" for payslip in self):
            raise UserError(self.env._("Payslips in a closed payroll batch are locked. Reopen the batch with a documented reason before changing them."))
        return super().write(vals)

    def unlink(self):
        if any(payslip.payslip_run_id.state == "close" for payslip in self):
            raise UserError(self.env._("Payslips in a closed payroll batch are locked and cannot be deleted."))
        return super().unlink()

