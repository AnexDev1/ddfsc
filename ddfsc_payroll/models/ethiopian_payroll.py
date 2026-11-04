from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EthiopianTaxBand(models.Model):
    _name = "ddfsc.ethiopian.tax.band"
    _description = "Ethiopian Employment Income Tax Band"
    _order = "date_from desc, lower_bound"

    name = fields.Char(compute="_compute_name", store=True)
    date_from = fields.Date(required=True, default=lambda self: fields.Date.today())
    date_to = fields.Date()
    lower_bound = fields.Monetary(required=True, help="Inclusive monthly taxable-income threshold in ETB.")
    upper_bound = fields.Monetary(help="Inclusive threshold. Leave empty for the highest band.")
    rate = fields.Float(required=True, digits=(5, 2), help="Marginal rate as a percentage, for example 15 for 15%.")
    quick_deduction = fields.Monetary(default=0, help="Optional equivalent quick-formula deduction; it is not an allowance.")
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    note = fields.Text(default="Confirm tax base and statutory treatment with DDFSC HR/Finance before production use.")

    @api.depends("lower_bound", "upper_bound", "rate")
    def _compute_name(self):
        for record in self:
            ceiling = record.upper_bound if record.upper_bound else "Above"
            record.name = "ETB %s – %s (%s%%)" % (record.lower_bound or 0, ceiling, record.rate or 0)

    @api.constrains("lower_bound", "upper_bound", "rate", "date_from", "date_to")
    def _check_values(self):
        for record in self:
            if record.lower_bound < 0 or record.rate < 0 or record.rate > 100:
                raise ValidationError(self.env._("Tax thresholds must be positive and the rate must be between 0 and 100."))
            if record.upper_bound and record.upper_bound < record.lower_bound:
                raise ValidationError(self.env._("The upper threshold cannot be below the lower threshold."))
            if record.date_to and record.date_to < record.date_from:
                raise ValidationError(self.env._("The end date cannot be before the effective date."))

    @api.model
    def calculate_monthly_tax(self, taxable_income, payroll_date=None, company=None):
        """Return PAYE from the applicable, editable monthly tax schedule.

        The caller supplies the already-approved taxable base: the tax schedule
        deliberately does not decide which allowances are taxable.
        """
        company = company or self.env.company
        payroll_date = payroll_date or fields.Date.context_today(self)
        income = max(float(taxable_income or 0.0), 0.0)
        domain = [
            ("company_id", "=", company.id), ("active", "=", True),
            ("date_from", "<=", payroll_date), "|", ("date_to", "=", False),
            ("date_to", ">=", payroll_date), ("lower_bound", "<=", income),
        ]
        band = self.search(domain, order="lower_bound desc, date_from desc", limit=1)
        if not band:
            raise ValidationError(self.env._("No active Ethiopian income-tax band covers %s.") % payroll_date)
        return max((income * band.rate / 100.0) - band.quick_deduction, 0.0)

    @api.model
    def ensure_salary_rule_templates(self):
        """Link new DDFSC rule templates without removing local Finance rules."""
        structure = self.env.ref("ddfsc_payroll.structure_ethiopian_monthly", raise_if_not_found=False)
        if not structure:
            return
        rule_xmlids = (
            "rule_basic_salary", "rule_taxable_allowance", "rule_pensionable_allowance",
            "rule_non_taxable_allowance", "rule_overtime_pay", "rule_shift_differential", "rule_gross_tax_base", "rule_employee_pension",
            "rule_income_tax", "rule_approved_deduction", "rule_net_pay", "rule_employer_pension",
        )
        rules = self.env["hr.salary.rule"]
        for xmlid in rule_xmlids:
            rule = self.env.ref("ddfsc_payroll.%s" % xmlid, raise_if_not_found=False)
            if rule:
                rules |= rule
        missing = rules - structure.rule_ids
        if missing:
            structure.write({"rule_ids": [(4, rule.id) for rule in missing]})


class EthiopianPensionConfig(models.Model):
    _name = "ddfsc.ethiopian.pension.config"
    _description = "Ethiopian Pension Configuration"
    _order = "date_from desc"

    name = fields.Char(required=True, default="Private-sector pension baseline")
    date_from = fields.Date(required=True, default=lambda self: fields.Date.today())
    date_to = fields.Date()
    employee_rate = fields.Float(required=True, default=7.0, digits=(5, 2))
    employer_rate = fields.Float(required=True, default=11.0, digits=(5, 2))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    note = fields.Text(default="For covered private-sector employees. Confirm employee eligibility and the statutory salary base before production use.")

    @api.constrains("employee_rate", "employer_rate", "date_from", "date_to")
    def _check_values(self):
        for record in self:
            if not 0 <= record.employee_rate <= 100 or not 0 <= record.employer_rate <= 100:
                raise ValidationError(self.env._("Pension rates must be between 0 and 100."))
            if record.date_to and record.date_to < record.date_from:
                raise ValidationError(self.env._("The end date cannot be before the effective date."))

    @api.model
    def calculate_contributions(self, pension_salary, payroll_date=None, company=None):
        """Return employee and employer contributions for an approved base."""
        company = company or self.env.company
        payroll_date = payroll_date or fields.Date.context_today(self)
        config = self.search([
            ("company_id", "=", company.id), ("active", "=", True),
            ("date_from", "<=", payroll_date), "|", ("date_to", "=", False),
            ("date_to", ">=", payroll_date),
        ], order="date_from desc", limit=1)
        if not config:
            raise ValidationError(self.env._("No active Ethiopian pension configuration covers %s.") % payroll_date)
        base = max(float(pension_salary or 0.0), 0.0)
        return {
            "employee": base * config.employee_rate / 100.0,
            "employer": base * config.employer_rate / 100.0,
            "config": config,
        }


class DdfscOvertimePayRate(models.Model):
    _name = "ddfsc.overtime.pay.rate"
    _description = "Overtime Pay Rate"
    _order = "date_from desc, id desc"

    name = fields.Char(required=True)
    date_from = fields.Date(required=True, default=lambda self: fields.Date.today())
    date_to = fields.Date()
    multiplier = fields.Float(required=True, default=1.5, digits=(8, 4))
    monthly_standard_hours = fields.Float(required=True, default=208.0, digits=(16, 2))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    note = fields.Text(default="Confirm the approved multiplier and monthly standard-hours basis with DDFSC HR and Finance before production use.")

    @api.constrains("multiplier", "monthly_standard_hours", "date_from", "date_to")
    def _check_values(self):
        for record in self:
            if record.multiplier <= 0 or record.monthly_standard_hours <= 0:
                raise ValidationError(self.env._("Overtime multiplier and monthly standard hours must be greater than zero."))
            if record.date_to and record.date_to < record.date_from:
                raise ValidationError(self.env._("The end date cannot be before the effective date."))

    @api.model
    def calculate_payment(self, approved_hours, monthly_wage, payroll_date=None, company=None):
        company = company or self.env.company
        payroll_date = payroll_date or fields.Date.context_today(self)
        rate = self.search([
            ("company_id", "=", company.id), ("active", "=", True),
            ("date_from", "<=", payroll_date), "|", ("date_to", "=", False), ("date_to", ">=", payroll_date),
        ], order="date_from desc", limit=1)
        if not rate:
            raise ValidationError(self.env._("No active overtime pay rate covers %s.") % payroll_date)
        hourly_wage = max(float(monthly_wage or 0.0), 0.0) / rate.monthly_standard_hours
        return round(max(float(approved_hours or 0.0), 0.0) * hourly_wage * rate.multiplier, 2)
