from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DdfscLoanType(models.Model):
    _name = "ddfsc.loan.type"
    _description = "Employee Loan Type"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    maximum_months_basic = fields.Float(default=3.0, required=True)
    maximum_net_deduction_percent = fields.Float(default=30.0, required=True)
    maximum_term_months = fields.Integer(default=12, required=True)
    interest_rate = fields.Float(default=0.0, required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    _code_company_unique = models.Constraint("unique(code, company_id)", "Loan type code must be unique per company.")

    @api.constrains("maximum_months_basic", "maximum_net_deduction_percent", "maximum_term_months", "interest_rate")
    def _check_limits(self):
        for record in self:
            if record.maximum_months_basic <= 0 or record.maximum_term_months <= 0 or not 0 < record.maximum_net_deduction_percent <= 100 or record.interest_rate < 0:
                raise ValidationError(_("Loan limits must be positive and the deduction cap must be between 0 and 100%."))


class DdfscEmployeeLoan(models.Model):
    _name = "ddfsc.employee.loan"
    _description = "Employee Loan Application"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(readonly=True, default=lambda self: _("New"))
    employee_id = fields.Many2one("hr.employee", required=True, ondelete="restrict")
    loan_type_id = fields.Many2one("ddfsc.loan.type", required=True, ondelete="restrict")
    amount = fields.Monetary(required=True)
    term_months = fields.Integer(required=True)
    purpose = fields.Text(required=True)
    requested_date = fields.Date(default=fields.Date.context_today, required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    state = fields.Selection([("draft","Draft"),("submitted","Pending Manager"),("manager","Pending HR"),("hr","Pending Finance"),("approved","Approved — Awaiting Disbursement"),("disbursed","Disbursed"),("closed","Closed"),("rejected","Rejected"),("cancelled","Cancelled")], default="draft", required=True, tracking=True)
    disbursement_date = fields.Date()
    disbursement_reference = fields.Char()
    installment_amount = fields.Monetary(readonly=True)
    outstanding_balance = fields.Monetary(compute="_compute_balance", store=True)
    repayment_ids = fields.One2many("ddfsc.loan.repayment", "loan_id")
    settlement_date = fields.Date()
    settlement_reference = fields.Char()
    settlement_amount = fields.Monetary()

    @api.constrains("amount", "term_months", "employee_id", "loan_type_id")
    def _check_eligibility(self):
        for loan in self:
            if loan.amount <= 0 or loan.term_months <= 0:
                raise ValidationError(_("Loan amount and repayment term must be greater than zero."))
            if loan.term_months > loan.loan_type_id.maximum_term_months:
                raise ValidationError(_("Repayment term exceeds the loan-type limit."))
            wage = loan.employee_id.version_id.wage
            if loan.amount > wage * loan.loan_type_id.maximum_months_basic:
                raise ValidationError(_("Requested amount exceeds the employee's loan limit based on basic salary."))
            installment = loan.amount / loan.term_months
            cap = wage * loan.loan_type_id.maximum_net_deduction_percent / 100
            if installment > cap:
                raise ValidationError(_(
                    "The monthly installment exceeds the %(percent)s%% payroll-deduction cap (%(cap).2f). "
                    "Increase the repayment term or reduce the requested amount.",
                    percent=loan.loan_type_id.maximum_net_deduction_percent, cap=cap,
                ))

    @api.depends("amount", "repayment_ids.state", "repayment_ids.total_due")
    def _compute_balance(self):
        for loan in self:
            loan.outstanding_balance = sum(loan.repayment_ids.filtered(lambda line: line.state != "paid").mapped("total_due")) if loan.repayment_ids else loan.amount

    def action_submit(self):
        self.write({"state": "submitted"})

    def action_manager_approve(self):
        if self.filtered(lambda loan: loan.state != "submitted"):
            raise UserError(_("Only submitted loans can be manager-approved."))
        self.write({"state": "manager"})

    def action_hr_approve(self):
        if self.filtered(lambda loan: loan.state != "manager"):
            raise UserError(_("Only manager-approved loans can be HR-approved."))
        self.write({"state": "hr"})

    def action_finance_approve(self):
        self._require_payroll_manager()
        if self.filtered(lambda loan: loan.state != "hr"):
            raise UserError(_("Only HR-approved loans can be Finance-approved."))
        for loan in self:
            active = self.search_count([
                ("employee_id", "=", loan.employee_id.id), ("id", "!=", loan.id),
                ("state", "in", ("approved", "disbursed")),
            ])
            if active:
                raise UserError(_("This employee already has an approved or disbursed loan. Close it before approving another loan."))
            if loan.loan_type_id.interest_rate:
                raise UserError(_(
                    "Interest-bearing loans require a Finance-approved interest method. "
                    "Set the loan type interest rate to zero until that policy is configured."
                ))
            loan.write({"state": "approved"})

    def _require_payroll_manager(self):
        if not (self.env.is_superuser() or self.env.user.has_group("payroll.group_payroll_manager")):
            raise UserError(_("Only a Payroll Manager or Finance approver can perform this action."))

    def action_disburse(self):
        self._require_payroll_manager()
        for loan in self:
            if loan.state != "approved" or not loan.disbursement_date or not loan.disbursement_reference:
                raise UserError(_("Enter the disbursement date and payment reference for an approved loan."))
            installment = round(loan.amount / loan.term_months, 2)
            lines = []
            remaining = loan.amount
            for number in range(1, loan.term_months + 1):
                due = installment if number < loan.term_months else remaining
                lines.append((0, 0, {"sequence": number, "due_date": loan.disbursement_date + relativedelta(months=number), "principal_due": due, "total_due": due}))
                remaining -= due
            loan.write({"state": "disbursed", "installment_amount": installment, "repayment_ids": lines})
            deduction_type = self.env.ref("ddfsc_payroll.component_type_approved_deduction")
            for repayment in loan.repayment_ids:
                component = self.env["ddfsc.employee.payroll.component"].create({
                    "employee_id": loan.employee_id.id,
                    "component_type_id": deduction_type.id,
                    "amount": repayment.total_due,
                    "recurrence": "one_off",
                    "adjustment_type": "other_deduction",
                    "date_from": repayment.due_date,
                    "date_to": repayment.due_date,
                    "state": "approved",
                    "company_id": loan.company_id.id,
                    "loan_repayment_id": repayment.id,
                    "note": _("Loan %(loan)s installment %(sequence)s; disbursement %(reference)s.",
                              loan=loan.name, sequence=repayment.sequence,
                              reference=loan.disbursement_reference),
                })
                repayment.component_id = component
        return True

    def action_cancel(self):
        for loan in self:
            if loan.state not in ("draft", "submitted", "manager", "hr", "approved"):
                raise UserError(_("Only a loan that has not been disbursed can be cancelled."))
            loan.write({"state": "cancelled"})
        return True

    def action_reject(self):
        for loan in self:
            if loan.state not in ("submitted", "manager", "hr"):
                raise UserError(_("Only a loan in an approval step can be rejected."))
            loan.write({"state": "rejected"})
        return True

    def action_close_settled(self):
        """Close a loan only after its payroll installments have all been recovered."""
        self._require_payroll_manager()
        for loan in self:
            if loan.state != "disbursed":
                raise UserError(_("Only a disbursed loan can be closed."))
            if loan.repayment_ids.filtered(lambda line: line.state != "paid"):
                raise UserError(_("All repayment installments must be paid before closing this loan."))
            loan.write({"state": "closed", "settlement_date": fields.Date.context_today(loan),
                        "settlement_reference": _("Closed after payroll recovery")})
        return True

    def action_early_settle(self):
        """Record an authorized cash settlement and stop future payroll recovery."""
        self._require_payroll_manager()
        for loan in self:
            if loan.state != "disbursed":
                raise UserError(_("Only a disbursed loan can be settled early."))
            if not loan.settlement_date or not (loan.settlement_reference or "").strip():
                raise UserError(_("Enter the settlement date and payment reference before early settlement."))
            if loan.settlement_amount < loan.outstanding_balance:
                raise UserError(_(
                    "The settlement amount must cover the current outstanding balance of %(balance).2f.",
                    balance=loan.outstanding_balance,
                ))
            remaining = loan.repayment_ids.filtered(lambda line: line.state != "paid")
            remaining.mapped("component_id").filtered(lambda component: component.state == "approved").action_cancel()
            remaining.write({"state": "paid", "paid_date": loan.settlement_date, "paid_payslip_id": False})
            loan.write({"state": "closed"})
            loan.message_post(body=_("Early settlement recorded: %(amount).2f; reference %(reference)s.",
                                    amount=loan.settlement_amount, reference=loan.settlement_reference))
        return True


class DdfscLoanRepayment(models.Model):
    _name = "ddfsc.loan.repayment"
    _description = "Loan Repayment Schedule"
    _order = "due_date, sequence"

    loan_id = fields.Many2one("ddfsc.employee.loan", required=True, ondelete="cascade")
    sequence = fields.Integer(required=True)
    due_date = fields.Date(required=True)
    principal_due = fields.Monetary(required=True)
    interest_due = fields.Monetary(default=0)
    total_due = fields.Monetary(required=True)
    state = fields.Selection([("scheduled","Scheduled"),("paid","Paid"),("shortfall","Shortfall")], default="scheduled")
    company_id = fields.Many2one(related="loan_id.company_id", store=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    component_id = fields.Many2one("ddfsc.employee.payroll.component", readonly=True, copy=False, ondelete="restrict")
    paid_payslip_id = fields.Many2one("hr.payslip", readonly=True, copy=False, ondelete="restrict")
    paid_date = fields.Date(readonly=True)

    _loan_sequence_unique = models.Constraint("unique(loan_id, sequence)", "Each loan installment sequence must be unique.")

    def action_mark_shortfall(self):
        self.filtered(lambda line: line.state == "scheduled").write({"state": "shortfall"})
        return True
